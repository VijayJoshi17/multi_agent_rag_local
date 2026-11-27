from typing import Any

from app.agents.base import Agent
from app.core.config import Settings
from app.graph.context import NodeContext
from app.graph.state import GraphState
from app.schemas.rag import Chunk
from app.services.bm25 import BM25Index
from app.services.embeddings import Embedder, Reranker
from app.services.vector_store import VectorStore


def reciprocal_rank_fusion(
    ranked_lists: list[list[Chunk]], weights: list[float], k: int = 60
) -> list[Chunk]:
    scores: dict[str, float] = {}
    by_key: dict[str, Chunk] = {}
    for docs, w in zip(ranked_lists, weights, strict=True):
        for rank, doc in enumerate(docs):
            by_key.setdefault(doc.key, doc)
            scores[doc.key] = scores.get(doc.key, 0.0) + w / (k + rank + 1)
    order = sorted(scores, key=scores.__getitem__, reverse=True)
    return [by_key[key].model_copy(update={"score": scores[key]}) for key in order]


class RetrieverAgent(Agent):
    """Hybrid search (dense + BM25) → Reciprocal Rank Fusion → cross-encoder rerank."""

    name = "retrieve"

    def __init__(self, embedder: Embedder, store: VectorStore, bm25: BM25Index,
                 reranker: Reranker | None, settings: Settings):
        self.embedder, self.store, self.bm25, self.reranker = embedder, store, bm25, reranker
        self.pool = settings.CANDIDATE_POOL

    async def __call__(self, state: GraphState, ctx: NodeContext) -> dict[str, Any]:
        query = state["query"]
        top_k = state.get("top_k", 5)

        dense = await self.store.search(await self.embedder.embed_query(query), limit=self.pool)
        sparse = await self.bm25.search(query, k=self.pool)
        await ctx.log(f"Dense: {len(dense)} candidates · BM25: {len(sparse)} candidates")

        fused = reciprocal_rank_fusion([dense, sparse], weights=[1.0, 1.0])
        if not fused:
            await ctx.log("No candidates found in the knowledge base.")
            return {"evidence": []}

        if self.reranker:
            scores = await self.reranker.score(query, [c.text for c in fused])
            reranked = sorted(zip(fused, scores, strict=True), key=lambda x: x[1], reverse=True)
            # Drop clearly irrelevant passages (ms-marco logits < -5 are near-zero relevance).
            fused = [c.model_copy(update={"score": s}) for c, s in reranked if s > -5] or [
                reranked[0][0]
            ]
            await ctx.log(f"Cross-encoder reranked; top score {reranked[0][1]:.2f}")

        evidence = fused[:top_k]
        await ctx.log("Selected: " + ", ".join(
            f"{c.source}{f' p.{c.page}' if c.page else ''}" for c in evidence
        ))
        return {"evidence": evidence}

    @staticmethod
    def summary(update: dict[str, Any]) -> str | None:
        return f"{len(update.get('evidence', []))} passages"
