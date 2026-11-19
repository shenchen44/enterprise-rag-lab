import os
import tempfile
from pathlib import Path

os.environ.setdefault("PLATFORM_STORAGE", tempfile.mkdtemp(prefix="rag-platform-test-"))
os.environ.setdefault("AGENT_INTERNAL_TOKEN", "platform-test-token")
import pytest
import httpx
from agent_service import app as mod


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def client():
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=mod.app),
        base_url="http://test",
        headers={"X-Internal-Token": mod.TOKEN},
    )


@pytest.mark.anyio
async def test_internal_api_requires_token():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=mod.app), base_url="http://test"
    ) as c:
        assert (await c.get("/internal/catalog")).status_code == 401


@pytest.mark.anyio
async def test_ingestion_rejects_path_traversal(client):
    async with client as c:
        r = await c.post(
            "/internal/ingest",
            json={
                "documentId": "test",
                "owner": "alice",
                "fileName": "secret.txt",
                "storedName": "../../secret.txt",
            },
        )
        assert r.status_code == 400


@pytest.mark.anyio
async def test_private_evidence_is_owner_filtered(client, monkeypatch):
    monkeypatch.setattr(mod, "public_files", lambda: [])
    p = mod.UPLOADS / "test-document.txt"
    p.write_text(
        "Project Jupiter revenue is 42 million in fiscal year 2025. This private evidence belongs only to Alice."
    )
    mod.index_file(p, "private-alice-test", "alice", "test-document.txt")
    assert mod.lexical("Jupiter revenue", "alice", ["private-alice-test"])
    assert not mod.lexical("Jupiter revenue", "bob", ["private-alice-test"])
    async with client as c:
        body = {
            "taskId": "task-" + os.urandom(8).hex(),
            "owner": "alice",
            "question": "Jupiter revenue",
            "documentIds": ["private-alice-test"],
            "mode": "evidence",
        }
        r = await c.post("/internal/query/stream", json=body)
        assert r.status_code == 200
        assert "42 million" in r.text
        assert '"type": "done"' in r.text
        assert (await c.post("/internal/query/stream", json=body)).status_code == 409
        body["owner"] = "bob"
        assert (await c.post("/internal/query/stream", json=body)).status_code == 403


@pytest.mark.anyio
async def test_invalid_mode_is_not_silently_downgraded(client):
    async with client as c:
        r = await c.post(
            "/internal/query/stream",
            json={
                "taskId": "invalid",
                "owner": "alice",
                "question": "test",
                "mode": "fake",
            },
        )
        assert r.status_code == 400


@pytest.mark.anyio
async def test_model_401_has_actionable_error_and_persisted_status(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(mod, "public_files", lambda: [])
    monkeypatch.setattr(mod, "MODEL_KEY", "test-only-not-a-real-key")
    monkeypatch.setattr(mod, "MODEL_STATE", tmp_path / "model-status.json")
    monkeypatch.setattr(
        mod,
        "lexical",
        lambda *args: [
            {
                "id": "c",
                "documentId": "d",
                "fileName": "test.txt",
                "page": 1,
                "text": "Revenue is 42 million.",
                "score": 1.0,
            }
        ],
    )

    class Response:
        status_code = 401

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    class Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        def stream(self, *args, **kwargs):
            return Response()

    monkeypatch.setattr(httpx, "AsyncClient", Client)
    response = await mod.query_stream(
        mod.Query(
            taskId="auth-" + os.urandom(8).hex(),
            owner="alice",
            question="Revenue?",
            documentIds=["d"],
            mode="live",
        )
    )
    events = "".join([item async for item in response.body_iterator])
    assert "认证失败" in events
    assert mod.MODEL_STATUS == "auth_error"
    assert mod.MODEL_STATE.exists()
