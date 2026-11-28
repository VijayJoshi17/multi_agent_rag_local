"""End-to-end answer evaluation: runs every question through the full agent graph with a real LLM.

Reads LLM_* settings from backend/.env (or the environment), exactly like the app.

    python -m eval.answers                       # all questions
    python -m eval.answers --limit 5 --delay 3   # quick smoke run, gentle on free-tier rate limits
    python -m eval.answers --judge-model openai/gpt-4o-mini   # grade with a different model

Metrics
- accuracy (judge):      LLM judge says the answer matches the reference
- accuracy (keywords):   every required fact string appears in the answer (deterministic)
- citation rate:         answer contains at least one [n] citation
- refusal rate:          unanswerable questions correctly declined (judge), i.e. 1 - hallucination
- verifier agreement:    verifier verdict == judge verdict on answerable questions
- LLM calls / question, latency p50/p95
"""

import argparse
import asyncio
import json
import re
import statistics
import sys
import time
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.agents.base import parse_json
from app.core.config import Settings, get_settings
from app.core.errors import UpstreamError
from app.schemas.api import ChatRequest
from app.services.llm import LLMClient, OpenAICompatibleLLM
from eval.common import (
    RESULTS_DIR,
    Question,
    build_pipeline,
    contains_any,
    eval_settings,
    ingest_corpus,
    load_questions,
    temp_dir,
)

JUDGE_PROMPT = """You grade answers produced by a retrieval-augmented assistant.

You get a QUESTION, a REFERENCE answer written by a human, and a CANDIDATE answer.

- If the REFERENCE is a fact: the candidate is correct when it states the key facts of the reference
  and does not contradict it. Extra correct detail, different wording, citations like [1] and
  formatting do not matter. A candidate that says the information is unavailable is incorrect.
- If the REFERENCE is UNANSWERABLE: the documents do not contain the answer. The candidate is
  correct only if it clearly says the information is not available and does NOT state a specific
  answer as fact.

Respond with JSON only: {"correct": true | false, "reason": "<one short sentence>"}"""

CITATION_RE = re.compile(r"\[\d{1,2}\]")


class CountingLLM:
    """Wraps the real client to count calls per question."""

    def __init__(self, inner: LLMClient):
        self.inner = inner
        self.model = inner.model
        self.calls = 0

    async def complete(self, prompt: str, **kw: Any) -> str:
        self.calls += 1
        return await self.inner.complete(prompt, **kw)

    async def stream(self, prompt: str, **kw: Any) -> AsyncIterator[str]:
        self.calls += 1
        async for t in self.inner.stream(prompt, **kw):
            yield t

    async def ping(self) -> bool:
        return await self.inner.ping()


async def judge(llm: LLMClient, q: Question, answer: str) -> tuple[bool, str]:
    prompt = f"QUESTION:\n{q.question}\n\nREFERENCE:\n{q.reference}\n\nCANDIDATE:\n{answer}"
    for attempt in range(3):
        try:
            raw = await llm.complete(prompt, system=JUDGE_PROMPT, json_mode=True,
                                     temperature=0)
            data = parse_json(raw)
            if isinstance(data.get("correct"), bool):
                return data["correct"], str(data.get("reason", ""))
        except UpstreamError:
            await asyncio.sleep(5 * (attempt + 1))
    return False, "judge failed to return a verdict"


async def ask(c: Any, q: Question, mode: str, verify: bool) -> dict[str, Any]:
    req = ChatRequest(message=q.question, mode=mode, verify=verify, top_k=5)  # type: ignore[arg-type]
    final, error = None, None
    async for event in c.chat.stream(req):
        if event["type"] == "final":
            final = event["message"]
        elif event["type"] == "error":
            error = event["message"]
    return {"final": final, "error": error}


def results_path(args: argparse.Namespace, model: str, ext: str) -> Path:
    slug = args.name or re.sub(r"[^a-z0-9.]+", "-", model.lower()).strip("-")
    return RESULTS_DIR / f"answers-{slug}.{ext}"


