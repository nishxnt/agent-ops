"""FastAPI gateway for asynchronous AgentOps pipeline execution."""

from __future__ import annotations

import asyncio
import sqlite3
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request, Response

from agentops.api.models import (
    HealthResponse,
    ReadyResponse,
    RunRequest,
    RunStatusResponse,
    RunSubmitResponse,
)
from agentops.api.registry import RunRecord, RunRegistry
from agentops.orchestration.graph import PipelineOrchestrator


def create_app(
    *,
    orchestrator: PipelineOrchestrator | None = None,
    registry: RunRegistry | None = None,
) -> FastAPI:
    """Factory so tests can inject a pre-built orchestrator and registry."""

    app = FastAPI(title="AgentOps Gateway", version="0.5.0")
    app.state.orchestrator = orchestrator or PipelineOrchestrator()
    app.state.registry = registry or RunRegistry()

    @app.get("/healthz", response_model=HealthResponse)
    async def healthz() -> HealthResponse:
        return HealthResponse(status="alive")

    @app.get("/readyz", response_model=ReadyResponse)
    async def readyz(response: Response, request: Request) -> ReadyResponse:
        orch: PipelineOrchestrator = request.app.state.orchestrator
        checks = {
            "orchestrator_initialized": orch is not None,
            "audit_db_writable": _audit_db_writable(orch),
        }
        ready = all(checks.values())
        if not ready:
            response.status_code = 503
        return ReadyResponse(
            status="ready" if ready else "not_ready",
            checks=checks,
        )

    @app.post("/run", response_model=RunSubmitResponse, status_code=202)
    async def start_run(body: RunRequest, request: Request) -> RunSubmitResponse:
        orch: PipelineOrchestrator = request.app.state.orchestrator
        reg: RunRegistry = request.app.state.registry
        run_id = body.run_id or uuid4().hex
        await reg.register(run_id, body.query)
        task = asyncio.create_task(_execute_pipeline(orch, reg, run_id, body.query))
        await reg.attach_task(run_id, task)
        return RunSubmitResponse(run_id=run_id, status="RUNNING")

    @app.get("/status/{run_id}", response_model=RunStatusResponse)
    async def get_status(run_id: str, request: Request) -> RunStatusResponse:
        reg: RunRegistry = request.app.state.registry
        record = await reg.get(run_id)
        if record is None:
            raise HTTPException(status_code=404, detail="run_id not found")
        return _build_status_response(record)

    return app


async def _execute_pipeline(
    orch: PipelineOrchestrator,
    reg: RunRegistry,
    run_id: str,
    query: str,
) -> None:
    """Background task body. Never raises; failures are stored."""

    try:
        state = await orch.run(query, run_id=run_id)
        await reg.mark_complete(run_id, state)
    except Exception as exc:
        await reg.mark_failed(run_id, repr(exc))


def _audit_db_writable(orch: PipelineOrchestrator) -> bool:
    try:
        path = orch.audit_logger.db_path
        with sqlite3.connect(path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.rollback()
        return True
    except Exception:
        return False


def _build_status_response(record: RunRecord) -> RunStatusResponse:
    """Translate a RunRecord into the API response model."""

    payload: dict[str, Any] = {
        "run_id": record.run_id,
        "status": record.status,
        "error": record.error,
    }
    if record.final_state is not None:
        state = record.final_state
        payload.update(
            {
                "pipeline_status": state["pipeline_status"].value,
                "decision": (
                    state["quality_decision"].decision
                    if state["quality_decision"]
                    else None
                ),
                "budget_spent": state["budget_tracker"].spent,
                "per_agent_spend": dict(state["budget_tracker"].per_agent_spend),
                "failed_tasks": state["failed_tasks"],
                "report_sections": (
                    len(state["report"].sections) if state["report"] else 0
                ),
            }
        )
    return RunStatusResponse(**payload)


app = create_app()
