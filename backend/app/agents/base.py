import json
import re
from functools import cache
from pathlib import Path
from typing import Any

from app.graph.context import NodeContext
from app.graph.state import GraphState
from app.schemas.rag import Chunk

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


@cache
def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / f"{name}.txt").read_text(encoding="utf-8")


def format_history(history: list[dict[str, str]], turns: int) -> str:
    return "\n".join(f"{m['role']}: {m['content'][:800]}" for m in history[-turns:])


def format_evidence(chunks: list[Chunk], max_chars: int = 1800) -> str:
    blocks = []
    for i, c in enumerate(chunks, 1):
        loc = c.source + (f", page {c.page}" if c.page else "")
        blocks.append(f"[{i}] ({loc})\n{c.text.strip()[:max_chars]}")
    return "\n\n".join(blocks)


_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def parse_json(text: str) -> dict[str, Any]:
    """Lenient JSON extraction from LLM output (handles code fences / chatter)."""
    match = _JSON_RE.search(text)
    if not match:
        return {}
    try:
        data = json.loads(match.group(0))
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


class Agent:
    """An agent is a graph node: reads state, returns a partial state update."""

    name: str = "agent"

    async def __call__(self, state: GraphState, ctx: NodeContext) -> dict[str, Any]:
        raise NotImplementedError

    @staticmethod
    def summary(update: dict[str, Any]) -> str | None:
        """Short human-readable description of the node's result for the UI timeline."""
        return None
