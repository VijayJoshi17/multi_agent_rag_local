import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from qdrant_client import AsyncQdrantClient

from app.container import Container
from app.core.config import Settings
from app.main import create_app
from app.services.vector_store import VectorStore
from tests.fakes import FakeEmbedder, FakeLLM, FakeSandbox


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        ENVIRONMENT="test",
        DATA_DIR=tmp_path,
        DATABASE_URL=f"sqlite+aiosqlite:///{tmp_path / 'test.db'}",
        RERANKER_ENABLED=False,
        RATE_LIMIT_CHAT="1000/minute",
        RATE_LIMIT_UPLOAD="1000/minute",
    )


@pytest.fixture
def llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
def sandbox() -> FakeSandbox:
    return FakeSandbox()


@pytest.fixture
async def client(settings: Settings, llm: FakeLLM, sandbox: FakeSandbox) -> AsyncIterator[Any]:
    embedder = FakeEmbedder()

    async def factory(s: Settings) -> Container:
        store = VectorStore(AsyncQdrantClient(location=":memory:"), "test", embedder.dimension)
        return await Container.build(s, llm=llm, embedder=embedder, store=store,
                                     sandbox=sandbox)  # type: ignore[arg-type]

    app = create_app(settings, container_factory=factory)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            c.app = app  # type: ignore[attr-defined]
            yield c


def parse_sse(body: str) -> list[dict[str, Any]]:
    events = []
    for block in body.strip().split("\n\n"):
        for line in block.splitlines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    return events


async def ask(client: Any, message: str, **kwargs: Any) -> list[dict[str, Any]]:
    resp = await client.post("/api/v1/chat/stream", json={"message": message, **kwargs})
    assert resp.status_code == 200, resp.text
    return parse_sse(resp.text)


async def upload_text(client: Any, name: str, text: str) -> dict[str, Any]:
    resp = await client.post(
        "/api/v1/documents", files=[("files", (name, text.encode(), "text/plain"))]
    )
    assert resp.status_code == 202, resp.text
    await client.app.state.container.ingestion.wait_idle()
    return resp.json()