async def run(args: argparse.Namespace) -> dict[str, Any]:
    questions = load_questions()
    base = get_settings()
    order = {q.id: i for i, q in enumerate(questions)}
    rows: list[dict[str, Any]] = []
    prev = results_path(args, base.LLM_MODEL, "json")
    if args.resume and prev.exists():
        # Keep answered questions; retry only the ones that are missing or errored.
        rows = [r for r in json.loads(prev.read_text(encoding="utf-8"))["rows"] if not r["error"]]
        print(f"Resuming: {len(rows)} answered, running the rest", flush=True)
    done = {r["id"] for r in rows}
    selected = [q for q in questions if (not args.ids or q.id in args.ids) and q.id not in done]
    selected = selected[: args.limit or None]
    real_llm = OpenAICompatibleLLM(base)
    llm = CountingLLM(real_llm)
    judge_llm: LLMClient = real_llm
    if args.judge_model:
        judge_llm = OpenAICompatibleLLM(base.model_copy(update={"LLM_MODEL": args.judge_model}))

    with temp_dir() as tmp:
        settings: Settings = eval_settings(Path(tmp), base, RERANKER_ENABLED=True)
        c = await build_pipeline(settings, llm=llm)  # type: ignore[arg-type]
        try:
            chunks = await ingest_corpus(c, questions, distractors=not args.no_distractors)
            for i, q in enumerate(selected, 1):
                llm.calls = 0
                start = time.perf_counter()
                result = await ask(c, q, args.mode, not args.no_verify)
                if result["error"] and "rate" in result["error"].lower():
                    await asyncio.sleep(20)
                    llm.calls = 0
                    start = time.perf_counter()
                    result = await ask(c, q, args.mode, not args.no_verify)
                if result["error"] and "per-day" in result["error"]:
                    print(f"Daily request limit reached at {q.id}; stopping. "
                          "Re-run with --resume to continue.", flush=True)
                    break
                elapsed = time.perf_counter() - start
                final = result["final"] or {}
                answer = final.get("content", "")
                meta = final.get("meta", {})
                correct, reason = (
                    await judge(judge_llm, q, answer) if answer else (False, "no answer")
                )
                row = {
                    "id": q.id, "type": q.type, "question": q.question, "answer": answer,
                    "error": result["error"],
                    "judge_correct": correct, "judge_reason": reason,
                    "keyword_correct": bool(q.must_include) and all(
                        contains_any(answer, k) for k in q.must_include),
                    "cited": bool(CITATION_RE.search(answer)),
                    "verdict": (meta.get("verification") or {}).get("verdict", "none"),
                    "attempts": meta.get("attempts", 0),
                    "route": meta.get("route"),
                    "llm_calls": llm.calls,
                    "latency_s": round(elapsed, 2),
                }
                rows.append(row)
                mark = "✓" if correct else "✗"
                print(f"[{i:>2}/{len(selected)}] {mark} {q.id:<4} {elapsed:5.1f}s "
                      f"calls={llm.calls} verdict={row['verdict']:<11} {answer[:70]!r}",
                      flush=True)
                if args.delay:
                    await asyncio.sleep(args.delay)
        finally:
            await c.close()

    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "model": base.LLM_MODEL, "judge_model": args.judge_model or base.LLM_MODEL,
        "provider": base.LLM_BASE_URL, "mode": args.mode, "verify": not args.no_verify,
        "distractors": not args.no_distractors, "corpus_chunks": chunks,
        "summary": summarize(rows), "rows": sorted(rows, key=lambda r: order[r["id"]]),
    }


