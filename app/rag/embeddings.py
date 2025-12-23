from sentence_transformers import SentenceTransformer
from app.config import settings
from typing import List

class EmbeddingService:
    def __init__(self):
        # Initialize SentenceTransformer model (caches locally)
        self.model = SentenceTransformer(settings.EMBEDDING_MODEL)

    async def get_embedding(self, text: str) -> List[float]:
        # Synchronous implementation is fine for now; 
        # in high-load async, run_in_executor might be needed.
        embedding = self.model.encode(text)
        return embedding.tolist()

    async def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        embeddings = self.model.encode(texts)
        return embeddings.tolist()
