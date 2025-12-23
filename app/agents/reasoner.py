# ===================== reasoner.py =====================
from app.agents.base import BaseAgent
from app.models.schemas import AgentState
from app.utils.logger import setup_logger
import os

logger = setup_logger(__name__)


class ReasonerAgent(BaseAgent):
    """
    Produces the final user-facing answer strictly from summarized or retrieved context.
    Hallucination-intolerant by design.
    """

    def __init__(self):
        super().__init__(name="Reasoner")

    def _read_prompt(self) -> str:
        prompt_path = os.path.join(os.path.dirname(__file__), "../prompts/reasoner.txt")
        with open(prompt_path, "r", encoding="utf-8") as f:
            return f.read()

    async def run(self, state: AgentState) -> AgentState:
        logger.info("ReasonerAgent: generating final answer")

        system_prompt = self._read_prompt()

        # Prefer summarized context (lower noise, fewer tokens)
        if state.summary:
            context_block = f"CONTEXT SUMMARY:\n{state.summary}"
        else:
            docs = state.retrieved_docs or []
            context_block = "\n\n".join(
                f"[SOURCE {i+1}]\n{doc.content}" for i, doc in enumerate(docs[:3])
            ) or "NO CONTEXT"

        prompt = f"""
USER QUESTION:
{state.query}

{context_block}

FINAL ANSWER:
"""

        answer = await self.call_llm(prompt, system_prompt=system_prompt)
        answer = answer.strip()

        state.generated_answer = answer
        state.reasoning_trace.append("Answer generated using grounded context")

        logger.info("ReasonerAgent: answer generated")
        return state
