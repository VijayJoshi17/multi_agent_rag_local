from typing import Any

from app.agents.base import Agent, format_history, load_prompt
from app.graph.context import NodeContext
from app.graph.state import GraphState
from app.services.llm import LLMClient


class ContextualizerAgent(Agent):
    """Rewrites a follow-up question into a standalone query using chat history."""

    name = "contextualize"

    def __init__(self, llm: LLMClient, history_turns: int):
        self.llm = llm
        self.history_turns = history_turns

    async def __call__(self, state: GraphState, ctx: NodeContext) -> dict[str, Any]:
        question = state["question"]
        history = state.get("history") or []
        if not history:
            await ctx.log("No history — query is already standalone.")
            return {"query": question}

        prompt = (
            f"CHAT HISTORY:\n{format_history(history, self.history_turns)}\n\n"
            f"LATEST USER QUESTION:\n{question}\n\nSTANDALONE QUESTION:"
        )
        raw = await self.llm.complete(prompt, system=load_prompt("contextualizer"))
        rewritten = raw.strip().strip('"')
        # Guard against the model answering instead of rewriting.
        if not rewritten or len(rewritten) > max(400, len(question) * 4):
            rewritten = question
        if rewritten != question:
            await ctx.log(f"Rewrote query → “{rewritten}”")
        return {"query": rewritten}

    @staticmethod
    def summary(update: dict[str, Any]) -> str | None:
        return f"Query: {update.get('query', '')[:120]}"
