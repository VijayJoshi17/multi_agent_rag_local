"""Provider-agnostic async LLM client.

Any OpenAI-compatible endpoint works: OpenRouter (default), Ollama (`http://host:11434/v1`),
vLLM, LM Studio, OpenAI itself, etc. Swapping providers is a config change only.
"""

import time
from collections.abc import AsyncIterator
from typing import Protocol

from openai import APIError, APITimeoutError, AsyncOpenAI

from app.core.config import Settings
from app.core.errors import UpstreamError
from app.core.logging import get_logger
from app.services.metrics import LLM_LATENCY

logger = get_logger(__name__)


class LLMClient(Protocol):
    model: str

    async def complete(
        self, prompt: str, *, system: str = "", temperature: float | None = None,
        max_tokens: int | None = None, json_mode: bool = False,
    ) -> str: ...

    def stream(
        self, prompt: str, *, system: str = "", temperature: float | None = None,
    ) -> AsyncIterator[str]: ...

    async def ping(self) -> bool: ...


class OpenAICompatibleLLM:
    def __init__(self, settings: Settings):
        self.model = settings.LLM_MODEL
        self.temperature = settings.LLM_TEMPERATURE
        api_key = settings.LLM_API_KEY.get_secret_value() or "not-needed"
        self._client = AsyncOpenAI(
            base_url=settings.LLM_BASE_URL,
            api_key=api_key,
            timeout=settings.LLM_TIMEOUT_S,
            max_retries=settings.LLM_MAX_RETRIES,
            # OpenRouter uses these for attribution/rankings; harmless elsewhere.
            default_headers={"X-Title": settings.APP_NAME},
        )

    @staticmethod
    def _messages(prompt: str, system: str) -> list[dict[str, str]]:
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.append({"role": "user", "content": prompt})
        return msgs

    async def complete(
        self, prompt: str, *, system: str = "", temperature: float | None = None,
        max_tokens: int | None = None, json_mode: bool = False,
    ) -> str:
        start = time.perf_counter()
        kwargs: dict = {}
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        try:
            resp = await self._client.chat.completions.create(
                model=self.model,
                messages=self._messages(prompt, system),  # type: ignore[arg-type]
                temperature=self.temperature if temperature is None else temperature,
                max_tokens=max_tokens,
                **kwargs,
            )
        except APITimeoutError as e:
            raise UpstreamError("LLM request timed out") from e
        except APIError as e:
            if json_mode and getattr(e, "status_code", None) == 400:
                # Some models/providers reject response_format; retry without it.
                return await self.complete(prompt, system=system, temperature=temperature,
                                           max_tokens=max_tokens, json_mode=False)
            logger.warning("LLM API error: %s", e)
            raise UpstreamError(f"LLM provider error: {e.message}") from e
        finally:
            LLM_LATENCY.labels(mode="complete").observe(time.perf_counter() - start)

        if not resp.choices:
            raise UpstreamError("LLM returned no choices")
        return (resp.choices[0].message.content or "").strip()

    async def stream(
        self, prompt: str, *, system: str = "", temperature: float | None = None,
    ) -> AsyncIterator[str]:
        start = time.perf_counter()
        try:
            stream = await self._client.chat.completions.create(
                model=self.model,
                messages=self._messages(prompt, system),  # type: ignore[arg-type]
                temperature=self.temperature if temperature is None else temperature,
                stream=True,
            )
            async for chunk in stream:
                if chunk.choices and (delta := chunk.choices[0].delta.content):
                    yield delta
        except APITimeoutError as e:
            raise UpstreamError("LLM request timed out") from e
        except APIError as e:
            raise UpstreamError(f"LLM provider error: {e.message}") from e
        finally:
            LLM_LATENCY.labels(mode="stream").observe(time.perf_counter() - start)

    async def ping(self) -> bool:
        try:
            await self._client.models.list()
            return True
        except Exception:  # noqa: BLE001
            return False
