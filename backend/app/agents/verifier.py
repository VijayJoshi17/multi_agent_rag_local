import re
from typing import Any

from app.agents.base import Agent, format_evidence, load_prompt, parse_json
from app.graph.context import NodeContext
from app.graph.state import GraphState, Verification
from app.services.llm import LLMClient
from app.services.metrics import VERIFICATION_COUNTER

_FALLBACK_RE = re.compile(r"\b(UNSUPPORTED|SUPPORTED|INACCURATE|ACCURATE)\b", re.I)


def parse_verdict(raw: str) -> Verification:
    data = parse_json(raw)
    verdict = str(data.get("verdict", "")).lower()
    reason = str(data.get("reason", "")).strip()
    if verdict not in {"supported", "unsupported"}:
        m = _FALLBACK_RE.search(raw)
        word = m.group(1).upper() if m else ""
        verdict = "supported" if word in {"SUPPORTED", "ACCURATE"} else "unsupported"
        reason = reason or raw.strip()[:300] or "Verifier returned an unparseable response."
    return {"verdict": verdict, "reason": reason}  # type: ignore[typeddict-item]


class VerifierAgent(Agent):
    """LLM-as-judge groundedness check: is every claim in the answer backed by the sources?"""

    name = "verify"

    def __init__(self, llm: LLMClient):
        self.llm = llm

    async def __call__(self, state: GraphState, ctx: NodeContext) -> dict[str, Any]:
        prompt = (
            f"SOURCES:\n{format_evidence(state.get('evidence') or [])}\n\n"
            f"QUESTION:\n{state['query']}\n\nANSWER TO CHECK:\n{state.get('answer', '')}"
        )
        raw = await self.llm.complete(prompt, system=load_prompt("verifier"), json_mode=True,
                                      max_tokens=250, temperature=0)
        verification = parse_verdict(raw)
        VERIFICATION_COUNTER.labels(verdict=verification["verdict"]).inc()
        await ctx.log(f"Verdict: {verification['verdict']} — {verification['reason']}")
        return {"verification": verification}

    @staticmethod
    def summary(update: dict[str, Any]) -> str | None:
        v = update.get("verification") or {}
        return f"Verdict: {v.get('verdict', '?')}"
