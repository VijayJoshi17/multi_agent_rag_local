"""Document ingestion: register uploads, then chunk/embed/index them in a background worker."""

import asyncio
import contextlib
import hashlib
from pathlib import Path

from langchain_text_splitters import RecursiveCharacterTextSplitter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.concurrency import run_in_threadpool

from app.core.config import Settings
from app.core.logging import get_logger
from app.db.models import Document, DocumentStatus
from app.schemas.rag import Chunk
from app.services import parsing
from app.services.bm25 import BM25Index
from app.services.embeddings import Embedder
from app.services.fetch import fetch_page
from app.services.metrics import INGESTED_CHUNKS
from app.services.vector_store import VectorStore

logger = get_logger(__name__)


class IngestionService:
    def __init__(
        self,
        settings: Settings,
        sessionmaker: async_sessionmaker[AsyncSession],
        embedder: Embedder,
        store: VectorStore,
        bm25: BM25Index,
    ):
        self.settings = settings
        self.sessionmaker = sessionmaker
        self.embedder = embedder
        self.store = store
        self.bm25 = bm25
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.CHUNK_SIZE, chunk_overlap=settings.CHUNK_OVERLAP
        )
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._worker: asyncio.Task[None] | None = None
        settings.documents_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ lifecycle
    async def start(self) -> None:
        self._worker = asyncio.create_task(self._run_worker(), name="ingestion-worker")
        # Crash recovery: re-queue anything that never finished.
        async with self.sessionmaker() as s:
            rows = await s.scalars(
                select(Document.id).where(
                    Document.status.in_([DocumentStatus.PENDING, DocumentStatus.PROCESSING])
                )
            )
            for doc_id in rows:
                self._queue.put_nowait(doc_id)

    async def stop(self) -> None:
        if self._worker:
            self._worker.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._worker

    async def wait_idle(self) -> None:
        """Block until the queue is drained (used by tests)."""
        await self._queue.join()

    # ------------------------------------------------------------------ uploads
    def _path(self, doc: Document) -> Path:
        return self.settings.documents_dir / f"{doc.id}.{doc.content_type}"

    async def register_upload(self, filename: str, data: bytes) -> tuple[list[Document], list[str]]:
        ext = parsing.sniff(filename, data)
        if ext in parsing.DATASET_EXTS:
            raise parsing.UnsupportedFileError(
                "CSV/XLSX files are datasets — upload them via /datasets"
            )
        if ext in parsing.ARCHIVE_EXTS:
            files, skipped = parsing.expand_zip(
                filename, data,
                max_members=self.settings.MAX_ZIP_MEMBERS,
                max_total_bytes=self.settings.MAX_ZIP_UNCOMPRESSED_MB * 1024 * 1024,
            )
        else:
            files, skipped = [parsing.FilePayload(filename, ext, data)], []

        return await self._add([(f.filename, f.ext.lstrip("."), f.data) for f in files], skipped)

    async def register_url(self, url: str) -> tuple[list[Document], list[str]]:
        """Fetch a public web page and ingest its readable text. The URL is the document name."""
        page = await fetch_page(url)
        text = f"# {page.title}\n\nSource: {page.url}\n\n{page.text}"
        return await self._add([(page.url, "url", text.encode("utf-8"))], [])

    async def _add(
        self, files: list[tuple[str, str, bytes]], skipped: list[str]
    ) -> tuple[list[Document], list[str]]:
        """Store new files (skipping duplicates by content hash) and queue them for ingestion."""
        created: list[Document] = []
        async with self.sessionmaker() as s:
            for filename, content_type, data in files:
                digest = hashlib.sha256(data).hexdigest()
                dup = await s.scalar(
                    select(Document).where(
                        Document.content_hash == digest, Document.status != DocumentStatus.FAILED
                    )
                )
                if dup:
                    skipped.append(f"{filename} (duplicate of {dup.filename})")
                    continue
                doc = Document(filename=filename, content_type=content_type,
                               size_bytes=len(data), content_hash=digest)
                s.add(doc)
                await s.flush()
                await run_in_threadpool(self._path(doc).write_bytes, data)
                created.append(doc)
            await s.commit()

        for doc in created:
            self._queue.put_nowait(doc.id)
        return created, skipped

    # ------------------------------------------------------------------ deletion
    async def delete(self, doc: Document) -> None:
        await self.store.delete_document(doc.id)
        self._path(doc).unlink(missing_ok=True)
        await self.bm25.rebuild(self.store)

    async def reset(self) -> None:
        await self.store.reset()
        self.bm25.clear()
        for p in self.settings.documents_dir.glob("*"):
            p.unlink(missing_ok=True)

    # ------------------------------------------------------------------ worker
    async def _run_worker(self) -> None:
        while True:
            doc_id = await self._queue.get()
            try:
                await self._process(doc_id)
            except Exception:  # noqa: BLE001 - worker must never die
                logger.exception("Ingestion crashed for %s", doc_id)
            finally:
                self._queue.task_done()

    def _chunk(self, doc: Document, pages: list[parsing.PageText]) -> list[Chunk]:
        chunks: list[Chunk] = []
        for page in pages:
            for piece in self.splitter.split_text(page.text):
                if piece.strip():
                    chunks.append(Chunk(
                        text=piece, source=doc.filename, document_id=doc.id,
                        chunk_index=len(chunks), page=page.page,
                        url=doc.filename if doc.content_type == "url" else None,
                    ))
        return chunks

    async def _process(self, doc_id: str) -> None:
        async with self.sessionmaker() as s:
            doc = await s.get(Document, doc_id)
            if doc is None:
                return
            doc.status = DocumentStatus.PROCESSING
            await s.commit()
            try:
                data = await run_in_threadpool(self._path(doc).read_bytes)
                pages = await run_in_threadpool(parsing.extract_text, f".{doc.content_type}", data)
                chunks = self._chunk(doc, pages)
                if not chunks:
                    raise ValueError("No extractable text found (scanned PDF or empty file?)")
                vectors = await self.embedder.embed_documents([c.text for c in chunks])
                await self.store.upsert(chunks, vectors)
                doc.chunk_count = len(chunks)
                doc.status = DocumentStatus.READY
                doc.error = None
                INGESTED_CHUNKS.inc(len(chunks))
                logger.info("Ingested %s (%d chunks)", doc.filename, len(chunks))
            except Exception as e:  # noqa: BLE001
                logger.warning("Ingestion failed for %s: %s", doc.filename, e)
                doc.status = DocumentStatus.FAILED
                doc.error = str(e)[:500]
            await s.commit()
        if self._queue.qsize() == 0:
            # Batch BM25 rebuilds: only once the queue drains.
            await self.bm25.rebuild(self.store)
