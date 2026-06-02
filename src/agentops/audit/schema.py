"""Immutable audit log record schema."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

AuditStatus = Literal["SUCCESS", "RECOVERED", "FAILED", "BUDGET_HALTED"]


class AuditEntry(BaseModel):
    """Immutable record of one agent action. Frozen after construction."""

    model_config = ConfigDict(frozen=True)

    run_id: str
    agent_type: str
    timestamp_utc: str
    input_hash: str
    output_hash: str
    model_id: str
    model_version: str
    latency_ms: int
    prompt_tokens: int
    completion_tokens: int
    confidence_score: float | None = None
    reasoning_trace: str | None = None
    parent_run_id: str | None = None
    status: AuditStatus
