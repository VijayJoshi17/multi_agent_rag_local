from typing import Any

from app.agents.base import Agent, load_prompt
from app.core.config import Settings
from app.graph.context import NodeContext
from app.graph.state import GraphState, Route
from app.services.bm25 import BM25Index
from app.services.embeddings import Embedder
from app.services.llm import LLMClient
from app.services.metrics import ROUTE_COUNTER
from app.services.vector_store import VectorStore

_MODE_ROUTES: dict[str, Route] = {
    "documents": "retrieve",
    "web": "web_search",
    "data": "data_analyst",
}

# Queries that are almost always about live, public information.
_LIVE_TRIGGERS = (
    "stock", "share price", "market cap", "weather", "news", "today", "latest",
    "forecast", "current price", "exchange rate", "score",
)


class RouterAgent(Agent):
    """Hybrid router: cheap retrieval-signal heuristics first, LLM only for ambiguous cases."""

    name = "router"

    def __init__(self, llm: LLMClient, embedder: Embedder, store: VectorStore,
                 bm25: BM25Index, settings: Settings):
        self.llm, self.embedder, self.store, self.bm25 = llm, embedder, store, bm25
        self.s = settings

    async def _decide(self, state: GraphState, ctx: NodeContext) -> Route:
        mode = state.get("mode", "auto")
        if mode in _MODE_ROUTES:
            await ctx.log(f"Mode '{mode}' selected explicitly.")
            return _MODE_ROUTES[mode]
        if state.get("document_ids"):
            await ctx.log("Specific documents selected → searching only those.")
            return "retrieve"

        query = state["query"]
        if self.bm25.size == 0:
            await ctx.log("Knowledge base is empty → web search.")
            return "web_search"

        hits = await self.store.search(await self.embedder.embed_query(query), limit=1)
        semantic = (hits[0].score or 0.0) if hits else 0.0
        kw_hits = await self.bm25.search(query, k=1)
        keyword = (kw_hits[0].score or 0.0) if kw_hits else 0.0
        await ctx.log(f"Relevance signals — semantic: {semantic:.3f}, BM25: {keyword:.2f}")

        if semantic >= self.s.ROUTER_SEMANTIC_HIGH:
            return "retrieve"
        if any(t in query.lower() for t in _LIVE_TRIGGERS):
            await ctx.log("Live-information keywords detected.")
            return "web_search"
        if keyword >= self.s.ROUTER_BM25_HIGH:
            return "retrieve"
        if semantic < self.s.ROUTER_SEMANTIC_LOW and keyword < self.s.ROUTER_BM25_HIGH / 2:
            return "web_search"

        await ctx.log("Ambiguous signals — asking the LLM to classify.")
        verdict = await self.llm.complete(f"Query: {query}\nLabel:",
                                          system=load_prompt("router"),
                                          temperature=0)
        return "web_search" if "external" in verdict.lower() else "retrieve"

    async def __call__(self, state: GraphState, ctx: NodeContext) -> dict[str, Any]:
        route = await self._decide(state, ctx)
        ROUTE_COUNTER.labels(route=route).inc()
        await ctx.log(f"Route → {route}")
        return {"route": route}

    @staticmethod
    def summary(update: dict[str, Any]) -> str | None:
        return f"Route: {update.get('route')}"
