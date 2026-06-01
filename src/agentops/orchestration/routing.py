"""Conditional routing helpers for the LangGraph pipeline."""

from typing import Literal

from agentops.orchestration.state import PipelineError, PipelineState, PipelineStatus


def route_after_research(state: PipelineState) -> Literal["proceed", "halt"]:
    """Route away from research failures before critique."""

    return "halt" if state["pipeline_status"] == PipelineStatus.FAILED else "proceed"


def route_quality_decision(state: PipelineState) -> Literal["PASS", "REVISION", "FAIL"]:
    """Route from the Quality Gate decision."""

    decision = state["quality_decision"]
    if decision is None:
        raise PipelineError(
            "Cannot route quality decision before evaluation.",
            stage="quality",
        )
    return decision.decision
