"""Pydantic models for the AgentOps HTTP gateway."""

from pydantic import BaseModel, Field


class RunRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    run_id: str | None = None


class RunSubmitResponse(BaseModel):
    run_id: str
    status: str


class RunStatusResponse(BaseModel):
    run_id: str
    status: str
    pipeline_status: str | None = None
    decision: str | None = None
    error: str | None = None
    budget_spent: int | None = None
    per_agent_spend: dict[str, int] | None = None
    failed_tasks: list[str] | None = None
    report_sections: int | None = None


class HealthResponse(BaseModel):
    status: str


class ReadyResponse(BaseModel):
    status: str
    checks: dict[str, bool]
