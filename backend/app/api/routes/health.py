import asyncio

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.deps import get_container
from app.container import Container
from app.schemas.api import HealthOut

router = APIRouter(prefix="/health", tags=["health"])

VERSION = "1.0.0"


@router.get("/live")
async def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready", response_model=HealthOut)
async def ready(c: Container = Depends(get_container)) -> JSONResponse:
    async def db_ok() -> bool:
        try:
            async with c.db.engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return True
        except Exception:  # noqa: BLE001
            return False

    db, store, llm, sandbox = await asyncio.gather(
        db_ok(), c.store.ping(), c.llm.ping(), c.sandbox.ping()
    )
    checks = {"database": db, "vector_store": store, "llm": llm, "sandbox": sandbox}
    # Core = what chat over documents needs. Sandbox only affects data analysis.
    core_ok = db and store
    body = HealthOut(
        status="ok" if all(checks.values()) else "degraded",
        checks=checks, version=VERSION, llm_model=c.settings.LLM_MODEL,
    )
    return JSONResponse(status_code=200 if core_ok else 503, content=body.model_dump())
