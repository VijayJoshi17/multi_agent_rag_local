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
        self.rerank_candidates = settings.RERANK_CANDIDATES

    async def retrieve(
        self, query: str, top_k: int, *, dense: bool = True, sparse: bool = True,
        rerank: bool = True, rerank_candidates: int | None = None,
    ) -> tuple[list[Chunk], list[str]]:
        """The retrieval pipeline. Flags exist so the evaluation harness can ablate stages."""
        notes: list[str] = []
        lists, weights = [], []
        if dense:
            vec = await self.embedder.embed_query(query)
            lists.append(await self.store.search(vec, limit=self.pool))
            weights.append(1.0)
        if sparse:
            lists.append(await self.bm25.search(query, k=self.pool))
            weights.append(1.0)
        notes.append(" · ".join(
            f"{name}: {len(r)} candidates"
            for name, r in zip([n for n, on in (("Dense", dense), ("BM25", sparse)) if on], lists,
                               strict=True)
        ))
        fused = reciprocal_rank_fusion(lists, weights) if len(lists) > 1 else (lists or [[]])[0]
        if not fused:
            return [], notes

        if rerank and self.reranker:
            # Rerank only the head of the fused list: cross-encoder cost is linear in candidates.
            n = rerank_candidates or self.rerank_candidates
            head = fused[:n]
            scores = await self.reranker.score(query, [c.text for c in head])
            ranked = sorted(zip(head, scores, strict=True), key=lambda x: x[1], reverse=True)
            # No absolute score cut-off: cross-encoder logits are not calibrated across query
            # styles (paraphrases score low even when relevant). Keep the top-k; the reasoner
            # is instructed to say so when the passages don't answer the question.
            fused = [c.model_copy(update={"score": s}) for c, s in ranked]
            notes.append(f"Cross-encoder reranked {len(head)}; top score {ranked[0][1]:.2f}")
        return fused[:top_k], notes

    async def __call__(self, state: GraphState, ctx: NodeContext) -> dict[str, Any]:
        evidence, notes = await self.retrieve(state["query"], state.get("top_k", 5))
        for note in notes:
            await ctx.log(note)
        if not evidence:
            await ctx.log("No candidates found in the knowledge base.")
            return {"evidence": []}
        await ctx.log("Selected: " + ", ".join(
            f"{c.source}{f' p.{c.page}' if c.page else ''}" for c in evidence
        ))
        return {"evidence": evidence}

    @staticmethod
    def summary(update: dict[str, Any]) -> str | None:
        return f"{len(update.get('evidence', []))} passages"
