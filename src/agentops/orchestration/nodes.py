"""Async LangGraph node functions for the Phase 2 pipeline."""

import asyncio

from agentops.agents.critic import CriticAgent
from agentops.agents.planner import PlannerAgent, ResearchSubtask
from agentops.agents.quality_gate import QualityGateAgent
from agentops.agents.researcher import ResearcherAgent, ResearchFinding
from agentops.agents.writer import WriterAgent
from agentops.budget.guard import BudgetExceededError
from agentops.config import get_settings
from agentops.orchestration.state import PipelineError, PipelineState, PipelineStatus


async def planning_node(
    state: PipelineState,
    *,
    planner: PlannerAgent,
) -> PipelineState:
    """Plan the query and move to sequential research."""

    plan = await planner.plan(state["query"])
    return {**state, "plan": plan, "pipeline_status": PipelineStatus.RESEARCHING}


async def research_node(
    state: PipelineState,
    *,
    researcher: ResearcherAgent,
) -> PipelineState:
    """Run planned research subtasks concurrently and tolerate partial failures."""

    plan = state["plan"]
    if plan is None:
        raise PipelineError("Cannot research without a plan.", stage="research")

    settings = get_settings()
    timeout_s = settings.researcher_timeout_secs

    async def _run_one(subtask: ResearchSubtask) -> ResearchFinding:
        return await asyncio.wait_for(researcher.research(subtask), timeout=timeout_s)

    results = await asyncio.gather(
        *(_run_one(subtask) for subtask in plan.subtasks),
        return_exceptions=True,
    )

    findings: list[ResearchFinding] = []
    failed_tasks: list[str] = []
    for subtask, result in zip(plan.subtasks, results, strict=True):
        if isinstance(result, BudgetExceededError):
            raise result
        if isinstance(result, BaseException):
            failed_tasks.append(subtask.task_id)
        else:
            findings.append(result)

    if not findings:
        return {
            **state,
            "findings": [],
            "failed_tasks": failed_tasks,
            "pipeline_status": PipelineStatus.FAILED,
            "error": PipelineError(
                f"All {len(plan.subtasks)} researchers failed.",
                stage="research",
            ),
        }

    return {
        **state,
        "findings": findings,
        "failed_tasks": failed_tasks,
        "pipeline_status": PipelineStatus.CRITICISING,
    }


async def critique_node(
    state: PipelineState,
    *,
    critic: CriticAgent,
) -> PipelineState:
    """Critique gathered findings and move to report writing."""

    critic_report = await critic.review(state["findings"])
    return {
        **state,
        "critic_report": critic_report,
        "pipeline_status": PipelineStatus.WRITING,
    }


async def write_node(
    state: PipelineState,
    *,
    writer: WriterAgent,
) -> PipelineState:
    """Write a report and preserve graph-owned revision count."""

    critic_report = state["critic_report"]
    if critic_report is None:
        raise PipelineError("Cannot write without a critic report.", stage="write")

    report = await writer.write(critic_report, state["query"])
    report = report.model_copy(update={"revision_count": state["revision_count"]})
    return {
        **state,
        "report": report,
        "pipeline_status": PipelineStatus.QUALITY_CHECK,
    }


async def quality_check_node(
    state: PipelineState,
    *,
    quality_gate: QualityGateAgent,
) -> PipelineState:
    """Evaluate report quality and set the next route status."""

    report = state["report"]
    critic_report = state["critic_report"]
    if report is None:
        raise PipelineError("Cannot quality-check without a report.", stage="quality")
    if critic_report is None:
        raise PipelineError(
            "Cannot quality-check without a critic report.",
            stage="quality",
        )

    decision = await quality_gate.evaluate(
        report,
        critic_report.verified_facts,
        state["query"],
    )
    new_state: PipelineState = {**state, "quality_decision": decision}
    if decision.decision == "REVISION":
        new_state["revision_count"] = state["revision_count"] + 1
        new_state["pipeline_status"] = PipelineStatus.REVISING
    elif decision.decision == "PASS":
        new_state["pipeline_status"] = PipelineStatus.DONE
    else:
        new_state["pipeline_status"] = PipelineStatus.FAILED
    return new_state
