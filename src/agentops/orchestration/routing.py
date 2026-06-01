"""Conditional routing helpers for the LangGraph pipeline."""

from typing import Literal

from agentops.orchestration.state import PipelineError, PipelineState, PipelineStatus


def route_after_research(state: PipelineState) -> Literal["proceed", "recover"]:
    """Route research failures into recovery."""

    return (
        "recover" if state["pipeline_status"] == PipelineStatus.RECOVERY else "proceed"
    )


def route_after_critique(state: PipelineState) -> Literal["proceed", "recover"]:
    """Route low-quality evidence into recovery."""

    return (
        "recover" if state["pipeline_status"] == PipelineStatus.RECOVERY else "proceed"
    )


def route_after_recovery(state: PipelineState) -> Literal["retry", "fail"]:
    """Retry research until the recovery circuit breaker opens."""

    return "fail" if state["pipeline_status"] == PipelineStatus.FAILED else "retry"


def route_quality_decision(state: PipelineState) -> Literal["PASS", "REVISION", "FAIL"]:
    """Route from the Quality Gate decision."""

    decision = state["quality_decision"]
    if decision is None:
        raise PipelineError(
            "Cannot route quality decision before evaluation.",
            stage="quality",
        )
    return decision.decision
