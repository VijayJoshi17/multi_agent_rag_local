import io
import zipfile

from app.core.config import Settings
from app.main import create_app
from app.services.sandbox import ExecutionResult
from tests.conftest import ask, upload_text

FRANCE = (
    "France is a country in Western Europe. Its capital and largest city is Paris. "
    "The Eiffel Tower in Paris was completed in 1889."
)


async def test_health(client):
    resp = await client.get("/api/v1/health/ready")
    assert resp.status_code == 200
    assert resp.json()["checks"]["database"] is True


async def test_upload_and_list_documents(client):
    body = await upload_text(client, "france.txt", FRANCE)
    assert body["documents"][0]["filename"] == "france.txt"

    docs = (await client.get("/api/v1/documents")).json()
    assert docs[0]["status"] == "ready"
    assert docs[0]["chunk_count"] >= 1

    stats = (await client.get("/api/v1/knowledge-base/stats")).json()
    assert stats == {"documents": 1, "chunks": docs[0]["chunk_count"]}


async def test_duplicate_upload_is_skipped(client):
    await upload_text(client, "france.txt", FRANCE)
    body = await upload_text(client, "copy.txt", FRANCE)
    assert body["documents"] == []
    assert "duplicate" in body["skipped"][0]


async def test_rejects_spoofed_pdf(client):
    resp = await client.post(
        "/api/v1/documents", files=[("files", ("evil.pdf", b"not a pdf", "application/pdf"))]
    )
    assert resp.status_code == 415
    assert resp.json()["error"]["code"] == "unsupported_file"


async def test_zip_upload_skips_traversal(client):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("docs/a.txt", "Alpha document about apples.")
        zf.writestr("../escape.txt", "should be skipped")
        zf.writestr("image.png", "nope")
    resp = await client.post(
        "/api/v1/documents", files=[("files", ("bundle.zip", buf.getvalue(), "application/zip"))]
    )
    body = resp.json()
    assert [d["filename"] for d in body["documents"]] == ["bundle.zip/docs/a.txt"]
    assert set(body["skipped"]) == {"../escape.txt", "image.png"}


async def test_chat_over_documents_streams_and_persists(client, llm):
    await upload_text(client, "france.txt", FRANCE)
    events = await ask(client, "What is the capital of France?", mode="documents")
    types = [e["type"] for e in events]

    assert types[0] == "start"
    assert types[-1] == "final"
    assert "token" in types
    started = [e["node"] for e in events if e["type"] == "node_start"]
    assert started == ["contextualize", "router", "retrieve", "reason", "verify"]

    final = events[-1]["message"]
    assert final["content"] == "Paris is the capital of France [1]."
    assert final["sources"][0]["source"] == "france.txt"
    assert final["meta"]["verification"]["verdict"] == "supported"
    assert llm.calls["contextualizer"] == 0  # no history → no LLM call

    conv_id = events[0]["conversation_id"]
    conv = (await client.get(f"/api/v1/conversations/{conv_id}")).json()
    assert [m["role"] for m in conv["messages"]] == ["user", "assistant"]

    # Follow-up uses history → contextualizer runs.
    await ask(client, "And its largest city?", conversation_id=conv_id, mode="documents")
    assert llm.calls["contextualizer"] == 1


async def test_verifier_rejection_triggers_regeneration(client, llm):
    llm.replies["verifier"] = [
        '{"verdict": "unsupported", "reason": "invented a date"}',
        '{"verdict": "supported", "reason": "ok"}',
    ]
    await upload_text(client, "france.txt", FRANCE)
    events = await ask(client, "Tell me about Paris", mode="documents")
    types = [e["type"] for e in events]

    assert "answer_reset" in types
    assert llm.calls["reasoner"] == 2
    meta = events[-1]["message"]["meta"]
    assert meta["attempts"] == 2
    assert meta["verification"]["verdict"] == "supported"


async def test_verification_can_be_disabled(client):
    await upload_text(client, "france.txt", FRANCE)
    events = await ask(client, "Capital of France?", mode="documents", verify=False)
    assert "verify" not in [e.get("node") for e in events]
    assert events[-1]["message"]["meta"]["verification"]["verdict"] == "skipped"


async def test_empty_knowledge_base_routes_to_web(client, monkeypatch):
    from app.agents import web_search

    monkeypatch.setattr(web_search, "_ddg_search", lambda q, n: [
        {"title": "Paris - Wikipedia", "href": "https://en.wikipedia.org/wiki/Paris",
         "body": "Paris is the capital of France."}
    ])
    events = await ask(client, "What is the capital of France?")
    final = events[-1]["message"]
    assert final["meta"]["route"] == "web_search"
    assert final["sources"][0]["kind"] == "web"
    assert final["sources"][0]["url"].startswith("https://")


