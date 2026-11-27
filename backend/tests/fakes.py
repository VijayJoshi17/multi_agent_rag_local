"""Deterministic test doubles for the LLM, embedder and sandbox."""

import hashlib
import math
import re
from collections import defaultdict
from collections.abc import AsyncIterator

from app.agents.base import load_prompt
from app.services.sandbox import ExecutionResult

PROMPT_NAMES = ["contextualizer", "router", "web_plan", "data_analyst", "reasoner", "verifier"]


class FakeLLM:
    """Replies are scripted per agent prompt. A list value is consumed one item per call."""

    model = "fake-model"

    def __init__(self, replies: dict[str, str | list[str]] | None = None):
        self.replies: dict[str, str | list[str]] = {
            "contextualizer": "standalone question",
            "router": "internal",
            "web_plan": '{"search_query": "q", "ticker": null}',
            "data_analyst": "```python\nresult = len(df)\n```",
            "reasoner": "Paris is the capital of France [1].",
            "verifier": '{"verdict": "supported", "reason": "ok"}',
        }
        self.replies.update(replies or {})
        self.calls: dict[str, int] = defaultdict(int)

    def _name(self, system: str) -> str:
        for name in PROMPT_NAMES:
            if system == load_prompt(name):
                return name
        return "unknown"

    def _reply(self, system: str) -> str:
        name = self._name(system)
        self.calls[name] += 1
        value = self.replies.get(name, "")
        if isinstance(value, list):
            return value.pop(0) if len(value) > 1 else value[0]
        return value

    async def complete(self, prompt: str, *, system: str = "", temperature=None,
                       max_tokens=None, json_mode: bool = False) -> str:
        return self._reply(system)

    async def stream(self, prompt: str, *, system: str = "",
                     temperature=None) -> AsyncIterator[str]:
        text = self._reply(system)
        for word in re.findall(r"\S+\s*", text):
            yield word

    async def ping(self) -> bool:
        return True


class FakeEmbedder:
    """Bag-of-words hashing embedder: similar wording → similar vectors."""

    dimension = 64

    def _vec(self, text: str) -> list[float]:
        v = [0.0] * self.dimension
        for tok in re.findall(r"\w+", text.lower()):
            v[int(hashlib.md5(tok.encode()).hexdigest(), 16) % self.dimension] += 1.0
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / norm for x in v]

    async def embed_query(self, text: str) -> list[float]:
        return self._vec(text)

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]


class FakeSandbox:
    def __init__(self, results: list[ExecutionResult] | None = None):
        self.results = results or [ExecutionResult(ok=True, output="42", duration_ms=5)]
        self.calls: list[tuple[str, str]] = []

    async def execute(self, code: str, dataset: str) -> ExecutionResult:
        self.calls.append((code, dataset))
        return self.results.pop(0) if len(self.results) > 1 else self.results[0]

    async def ping(self) -> bool:
        return True

    async def close(self) -> None:
        return None
