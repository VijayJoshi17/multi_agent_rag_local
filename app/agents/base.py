# ===================== base.py =====================
from abc import ABC, abstractmethod
from typing import Any
from app.models.schemas import AgentState
from app.config import settings
import ollama
import asyncio
import logging

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """
    Base class for all agents.
    Provides a hardened LLM call interface with timeouts and clean failures.
    """

    def __init__(self, name: str):
        self.name = name
        self.model = settings.LLM_MODEL

    @abstractmethod
    async def run(self, state: AgentState) -> AgentState:
        pass

    def log(self, state: AgentState, message: str):
        """Append a message to the state logs with agent name prefix."""
        entry = f"[{self.name}] {message}"
        state.logs.append(entry)
        logger.info(entry)

    async def call_llm(
        self,
        prompt: str,
        system_prompt: str = "You are a helpful assistant.",
        timeout: int = 60,
    ) -> str:
        """
        Safe LLM call wrapper.
        - Enforces timeout
        - Returns clean error messages
        """

        async def _call():
            response = ollama.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
            )
            return response["message"]["content"]

        try:
            return await asyncio.wait_for(_call(), timeout=timeout)
        except asyncio.TimeoutError:
            logger.error("LLM call timed out")
            return "ERROR: LLM_TIMEOUT"
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return f"ERROR: {str(e)}"

