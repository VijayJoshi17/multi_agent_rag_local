"""Client for the isolated code-execution sandbox service (see /sandbox)."""

from dataclasses import dataclass

import httpx

from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass(slots=True)
class ExecutionResult:
    ok: bool
    output: str
    error: str | None = None
    duration_ms: int = 0


class SandboxClient:
    def __init__(self, base_url: str, timeout_s: float):
        self._client = httpx.AsyncClient(base_url=base_url, timeout=timeout_s + 5)
        self.timeout_s = timeout_s

    async def execute(self, code: str, dataset: str) -> ExecutionResult:
        try:
            resp = await self._client.post(
                "/execute", json={"code": code, "dataset": dataset, "timeout_s": self.timeout_s}
            )
        except httpx.HTTPError as e:
            logger.warning("Sandbox unreachable: %s", e)
            return ExecutionResult(ok=False, output="", error="Sandbox service is unavailable")
        if resp.status_code >= 500:
            return ExecutionResult(ok=False, output="", error=f"Sandbox error {resp.status_code}")
        body = resp.json()
        return ExecutionResult(
            ok=bool(body.get("ok")), output=body.get("output", ""),
            error=body.get("error"), duration_ms=int(body.get("duration_ms", 0)),
        )

    async def ping(self) -> bool:
        try:
            return (await self._client.get("/health")).status_code == 200
        except httpx.HTTPError:
            return False

    async def close(self) -> None:
        await self._client.aclose()
