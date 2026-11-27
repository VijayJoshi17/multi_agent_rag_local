"""Sandbox HTTP service. Spawns one resource-limited subprocess per execution."""

import asyncio
import json
import os
import re
import sys
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

DATASETS_DIR = Path(os.environ.get("DATASETS_DIR", "/data/datasets")).resolve()
MAX_CONCURRENCY = int(os.environ.get("SANDBOX_CONCURRENCY", "2"))
MEMORY_LIMIT_MB = int(os.environ.get("SANDBOX_MEMORY_MB", "1024"))
MAX_TIMEOUT_S = float(os.environ.get("SANDBOX_MAX_TIMEOUT_S", "60"))
RUNNER = Path(__file__).with_name("runner.py")
_NAME_RE = re.compile(r"^[a-f0-9]{32}\.(csv|xlsx)$")

app = FastAPI(title="Analysis Sandbox", docs_url=None, redoc_url=None)
_slots = asyncio.Semaphore(MAX_CONCURRENCY)


class ExecuteRequest(BaseModel):
    code: str = Field(max_length=20_000)
    dataset: str
    timeout_s: float = Field(default=30, gt=0)


class ExecuteResponse(BaseModel):
    ok: bool
    output: str = ""
    error: str | None = None
    duration_ms: int = 0


def _limits(cpu_s: int):  # noqa: ANN202
    """preexec_fn for POSIX: cap CPU time, address space, file writes and open files."""

    def apply() -> None:
        import resource

        mem = MEMORY_LIMIT_MB * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_s, cpu_s + 1))
        resource.setrlimit(resource.RLIMIT_AS, (mem, mem))
        resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
        resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
        os.setsid()

    return apply


def _child_env() -> dict[str, str]:
    """Minimal environment for the child: no secrets or proxies inherited."""
    env = {"PATH": "/usr/bin:/bin", "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1",
           "PYTHONDONTWRITEBYTECODE": "1"}
    if "SYSTEMROOT" in os.environ:  # required for Python to start on Windows (local dev)
        env["SYSTEMROOT"] = os.environ["SYSTEMROOT"]
    return env


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/execute", response_model=ExecuteResponse)
async def execute(req: ExecuteRequest) -> ExecuteResponse:
    if not _NAME_RE.match(req.dataset):
        raise HTTPException(400, "Invalid dataset name")
    path = (DATASETS_DIR / req.dataset).resolve()
    if path.parent != DATASETS_DIR or not path.is_file():
        raise HTTPException(404, "Dataset not found")

    timeout = min(req.timeout_s, MAX_TIMEOUT_S)
    payload = json.dumps({"code": req.code, "dataset_path": str(path)}).encode()
    async with _slots:
        start = time.perf_counter()
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-I", str(RUNNER),
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=_child_env(),
            preexec_fn=_limits(int(timeout) + 1) if os.name == "posix" else None,
        )
        try:
            out, err = await asyncio.wait_for(proc.communicate(payload), timeout=timeout)
        except TimeoutError:
            proc.kill()
            await proc.wait()
            return ExecuteResponse(ok=False, error=f"Execution timed out after {timeout:.0f}s")
        elapsed = int((time.perf_counter() - start) * 1000)

    if proc.returncode != 0 and not out:
        msg = err.decode(errors="replace").strip().splitlines()[-1:] or ["process crashed"]
        return ExecuteResponse(ok=False, error=f"Sandbox process failed: {msg[0][:500]}",
                               duration_ms=elapsed)
    try:
        body = json.loads(out)
    except json.JSONDecodeError:
        return ExecuteResponse(ok=False, error="Sandbox produced invalid output",
                               duration_ms=elapsed)
    return ExecuteResponse(**body, duration_ms=elapsed)
