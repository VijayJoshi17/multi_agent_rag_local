"""Qdrant-backed vector store (server mode via URL, or embedded local mode via path)."""

import uuid
from collections.abc import AsyncIterator

from qdrant_client import AsyncQdrantClient, models

from app.core.logging import get_logger
from app.schemas.rag import Chunk

logger = get_logger(__name__)


class VectorStore:
    def __init__(
        self, client: AsyncQdrantClient, collection: str, dimension: int,
        server_mode: bool = False,
    ):
        self.client = client
        self._server_mode = server_mode
        self.collection = collection
        self.dimension = dimension

    @classmethod
    def create(
        cls, *, url: str | None, path: str, collection: str, dimension: int
    ) -> "VectorStore":
        client = AsyncQdrantClient(url=url) if url else AsyncQdrantClient(path=path)
        return cls(client, collection, dimension, server_mode=bool(url))

    async def ensure_collection(self) -> None:
        if await self.client.collection_exists(self.collection):
            info = await self.client.get_collection(self.collection)
            params = info.config.params.vectors
            size = getattr(params, "size", None)
            if size is not None and size != self.dimension:
                raise RuntimeError(
                    f"Collection '{self.collection}' has dimension {size}, but the embedding "
                    f"model produces {self.dimension}. Reset the knowledge base or change "
                    f"QDRANT_COLLECTION."
                )
            return
        await self.client.create_collection(
            self.collection,
            vectors_config=models.VectorParams(
                size=self.dimension, distance=models.Distance.COSINE
            ),
        )
        if self._server_mode:  # embedded/local mode ignores payload indexes
            await self.client.create_payload_index(
                self.collection, "document_id", models.PayloadSchemaType.KEYWORD
            )
        logger.info("Created Qdrant collection %s (dim=%d)", self.collection, self.dimension)

    async def upsert(self, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        points = [
            models.PointStruct(
                id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{c.document_id}:{c.chunk_index}")),
                vector=v,
                payload=c.payload(),
            )
            for c, v in zip(chunks, vectors, strict=True)
        ]
        for i in range(0, len(points), 256):
            await self.client.upsert(self.collection, points=points[i : i + 256], wait=True)

    async def search(self, vector: list[float], limit: int) -> list[Chunk]:
        res = await self.client.query_points(
            self.collection, query=vector, limit=limit, with_payload=True
        )
        return [Chunk.from_payload(p.payload or {}, score=p.score) for p in res.points]

    async def delete_document(self, document_id: str) -> None:
        await self.client.delete(
            self.collection,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[models.FieldCondition(
                        key="document_id", match=models.MatchValue(value=document_id)
                    )]
                )
            ),
            wait=True,
        )

    async def iter_all(self, batch: int = 512) -> AsyncIterator[Chunk]:
        offset = None
        while True:
            points, offset = await self.client.scroll(
                self.collection, limit=batch, offset=offset, with_payload=True, with_vectors=False
            )
            for p in points:
                yield Chunk.from_payload(p.payload or {})
            if offset is None:
                break

    async def count(self) -> int:
        return (await self.client.count(self.collection, exact=True)).count

    async def reset(self) -> None:
        if await self.client.collection_exists(self.collection):
            await self.client.delete_collection(self.collection)
        await self.ensure_collection()

    async def ping(self) -> bool:
        try:
            await self.client.get_collections()
            return True
        except Exception:  # noqa: BLE001
            return False

    async def close(self) -> None:
        await self.client.close()