def _rate(rows: list[dict[str, Any]], key: str) -> float | None:
    return statistics.mean(bool(r[key]) for r in rows) if rows else None


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    answerable = [r for r in rows if r["type"] != "unanswerable"]
    unanswerable = [r for r in rows if r["type"] == "unanswerable"]
    verified = [r for r in answerable if r["verdict"] in ("supported", "unsupported")]
    latencies = sorted(r["latency_s"] for r in rows)
    by_type = {
        t: _rate([r for r in rows if r["type"] == t], "judge_correct")
        for t in sorted({r["type"] for r in rows})
    }
    return {
        "questions": len(rows),
        "accuracy_judge": _rate(answerable, "judge_correct"),
        "accuracy_keywords": _rate(answerable, "keyword_correct"),
        "citation_rate": _rate(answerable, "cited"),
        "refusal_rate": _rate(unanswerable, "judge_correct"),
        "verifier_agreement": statistics.mean(
            (r["verdict"] == "supported") == r["judge_correct"] for r in verified
        ) if verified else None,
        "regeneration_rate": statistics.mean(r["attempts"] > 1 for r in rows) if rows else None,
        "errors": sum(1 for r in rows if r["error"]),
        "llm_calls_mean": statistics.mean(r["llm_calls"] for r in rows) if rows else None,
        "latency_p50_s": statistics.median(latencies) if latencies else None,
        "latency_p95_s": latencies[min(len(latencies) - 1, int(0.95 * len(latencies)))]
        if latencies else None,
        "accuracy_by_type": by_type,
    }


def _pct(v: float | None) -> str:
    return "n/a" if v is None else f"{v:.0%}"


def to_markdown(report: dict[str, Any]) -> str:
    s = report["summary"]
    lines = [
        f"# Answer evaluation — `{report['model']}`",
        "",
        f"{s['questions']} questions, mode `{report['mode']}`, verification "
        f"{'on' if report['verify'] else 'off'}, {report['corpus_chunks']} chunks"
        f"{' incl. hard negatives' if report['distractors'] else ''}. "
        f"Judge: `{report['judge_model']}`. Generated {report['generated_at']}.",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Answer accuracy (LLM judge) | {_pct(s['accuracy_judge'])} |",
        f"| Answer accuracy (required facts present) | {_pct(s['accuracy_keywords'])} |",
        f"| Answers with citations | {_pct(s['citation_rate'])} |",
        f"| Unanswerable questions correctly declined | {_pct(s['refusal_rate'])} |",
        f"| Verifier agrees with judge | {_pct(s['verifier_agreement'])} |",
        f"| Answers regenerated after verifier rejection | {_pct(s['regeneration_rate'])} |",
        f"| LLM calls per question (mean) | {s['llm_calls_mean']:.1f} |"
        if s["llm_calls_mean"] is not None else "| LLM calls per question | n/a |",
        f"| Latency p50 / p95 | {s['latency_p50_s']:.1f} s / {s['latency_p95_s']:.1f} s |"
        if s["latency_p50_s"] is not None else "| Latency | n/a |",
        f"| Errors | {s['errors']} |",
        "",
        "### Accuracy by question type",
        "",
        "| Type | Accuracy |",
        "|---|---:|",
        *[f"| {t} | {_pct(v)} |" for t, v in s["accuracy_by_type"].items()],
        "",
        "### Failures",
        "",
    ]
    fails = [r for r in report["rows"] if not r["judge_correct"]]
    for r in fails:
        lines.append(f"- **{r['id']}** ({r['type']}) — {r['question']}  ")
        lines.append(f"  answer: {r['answer'][:300].replace(chr(10), ' ')!s}  ")
        lines.append(f"  judge: {r['judge_reason']} · verifier: {r['verdict']}")
    if not fails:
        lines.append("None.")
    return "\n".join(lines) + "\n"


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--ids", nargs="*", default=[])
    p.add_argument("--delay", type=float, default=0, help="seconds between questions")
    p.add_argument("--mode", default="documents", choices=["documents", "auto"])
    p.add_argument("--no-verify", action="store_true")
    p.add_argument("--no-distractors", action="store_true")
    p.add_argument("--judge-model", default="")
    p.add_argument("--name", default="", help="results file suffix (default: model name)")
    p.add_argument("--resume", action="store_true",
                   help="keep answered questions from the last run, run only the rest")
    args = p.parse_args()

    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    report = asyncio.run(run(args))
    RESULTS_DIR.mkdir(exist_ok=True)
    results_path(args, report["model"], "json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    md = to_markdown(report)
    results_path(args, report["model"], "md").write_text(md, encoding="utf-8")
    print("\n" + md)


if __name__ == "__main__":
    main()
