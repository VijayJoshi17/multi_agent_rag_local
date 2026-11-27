from fastapi import APIRouter, Depends, File, Request, Response, UploadFile
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_container, get_session, limiter, read_upload
from app.container import Container
from app.core.config import get_settings
from app.core.errors import AppError, NotFoundError
from app.db.models import Document, DocumentStatus
from app.schemas.api import DocumentOut, KnowledgeBaseStats, UploadResult

router = APIRouter(tags=["knowledge-base"])


@router.post("/documents", response_model=UploadResult, status_code=202)
@limiter.limit(lambda: get_settings().RATE_LIMIT_UPLOAD)
async def upload_documents(
    request: Request,
    files: list[UploadFile] = File(..., description="TXT, MD, PDF, DOCX, PPTX or ZIP"),
    c: Container = Depends(get_container),
) -> UploadResult:
    """Registers documents and queues them for background ingestion.
    Poll `GET /documents` for status (`pending` → `processing` → `ready` | `failed`)."""
    max_bytes = c.settings.MAX_UPLOAD_MB * 1024 * 1024
    created, skipped = [], []
    for f in files:
        data = await read_upload(f, max_bytes)
        try:
            docs, skip = await c.ingestion.register_upload(f.filename or "upload", data)
        except AppError as e:
            if len(files) == 1:
                raise
            skipped.append(f"{f.filename}: {e.message}")
            continue
        created.extend(docs)
        skipped.extend(skip)
    return UploadResult(
        documents=[DocumentOut.model_validate(d) for d in created], skipped=skipped
    )


@router.get("/documents", response_model=list[DocumentOut])
async def list_documents(s: AsyncSession = Depends(get_session)) -> list[Document]:
    return list(await s.scalars(select(Document).order_by(Document.created_at.desc())))


@router.get("/documents/{document_id}", response_model=DocumentOut)
async def get_document(document_id: str, s: AsyncSession = Depends(get_session)) -> Document:
    doc = await s.get(Document, document_id)
    if doc is None:
        raise NotFoundError("Document not found")
    return doc


@router.delete("/documents/{document_id}", status_code=204)
async def delete_document(
    document_id: str,
    s: AsyncSession = Depends(get_session),
    c: Container = Depends(get_container),
) -> Response:
    doc = await s.get(Document, document_id)
    if doc is None:
        raise NotFoundError("Document not found")
    await c.ingestion.delete(doc)
    await s.delete(doc)
    await s.commit()
    return Response(status_code=204)


@router.get("/knowledge-base/stats", response_model=KnowledgeBaseStats)
async def kb_stats(
    s: AsyncSession = Depends(get_session), c: Container = Depends(get_container)
) -> KnowledgeBaseStats:
    docs = await s.scalar(
        select(func.count()).select_from(Document).where(Document.status == DocumentStatus.READY)
    )
    return KnowledgeBaseStats(documents=docs or 0, chunks=await c.store.count())


@router.delete("/knowledge-base", status_code=204)
async def reset_knowledge_base(
    s: AsyncSession = Depends(get_session), c: Container = Depends(get_container)
) -> Response:
    """Delete every document, chunk and stored file."""
    await c.ingestion.reset()
    await s.execute(delete(Document))
    await s.commit()
    return Response(status_code=204)
