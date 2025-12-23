from qdrant_client import QdrantClient, models
from app.config import settings
from app.models.schemas import DocumentChunk
from typing import List
import uuid

# Singleton Client Instance to prevent locking issues
_client_instance = None

def get_qdrant_client():
    global _client_instance
    if _client_instance is None:
        if settings.QDRANT_URL:
            _client_instance = QdrantClient(url=settings.QDRANT_URL)
        else:
            _client_instance = QdrantClient(path=settings.QDRANT_PATH)
    return _client_instance

class VectorStore:
    def __init__(self, collection_name: str = "rag_collection_free"):
        self.client = get_qdrant_client()
        self.collection_name = collection_name
        # all-MiniLM-L6-v2 uses 384 dimensions
        self.embedding_size = 384 

    async def ensure_collection(self):
        collections = self.client.get_collections()
        if self.collection_name not in [c.name for c in collections.collections]:
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=models.VectorParams(
                    size=self.embedding_size,
                    distance=models.Distance.COSINE
                )
            )

    async def upsert_documents(self, documents: List[DocumentChunk], embeddings: List[List[float]]):
        await self.ensure_collection()
        
        points = []
        for doc, emb in zip(documents, embeddings):
            points.append(models.PointStruct(
                id=str(uuid.uuid4()),
                vector=emb,
                payload={
                    "content": doc.content,
                    "metadata": doc.metadata
                }
            ))
            
        self.client.upsert(
            collection_name=self.collection_name,
            points=points
        )

    async def search(self, query_embedding: List[float], top_k: int = 3) -> List[DocumentChunk]:
        # Using query_points which is the unified search method for newer Qdrant clients
        results = self.client.query_points(
            collection_name=self.collection_name,
            query=query_embedding,
            limit=top_k
        )
        
        return [
            DocumentChunk(
                content=res.payload["content"],
                metadata=res.payload["metadata"],
                score=res.score
            )
            for res in results.points
        ]
    async def clear(self):
        """Delete and recreate the collection."""
        try:
             self.client.delete_collection(self.collection_name)
             await self.ensure_collection()
             return True
        except Exception as e:
             print(f"Failed to clear collection: {e}")
             return False
