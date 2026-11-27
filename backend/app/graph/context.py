"""Per-node execution context: lets agents emit logs and tokens to the client stream."""

from collections.abc import Awaitable, Callable
from typing import Any

from app.core.logging import get_logger

Emit = Callable[[dict[str, Any]], Awaitable[None]]

logger = get_logger("agents")


class NodeContext:
    def __init__(self, node: str, emit: Emit):
        self.node = node
        self._emit = emit

    async def log(self, message: str) -> None:
        logger.info("[%s] %s", self.node, message)
        await self._emit({"type": "log", "node": self.node, "message": message})

    async def token(self, text: str) -> None:
        await self._emit({"type": "token", "text": text})

    async def event(self, payload: dict[str, Any]) -> None:
        await self._emit(payload)


async def _noop(_: dict[str, Any]) -> None:
    return None


def null_context(node: str = "test") -> NodeContext:
    return NodeContext(node, _noop)
