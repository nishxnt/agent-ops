import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from agentops.api.main import create_app


@pytest.fixture
def app(monkeypatch: pytest.MonkeyPatch, tmp_path) -> FastAPI:
    monkeypatch.setenv("AGENTOPS_MODE", "mock")
    monkeypatch.setenv("AUDIT_DB_PATH", str(tmp_path / "audit.sqlite"))
    monkeypatch.setenv("BUDGET_TOKEN_LIMIT", "100000")
    return create_app()


@pytest.fixture
async def client(app: FastAPI):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_healthz_returns_200(client: AsyncClient) -> None:
    response = await client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


@pytest.mark.asyncio
async def test_readyz_returns_200_when_healthy(client: AsyncClient) -> None:
    response = await client.get("/readyz")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert all(body["checks"].values())


@pytest.mark.asyncio
async def test_readyz_returns_503_when_audit_db_unwritable(
    app: FastAPI,
    tmp_path,
) -> None:
    app.state.orchestrator.audit_logger.db_path = tmp_path / "nonexistent" / "x.db"
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/readyz")
    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"
    assert response.json()["checks"]["audit_db_writable"] is False


@pytest.mark.asyncio
async def test_post_run_returns_202_with_run_id(client: AsyncClient) -> None:
    response = await client.post("/run", json={"query": "What is FAISS?"})
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "RUNNING"
    assert len(body["run_id"]) > 0


@pytest.mark.asyncio
async def test_status_unknown_run_id_returns_404(client: AsyncClient) -> None:
    response = await client.get("/status/nonexistent")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_full_run_lifecycle(client: AsyncClient, app: FastAPI) -> None:
    """POST /run, wait for completion via registry, then GET /status."""

    response = await client.post("/run", json={"query": "What is FAISS?"})
    run_id = response.json()["run_id"]
    record = await app.state.registry.wait_for_completion(run_id, timeout=30.0)
    assert record.status == "COMPLETED"
    status_response = await client.get(f"/status/{run_id}")
    assert status_response.status_code == 200
    payload = status_response.json()
    assert payload["status"] == "COMPLETED"
    assert payload["pipeline_status"] == "DONE"
    assert payload["decision"] == "PASS"
    assert payload["budget_spent"] > 0


@pytest.mark.asyncio
async def test_concurrent_runs_dont_interfere(
    client: AsyncClient,
    app: FastAPI,
) -> None:
    """Two concurrent runs should both complete with their own state."""

    r1 = await client.post("/run", json={"query": "First query"})
    r2 = await client.post("/run", json={"query": "Second query"})
    id1, id2 = r1.json()["run_id"], r2.json()["run_id"]
    assert id1 != id2
    record1 = await app.state.registry.wait_for_completion(id1, timeout=30.0)
    record2 = await app.state.registry.wait_for_completion(id2, timeout=30.0)
    assert record1.status == "COMPLETED"
    assert record2.status == "COMPLETED"
    assert record1.final_state["budget_tracker"].spent > 0
    assert record2.final_state["budget_tracker"].spent > 0

    audit_logger = app.state.orchestrator.audit_logger
    assert len(audit_logger.query_by_run_id(id1)) > 0
    assert len(audit_logger.query_by_run_id(id2)) > 0
    assert audit_logger.verify_chain(id1) is True
    assert audit_logger.verify_chain(id2) is True
