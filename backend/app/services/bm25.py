"""In-memory BM25 keyword index, rebuilt from the vector store whenever the corpus changes.

Fine for a single-user knowledge base (tens of thousands of chunks). For larger corpora
swap this for Qdrant sparse vectors or OpenSearch behind the same interface.
"""

import asyncio
import math
import re

from rank_bm25 import BM25Okapi
from starlette.concurrency import run_in_threadpool

from app.core.logging import get_logger
from app.schemas.rag import Chunk
from app.services.vector_store import VectorStore

logger = get_logger(__name__)

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


class LuceneBM25(BM25Okapi):
    """BM25 with Lucene's IDF, log(1 + (N - n + 0.5) / (n + 0.5)).

    rank_bm25's classic Okapi IDF goes negative for terms present in more than half the
    documents — on a small knowledge base that zeroes out almost every match.
    """

    def _calc_idf(self, nd: dict[str, int]) -> None:  # noqa: D401
        for word, freq in nd.items():
            self.idf[word] = math.log(1 + (self.corpus_size - freq + 0.5) / (freq + 0.5))


class BM25Index:
    def __init__(self) -> None:
        self._bm25: LuceneBM25 | None = None
        self._chunks: list[Chunk] = []
        self._lock = asyncio.Lock()

    @property
    def size(self) -> int:
        return len(self._chunks)

    async def rebuild(self, store: VectorStore) -> None:
        async with self._lock:
            chunks = [c async for c in store.iter_all()]
            if not chunks:
                self._bm25, self._chunks = None, []
                logger.info("BM25 index is empty")
                return
            corpus = [tokenize(c.text) for c in chunks]
            self._bm25 = await run_in_threadpool(LuceneBM25, corpus)
            self._chunks = chunks
            logger.info("BM25 index rebuilt with %d chunks", len(chunks))

    def _search(self, query: str, k: int, document_ids: list[str] | None) -> list[Chunk]:
        if self._bm25 is None:
            return []
        tokens = tokenize(query)
        if not tokens:
            return []
        scores = self._bm25.get_scores(tokens)
        allowed = set(document_ids) if document_ids else None
        ranked = sorted(
            ((i, s) for i, s in enumerate(scores)
             if s > 0 and (allowed is None or self._chunks[i].document_id in allowed)),
            key=lambda x: x[1], reverse=True,
        )[:k]
        return [self._chunks[i].model_copy(update={"score": float(s)}) for i, s in ranked]

    async def search(
        self, query: str, k: int, document_ids: list[str] | None = None
    ) -> list[Chunk]:
        return await run_in_threadpool(self._search, query, k, document_ids)

    def clear(self) -> None:
        self._bm25, self._chunks = None, []
