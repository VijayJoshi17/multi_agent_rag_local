from app.agents.base import BaseAgent
from app.models.schemas import AgentState
from app.utils.logger import setup_logger
from app.rag.bm25_retriever import get_bm25_retriever
from app.rag.embeddings import EmbeddingService
from app.rag.vector_store import VectorStore

logger = setup_logger(__name__)


class RouterAgent(BaseAgent):
    """
    Determines whether to route the query to internal retrieval or external web search.
    Uses deterministic rules first, LLM classification second.
    """

    def __init__(self):
        super().__init__(name="Router")
        self.bm25 = get_bm25_retriever()
        self.embedding_service = EmbeddingService()
        self.vector_store = VectorStore()
        
        self.system_prompt = """
You are a routing classifier.

Decide if the query should be answered using:
- internal_knowledge: private documents, uploaded files, known aliases
- external_search: public facts, news, weather, finance, geography

Output ONE word only:
internal_knowledge
OR
external_search
"""

    async def run(self, state: AgentState) -> AgentState:
        logger.info(f"RouterAgent classifying: {state.query}")

        # 1. Deterministic External Keywords
        external_triggers = [
            "stock", "price", "market cap", "share", "weather", 
            "news", "forecast", "capital of"
        ]
        if any(t in state.query.lower() for t in external_triggers):
            state.route = "web_search"
            return state

        # 2. Semantic Relevance Check (The "Do we have anything?" check)
        # We perform a quick lightweight search to see if any doc is semantically close.
        try:
            query_emb = await self.embedding_service.get_embedding(state.query)
            # Top 1 is enough to check relevance
            vector_results = await self.vector_store.search(query_emb, top_k=1)
            semantic_score = vector_results[0].score if vector_results else 0.0
            logger.info(f"Router Semantic Score: {semantic_score:.4f}")
        except Exception as e:
            logger.warning(f"Router semantic check failed: {e}")
            semantic_score = 0.0

        # 3. lexical Check (BM25)
        bm25_score = 0.0
        if self.bm25.is_ready:
            hits = self.bm25.search(state.query, k=1)
            if hits:
                bm25_score = hits[0].get("score", 0.0)
            logger.info(f"Router BM25 Score: {bm25_score:.4f}")

        # 4. DECISION LOGIC
        # Thresholds:
        # Semantic > 0.45: Likely relevant context exists (Cosine sim usually 0.4-0.6 for relevant paragraphs)
        # BM25 > 3.0: Specific keyword match (e.g. unique names)
        
        if semantic_score > 0.45:
            logger.info("High Semantic Relevance -> Force Retrieve")
            state.route = "retrieve"
            return state
            
        if bm25_score > 4.0: # Very strong keyword match (e.g. rare name)
            logger.info("High Keyword Relevance -> Force Retrieve")
            state.route = "retrieve"
            return state
            
        # If both scores are low, likely we don't have it.
        # But we let the LLM decide for edge cases, OR we bias towards Web Search.
        # If it's very low, strictly Web Search.
        if semantic_score < 0.35 and bm25_score < 2.0:
            logger.info("Low Relevance (Semantic & Keyword) -> Force Web Search")
            state.route = "web_search"
            return state

        # 5. LLM Fallback (for ambiguous cases like 0.35 < score < 0.45)
        route = await self.call_llm(
            f"Query: {state.query}\nRoute:", system_prompt=self.system_prompt
        )
        route = route.strip().lower()

        state.route = "web_search" if "external" in route else "retrieve"
        logger.info(f"RouterAgent decision (LLM): {state.route}")
        return state

