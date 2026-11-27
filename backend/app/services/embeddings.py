"""Local embedding + reranking models, loaded once and run off the event loop."""

from typing import Protocol

from starlette.concurrency import run_in_threadpool

from app.core.logging import get_logger

logger = get_logger(__name__)


class Embedder(Protocol):
    dimension: int

    async def embed_query(self, text: str) -> list[float]: ...
    async def embed_documents(self, texts: list[str]) -> list[list[float]]: ...


class Reranker(Protocol):
    async def score(self, query: str, passages: list[str]) -> list[float]: ...


class SentenceTransformerEmbedder:
    def __init__(self, model_name: str):
        from sentence_transformers import SentenceTransformer

        logger.info("Loading embedding model %s", model_name)
        self._model = SentenceTransformer(model_name, device="cpu")
        get_dim = getattr(self._model, "get_embedding_dimension", None) or (
            self._model.get_sentence_embedding_dimension
        )
        self.dimension: int = int(get_dim() or 384)

    def _encode(self, texts: list[str]) -> list[list[float]]:
        vecs = self._model.encode(
            texts, batch_size=32, normalize_embeddings=True, show_progress_bar=False
        )
        return vecs.tolist()

    async def embed_query(self, text: str) -> list[float]:
        return (await run_in_threadpool(self._encode, [text]))[0]

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return await run_in_threadpool(self._encode, texts)


class CrossEncoderReranker:
    def __init__(self, model_name: str):
        from sentence_transformers import CrossEncoder

        logger.info("Loading reranker model %s", model_name)
        self._model = CrossEncoder(model_name, device="cpu")

    def _predict(self, query: str, passages: list[str]) -> list[float]:
        return [float(s) for s in self._model.predict([(query, p) for p in passages])]

    async def score(self, query: str, passages: list[str]) -> list[float]:
        if not passages:
            return []
        return await run_in_threadpool(self._predict, query, passages)
