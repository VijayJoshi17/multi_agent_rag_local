from typing import Any

from app.agents.base import Agent, format_evidence, format_history, load_prompt
from app.graph.context import NodeContext
from app.graph.state import GraphState
from app.services.llm import LLMClient

# The reasoner prompt asks for this exact opening when the sources lack the answer. The graph
# uses it to skip verification: a refusal makes no factual claims to check.
NOT_FOUND_PREFIX = "I couldn't find this in the available sources."

NO_EVIDENCE_ANSWER = (
    f"{NOT_FOUND_PREFIX} Try uploading related documents, rephrasing the question, "
    "or switching to web search mode."
)


def is_refusal(answer: str) -> bool:
    return answer.lstrip().lower().startswith(NOT_FOUND_PREFIX.lower().rstrip("."))


class ReasonerAgent(Agent):
    """Writes the grounded, cited, Markdown-formatted answer and streams it token by token."""

    name = "reason"

    def __init__(self, llm: LLMClient):
        self.llm = llm

    async def __call__(self, state: GraphState, ctx: NodeContext) -> dict[str, Any]:
        evidence = state.get("evidence") or []
        attempts = state.get("attempts", 0) + 1

        if attempts > 1:
            await ctx.event({"type": "answer_reset", "reason": "verification_failed"})
            await ctx.log("Regenerating answer using verifier feedback.")

        if not evidence or all(c.kind == "system" for c in evidence):
            text = evidence[0].text if evidence else NO_EVIDENCE_ANSWER
            await ctx.token(text)
            return {"answer": text, "attempts": attempts}

        parts = [f"SOURCES:\n{format_evidence(evidence)}"]
        if history := state.get("history"):
            parts.append(f"CONVERSATION SO FAR:\n{format_history(history, 4)}")
        parts.append(f"QUESTION:\n{state['query']}")
        if attempts > 1 and (v := state.get("verification")):
            parts.append(
                "A fact-checker rejected your previous answer for this reason:\n"
                f"{v['reason']}\nWrite a corrected answer that only states supported facts."
            )

        chunks: list[str] = []
        async for token in self.llm.stream("\n\n".join(parts), system=load_prompt("reasoner")):
            chunks.append(token)
            await ctx.token(token)
        answer = "".join(chunks).strip()
        await ctx.log(f"Drafted answer ({len(answer)} chars, attempt {attempts}).")
        return {"answer": answer, "attempts": attempts}

    @staticmethod
    def summary(update: dict[str, Any]) -> str | None:
        return f"Answer drafted (attempt {update.get('attempts', 1)})"