async def test_data_analyst_with_self_repair(client, sandbox):
    sandbox.results = [
        ExecutionResult(ok=False, output="", error="KeyError: 'Revenue'"),
        ExecutionResult(ok=True, output="| region | total |\n|---|---|\n| EU | 10 |"),
    ]
    csv = b"region,revenue\nEU,4\nEU,6\n"
    resp = await client.post("/api/v1/datasets", files={"file": ("sales.csv", csv, "text/csv")})
    assert resp.status_code == 201, resp.text
    ds = resp.json()
    assert ds["row_count"] == 2
    assert [c["name"] for c in ds["columns"]] == ["region", "revenue"]

    events = await ask(client, "Total revenue by region?", mode="data", dataset_id=ds["id"])
    code_events = [e for e in events if e["type"] == "code"]
    assert [e["attempt"] for e in code_events] == [1, 2]
    final = events[-1]["message"]
    assert final["meta"]["analysis"]["ok"] is True
    assert "verify" not in [e.get("node") for e in events]

    preview = (await client.get(f"/api/v1/datasets/{ds['id']}/preview")).json()
    assert preview["columns"] == ["region", "revenue"]


async def test_delete_document_and_reset(client):
    body = await upload_text(client, "france.txt", FRANCE)
    doc_id = body["documents"][0]["id"]
    assert (await client.delete(f"/api/v1/documents/{doc_id}")).status_code == 204
    assert (await client.get("/api/v1/knowledge-base/stats")).json()["chunks"] == 0

    await upload_text(client, "france.txt", FRANCE)
    assert (await client.delete("/api/v1/knowledge-base")).status_code == 204
    assert (await client.get("/api/v1/documents")).json() == []


async def test_feedback_and_conversation_management(client):
    await upload_text(client, "france.txt", FRANCE)
    events = await ask(client, "Capital?", mode="documents")
    msg_id = events[-1]["message"]["id"]
    conv_id = events[0]["conversation_id"]

    resp = await client.post(f"/api/v1/messages/{msg_id}/feedback", json={"value": 1})
    assert resp.json()["feedback"] == 1

    resp = await client.patch(f"/api/v1/conversations/{conv_id}", json={"title": "Geo"})
    assert resp.json()["title"] == "Geo"
    assert (await client.delete(f"/api/v1/conversations/{conv_id}")).status_code == 204
    assert (await client.get(f"/api/v1/conversations/{conv_id}")).status_code == 404


async def test_unknown_conversation_returns_error_event(client):
    events = await ask(client, "hi", conversation_id="missing")
    assert events[-1] == {**events[-1], "type": "error", "code": "not_found"}


async def test_api_key_required_when_configured(tmp_path):
    import httpx

    settings = Settings(_env_file=None, ENVIRONMENT="test", API_KEY="s3cret",  # type: ignore[call-arg]
                        DATA_DIR=tmp_path,
                        DATABASE_URL=f"sqlite+aiosqlite:///{tmp_path / 'a.db'}")

    class _Stub:
        async def close(self) -> None: ...

    async def factory(_: Settings):
        return _Stub()

    app = create_app(settings, container_factory=factory)  # type: ignore[arg-type]
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            assert (await c.get("/api/v1/conversations")).status_code == 401
            r = await c.get("/api/v1/conversations", headers={"X-API-Key": "wrong"})
            assert r.status_code == 401
            assert r.json()["error"]["code"] == "unauthorized"
            assert (await c.get("/api/v1/health/live")).status_code == 200


def test_prod_requires_api_key(tmp_path):
    import pytest

    s = Settings(_env_file=None, ENVIRONMENT="prod", DATA_DIR=tmp_path)  # type: ignore[call-arg]
    with pytest.raises(RuntimeError):
        create_app(s)


async def test_refusal_skips_verification(client, llm):
    llm.replies["reasoner"] = (
        "I couldn't find this in the available sources. Try uploading the HR policy."
    )
    await upload_text(client, "france.txt", FRANCE)
    events = await ask(client, "Who is the CEO?", mode="documents")
    assert "verify" not in [e.get("node") for e in events]
    assert llm.calls["verifier"] == 0
    assert events[-1]["message"]["meta"]["verification"]["verdict"] == "skipped"
