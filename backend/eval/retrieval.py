"""Retrieval evaluation: ablates each stage of the hybrid retriever. No LLM required.

    python -m eval.retrieval           # print table, write eval/results/retrieval-latest.*
    python -m eval.retrieval --check         # also fail (exit 1) if quality drops below thresholds
"""

import argparse
import asyncio
import json
import math
import statistics
import sys
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.agents.retriever import RetrieverAgent
from app.core.config import get_settings
from eval.common import (
    RESULTS_DIR,
    Question,
    build_pipeline,
    eval_settings,
    has_evidence,
    ingest_corpus,
    load_questions,
    temp_dir,
)

CONFIGS: dict[str, dict[str, Any]] = {
    "BM25 only": {"dense": False, "sparse": True, "rerank": False},
    "Dense only": {"dense": True, "sparse": False, "rerank": False},
    "Hybrid (RRF)": {"dense": True, "sparse": True, "rerank": False},
    "Dense + rerank": {"dense": True, "sparse": False, "rerank": True},
    "Hybrid + rerank top-40": {"dense": True, "sparse": True, "rerank": True,
                               "rerank_candidates": 40},
    "Hybrid + rerank top-20": {"dense": True, "sparse": True, "rerank": True,
                               "rerank_candidates": 20},
    "Hybrid + rerank (production)": {"dense": True, "sparse": True, "rerank": True},
}
PRODUCTION = "Hybrid + rerank (production)"
# CI gate for the production configuration.
THRESHOLDS = {"recall@5": 0.90, "mrr": 0.75}
KS = (1, 3, 5)


@dataclass
class QuestionResult:
    id: str
    type: str
    first_hit_rank: int | None
    recall: dict[int, float]
    full_coverage_at_5: bool


def score(q: Question, ranked_texts: list[str]) -> QuestionResult:
    """Each evidence passage is one relevance 'group'. recall@k = share of groups found in top-k."""
    hit_rank: dict[int, int] = {}
    for gi, ev in enumerate(q.evidence):
        for rank, text in enumerate(ranked_texts, 1):
            if has_evidence(text, ev):
                hit_rank[gi] = rank
                break
    groups = len(q.evidence)
    recall = {k: sum(1 for r in hit_rank.values() if r <= k) / groups for k in KS}
    return QuestionResult(
        id=q.id, type=q.type,
        first_hit_rank=min(hit_rank.values()) if hit_rank else None,
        recall=recall, full_coverage_at_5=recall[5] == 1.0,
    )


def ndcg_at_5(r: QuestionResult) -> float:
    return 1 / math.log2(r.first_hit_rank + 1) if r.first_hit_rank and r.first_hit_rank <= 5 else 0


def aggregate(results: list[QuestionResult]) -> dict[str, float]:
    return {
        **{f"recall@{k}": statistics.mean(r.recall[k] for r in results) for k in KS},
        "mrr": statistics.mean(1 / r.first_hit_rank if r.first_hit_rank else 0 for r in results),
        "ndcg@5": statistics.mean(ndcg_at_5(r) for r in results),
        "full@5": statistics.mean(r.full_coverage_at_5 for r in results),
    }


async def run(distractors: bool = True) -> dict:
    all_questions = load_questions()
    questions = [q for q in all_questions if q.answerable]
    with temp_dir() as tmp:
        settings = eval_settings(Path(tmp), RERANKER_ENABLED=True)
        c = await build_pipeline(settings)
        try:
            chunks = await ingest_corpus(c, all_questions, distractors)
            docs = len(list(c.settings.documents_dir.glob('*')))
            retriever = RetrieverAgent(c.embedder, c.store, c.bm25, c.reranker, settings)
            report: dict = {
                "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
                "corpus_chunks": chunks, "corpus_documents": docs,
                "distractors": distractors, "questions": len(questions),
                "embedding_model": settings.EMBEDDING_MODEL,
                "reranker_model": settings.RERANKER_MODEL,
                "chunk_size": settings.CHUNK_SIZE, "configs": {},
            }
            for name, flags in CONFIGS.items():
                results, latencies = [], []
                for q in questions:
                    start = time.perf_counter()
                    ranked, _ = await retriever.retrieve(q.question, top_k=10, **flags)
                    latencies.append((time.perf_counter() - start) * 1000)
                    results.append(score(q, [r.text for r in ranked]))
                by_type = {
                    t: aggregate([r for r in results if r.type == t])
                    for t in sorted({r.type for r in results})
                }
                report["configs"][name] = {
                    "metrics": aggregate(results),
                    "by_type": by_type,
                    "latency_ms_p50": statistics.median(latencies),
                    "misses": [asdict(r) for r in results if not r.full_coverage_at_5],
                }
        finally:
            await c.close()
    return report


def to_markdown(report: dict) -> str:
    lines = [
        "# Retrieval evaluation",
        "",
        f"{report['questions']} answerable questions over {report['corpus_documents']} documents "
        f"/ {report['corpus_chunks']} chunks "
        f"({'8 gold + seeded hard negatives' if report['distractors'] else 'gold only'}, "
        f"chunk size {report['chunk_size']}). Embeddings `{report['embedding_model']}`, "
        f"reranker `{report['reranker_model']}`. Generated {report['generated_at']}.",
        "",
        "| Configuration | Recall@1 | Recall@3 | Recall@5 | MRR | nDCG@5 | All evidence @5 "
        "| p50 latency |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, r in report["configs"].items():
        m = r["metrics"]
        bold = "**" if name == PRODUCTION else ""
        lines.append(
            f"| {bold}{name}{bold} | {m['recall@1']:.2f} | {m['recall@3']:.2f} | "
            f"{m['recall@5']:.2f} | {m['mrr']:.2f} | {m['ndcg@5']:.2f} | {m['full@5']:.2f} | "
            f"{r['latency_ms_p50']:.0f} ms |"
        )
    types = list(next(iter(report["configs"].values()))["by_type"])
    lines += ["", "### MRR by question type", "",
              "| Configuration | " + " | ".join(types) + " |",
              "|---|" + "---:|" * len(types)]
    for name, r in report["configs"].items():
        lines.append(f"| {name} | " + " | ".join(
            f"{r['by_type'][t]['mrr']:.2f}" for t in types) + " |")
    misses = report["configs"][PRODUCTION]["misses"]
    lines += ["", f"### Production misses ({len(misses)})", ""]
    lines += [f"- `{m['id']}` ({m['type']}): first hit at rank {m['first_hit_rank']}, "
              f"recall@5 {m['recall'][5]:.2f}" for m in misses] or ["None."]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if below CI thresholds")
    parser.add_argument("--no-distractors", action="store_true", help="gold corpus only")
    args = parser.parse_args()

    get_settings.cache_clear()
    report = asyncio.run(run(distractors=not args.no_distractors))
    md = to_markdown(report)
    RESULTS_DIR.mkdir(exist_ok=True)
    (RESULTS_DIR / "retrieval-latest.md").write_text(md, encoding="utf-8")
    (RESULTS_DIR / "retrieval-latest.json").write_text(json.dumps(report, indent=2),
                                                       encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    print(md)

    if args.check:
        m = report["configs"][PRODUCTION]["metrics"]
        failed = {k: (m[k], v) for k, v in THRESHOLDS.items() if m[k] < v}
        if failed:
            print("FAILED thresholds:", failed)
            sys.exit(1)
        print("All retrieval thresholds met:", THRESHOLDS)


if __name__ == "__main__":
    main()
