"""Shared LangGraph state for the AgentOps pipeline."""

from enum import StrEnum
from typing import TypedDict
from uuid import uuid4

from agentops.agents.critic import CriticReport
from agentops.agents.planner import ResearchPlan
from agentops.agents.quality_gate import QualityDecision
from agentops.agents.researcher import ResearchFinding
from agentops.agents.writer import ResearchReport
from agentops.audit.schema import AuditEntry as AuditEntry
from agentops.budget.guard import BudgetGuard
from agentops.config import Settings, get_settings


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
    budget_tracker: BudgetGuard
    audit_entries: list[AuditEntry]
    pipeline_status: PipelineStatus
    error: PipelineError | None


def initial_state(
    query: str,
    run_id: str | None = None,
    *,
    settings: Settings | None = None,
) -> PipelineState:
    """Build the initial pipeline state for a query."""

    s = settings or get_settings()
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
        "budget_tracker": BudgetGuard(budget_tokens=s.budget_token_limit),
        "audit_entries": [],
        "pipeline_status": PipelineStatus.PLANNING,
        "error": None,
    }
