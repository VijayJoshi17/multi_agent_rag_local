# ===================== retriever.py =====================
from app.agents.base import BaseAgent
from app.models.schemas import AgentState, DocumentChunk
from app.rag.embeddings import EmbeddingService
from app.rag.vector_store import VectorStore
from app.rag.bm25_retriever import get_bm25_retriever
from app.utils.logger import setup_logger
from typing import List, Dict

logger = setup_logger(__name__)


from sentence_transformers import CrossEncoder

class RetrieverAgent(BaseAgent):
    """
    Hybrid retriever (Vector + BM25) with Cross-Encoder Reranking.
    """

    def __init__(self):
        super().__init__(name="Retriever")
        self.embedding_service = EmbeddingService()
        self.vector_store_client = VectorStore()
        self.bm25 = get_bm25_retriever()
        
        # Initialize Re-ranker
        # ms-marco-MiniLM-L-6-v2 is fast and effective for passage ranking
        try:
             self.reranker = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')
        except Exception as e:
             logger.warning(f"Failed to load Reranker: {e}")
             self.reranker = None

        try:
            if not self.bm25.is_ready:
                self.bm25.build_index(self.vector_store_client.client)
        except Exception as e:
            logger.warning(f"BM25 initialization failed: {e}")

    def reciprocal_rank_fusion(
        self,
        vector_results: List[DocumentChunk],
        keyword_results: List[DocumentChunk],
        k: int = 60,
        keyword_weight: float = 1.5,
    ) -> List[DocumentChunk]:
        """Combine results using RRF"""
        scores: Dict[str, Dict] = {}
        
        # Helper to avoid duplicates
        unique_map = {}

        def add_docs(docs: List[DocumentChunk], weight: float):
            for rank, doc in enumerate(docs):
                # Use content hash to deduplicate
                key = hash(doc.content)
                if key not in scores:
                    scores[key] = {"doc": doc, "score": 0.0}
                    unique_map[key] = doc
                scores[key]["score"] += weight / (k + rank + 1)

        add_docs(vector_results, weight=1.0)
        add_docs(keyword_results, weight=keyword_weight)

        ranked = sorted(scores.values(), key=lambda x: x["score"], reverse=True)
        return [item["doc"] for item in ranked]

    async def run(self, state: AgentState) -> AgentState:
        self.log(state, f"Searching for: {state.query}")

        # 1. Broad Retrieval (Vector + BM25)
        # Fetch more candidates (top_k=10) to give re-ranker enough options
        query_embedding = await self.embedding_service.get_embedding(state.query)
        self.log(state, "Generated query embedding.")
        
        vector_results = await self.vector_store_client.search(query_embedding, top_k=40)
        self.log(state, f"Vector Search: Found {len(vector_results)} candidates.")
        
        keyword_results: List[DocumentChunk] = []
        if self.bm25.is_ready:
            for r in self.bm25.search(state.query, k=40):
                keyword_results.append(
                    DocumentChunk(content=r["content"], metadata=r.get("metadata", {}))
                )
            self.log(state, f"BM25 Search: Found {len(keyword_results)} candidates.")

        # 2. Fusion
        if keyword_results:
            candidates = self.reciprocal_rank_fusion(vector_results, keyword_results)
            self.log(state, f"Fused Hybrid Results: {len(candidates)} candidates.")
        else:
            candidates = vector_results
            self.log(state, "Using Vector Results only (BM25 not ready or empty).")

        # 3. Re-ranking (Cross-Encoder)
        if self.reranker and candidates:
            self.log(state, f"Reranking {len(candidates)} candidates with Cross-Encoder...")
            
            # Prepare pairs: (query, doc_text)
            pairs = [[state.query, doc.content] for doc in candidates]
            
            try:
                scores = self.reranker.predict(pairs)
                
                # Attach scores and sort
                ranked_candidates = []
                for doc, score in zip(candidates, scores):
                    ranked_candidates.append((doc, score))
                
                # Sort descending by score
                ranked_candidates.sort(key=lambda x: x[1], reverse=True)
                
                top_score = ranked_candidates[0][1]
                self.log(state, f"Reranking Complete. Top Score: {top_score:.4f}")

                # Take top 5
                final_docs = [doc for doc, score in ranked_candidates[:10]]
                
            except Exception as e:
                logger.error(f"Reranking failed: {e}")
                self.log(state, f"Reranking Failed: {e}. Falling back to initial rank.")
                final_docs = candidates[:10]
        else:
             final_docs = candidates[:10]

        state.retrieved_docs = final_docs
        self.log(state, f"Final Selection: Top {len(final_docs)} documents returned.")
        return state
