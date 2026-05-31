"""Shared LangGraph state for the AgentOps pipeline."""

from enum import StrEnum
from typing import TypedDict
from uuid import uuid4

from pydantic import BaseModel

from agentops.agents.critic import CriticReport
from agentops.agents.planner import ResearchPlan
from agentops.agents.quality_gate import QualityDecision
from agentops.agents.researcher import ResearchFinding
from agentops.agents.writer import ResearchReport


class PipelineStatus(StrEnum):
    """Pipeline stages tracked in the graph state."""

    PLANNING = "PLANNING"
    RESEARCHING = "RESEARCHING"
    CRITICISING = "CRITICISING"
    WRITING = "WRITING"
    QUALITY_CHECK = "QUALITY_CHECK"
    REVISING = "REVISING"
    DONE = "DONE"
    FAILED = "FAILED"
    BUDGET_HALTED = "BUDGET_HALTED"
    RECOVERY = "RECOVERY"


class BudgetTracker(BaseModel):
    """Stub for Phase 2 M1. Full enforcement lands in M2."""

    spent_prompt_tokens: int = 0
    spent_completion_tokens: int = 0
    budget_tokens: int = 50_000


class AuditEntry(BaseModel):
    """Stub. Full hash-chained schema in Phase 3."""

    run_id: str
    agent_type: str
    timestamp_utc: str
    status: str


class PipelineError(Exception):
    """Pipeline exception annotated with the failed stage."""

    def __init__(self, message: str, *, stage: str | None = None) -> None:
        super().__init__(message)
        self.stage = stage


class PipelineState(TypedDict):
    """State carried through the LangGraph pipeline."""

    run_id: str
    query: str
    plan: ResearchPlan | None
    findings: list[ResearchFinding]
    failed_tasks: list[str]
    critic_report: CriticReport | None
    report: ResearchReport | None
    quality_decision: QualityDecision | None
    revision_count: int
    recovery_attempts: dict[str, int]
    budget_tracker: BudgetTracker
    audit_entries: list[AuditEntry]
    pipeline_status: PipelineStatus
    error: PipelineError | None


def initial_state(query: str, run_id: str | None = None) -> PipelineState:
    """Build the initial pipeline state for a query."""

    return {
        "run_id": run_id or uuid4().hex,
        "query": query,
        "plan": None,
        "findings": [],
        "failed_tasks": [],
        "critic_report": None,
        "report": None,
        "quality_decision": None,
        "revision_count": 0,
        "recovery_attempts": {},
        "budget_tracker": BudgetTracker(),
        "audit_entries": [],
        "pipeline_status": PipelineStatus.PLANNING,
        "error": None,
    }
