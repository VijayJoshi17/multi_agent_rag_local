# ===================== summarizer.py =====================
from app.agents.base import BaseAgent
from app.models.schemas import AgentState
from app.utils.logger import setup_logger
import os

logger = setup_logger(__name__)


class SummarizerAgent(BaseAgent):
    """
    Condenses retrieved documents into a factual, query-focused summary.
    """

    def __init__(self):
        super().__init__(name="Summarizer")

    def _read_prompt(self) -> str:
        prompt_path = os.path.join(os.path.dirname(__file__), "../prompts/summarizer.txt")
        with open(prompt_path, "r", encoding="utf-8") as f:
            return f.read()

    async def run(self, state: AgentState) -> AgentState:
        logger.info("SummarizerAgent: generating summary")

        if not state.retrieved_docs:
            state.summary = "INSUFFICIENT CONTEXT"
            return state

        context = "\n\n".join(
            f"[SOURCE {i+1}] {doc.content}" for i, doc in enumerate(state.retrieved_docs)
        )

        prompt = f"""
USER QUESTION:
{state.query}

RETRIEVED CONTENT:
{context}

SUMMARY:
"""

        summary = await self.call_llm(prompt, system_prompt=self._read_prompt())
        state.summary = summary.strip()

        logger.info("SummarizerAgent: summary created")
        return state
