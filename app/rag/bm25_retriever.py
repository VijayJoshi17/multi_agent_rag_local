import logging
from rank_bm25 import BM25Okapi
from typing import List, Dict
from qdrant_client import QdrantClient
from app.config import settings

logger = logging.getLogger(__name__)

# Singleton Instance
_bm25_instance = None

def get_bm25_retriever():
    global _bm25_instance
    if _bm25_instance is None:
        _bm25_instance = BM25Retriever()
    return _bm25_instance

class BM25Retriever:
    """
    In-memory BM25 retriever.
    NOTE: In a production system with millions of docs, you would use Elasticsearch/Solr.
    For this local RAG, we load chunks from Qdrant into memory at startup.
    """
    def __init__(self):
        self.bm25 = None
        self.documents = [] # List of text content
        self.metadatas = [] # List of metadata dicts
        self.is_ready = False
        
    def build_index(self, client: QdrantClient):
        """
        Fetches all points from Qdrant directly to build the keyword index.
        """
        try:
            logger.info("Building BM25 Index from Vector Store...")
            # Scroll all points (limit to 10k for safety in this demo)
            # In Qdrant, we use scroll()
            points = []
            offset = None
            while True:
                results, offset = client.scroll(
                    collection_name="rag_collection_free",
                    limit=100,
                    offset=offset,
                    with_payload=True,
                    with_vectors=False
                )
                points.extend(results)
                if offset is None:
                    break
            
            if not points:
                logger.warning("No documents found in Vector Store. BM25 Index is empty.")
                self.is_ready = False
                return

            self.documents = []
            self.metadatas = []
            tokenized_corpus = []

            for point in points:
                payload = point.payload or {}
                text = payload.get("content", "")
                if text:
                    self.documents.append(text)
                    self.metadatas.append(payload)
                    # Simple whitespace tokenization for speed
                    tokenized_corpus.append(text.lower().split())

            self.bm25 = BM25Okapi(tokenized_corpus)
            self.is_ready = True
            logger.info(f"BM25 Index built with {len(self.documents)} chunks.")
            
        except Exception as e:
            logger.error(f"Failed to build BM25 index: {e}")
            self.is_ready = False

    def search(self, query: str, k: int = 3) -> List[Dict]:
        if not self.is_ready:
            logger.warning("BM25 not ready. Returning empty.")
            return []
            
        tokenized_query = query.lower().split()
        scores = self.bm25.get_scores(tokenized_query)
        
        # Pair up doc_idx and score
        # We need to sort by score descending
        scored_docs = []
        for idx, score in enumerate(scores):
            if score > 0:
                scored_docs.append((idx, score))
        
        # Sort by score desc
        scored_docs.sort(key=lambda x: x[1], reverse=True)
        
        # Take top k
        top_n = scored_docs[:k]
        
        results = []
        for idx, score in top_n:
            results.append({
                "content": self.documents[idx],
                "metadata": self.metadatas[idx],
                "score": score
            })
            
        return results
    def clear(self):
        """Clear the in-memory index."""
        self.bm25 = None
        self.documents = []
        self.metadatas = []
        self.is_ready = False
        logger.info("BM25 Index cleared.")
