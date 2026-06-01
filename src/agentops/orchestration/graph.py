"""LangGraph StateGraph orchestration for AgentOps."""

from functools import partial
from typing import cast

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from agentops.agents.critic import CriticAgent
from agentops.agents.planner import PlannerAgent
from agentops.agents.quality_gate import QualityGateAgent
from agentops.agents.researcher import ResearcherAgent
from agentops.agents.writer import WriterAgent
from agentops.budget.context import current_budget_guard
from agentops.budget.guard import BudgetExceededError
from agentops.config import Settings, get_settings
from agentops.orchestration.nodes import (
    critique_node,
    planning_node,
    quality_check_node,
    recovery_node,
    research_node,
    write_node,
)
from agentops.orchestration.routing import (
    route_after_critique,
    route_after_recovery,
    route_after_research,
    route_quality_decision,
)
from agentops.orchestration.state import (
    PipelineError,
    PipelineState,
    PipelineStatus,
    initial_state,
)


class PipelineOrchestrator:
    """Compiled LangGraph pipeline with linear flow and revision routing."""

    def __init__(
        self,
        planner: PlannerAgent | None = None,
        researcher: ResearcherAgent | None = None,
        critic: CriticAgent | None = None,
        writer: WriterAgent | None = None,
        quality_gate: QualityGateAgent | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.planner = planner or PlannerAgent()
        self.researcher = researcher or ResearcherAgent()
        self.critic = critic or CriticAgent()
        self.writer = writer or WriterAgent()
        self.quality_gate = quality_gate or QualityGateAgent(settings=self.settings)
        self.graph = self._build_graph()

    def _build_graph(
        self,
    ) -> CompiledStateGraph[PipelineState, None, PipelineState, PipelineState]:
        """Build and compile the Phase 2 M1 LangGraph StateGraph."""

        graph: StateGraph[PipelineState, None, PipelineState, PipelineState] = (
            StateGraph(PipelineState)
        )
        graph.add_node("plan", partial(planning_node, planner=self.planner))
        graph.add_node("research", partial(research_node, researcher=self.researcher))
        graph.add_node("critique", partial(critique_node, critic=self.critic))
        graph.add_node("recovery", recovery_node)
        graph.add_node("write", partial(write_node, writer=self.writer))
        graph.add_node(
            "quality_check",
            partial(quality_check_node, quality_gate=self.quality_gate),
        )

        graph.set_entry_point("plan")
        graph.add_edge("plan", "research")
        graph.add_conditional_edges(
            "research",
            route_after_research,
            {
                "proceed": "critique",
                "recover": "recovery",
            },
        )
        graph.add_conditional_edges(
            "critique",
            route_after_critique,
            {
                "proceed": "write",
                "recover": "recovery",
            },
        )
        graph.add_conditional_edges(
            "recovery",
            route_after_recovery,
            {
                "retry": "research",
                "fail": END,
            },
        )
        graph.add_edge("write", "quality_check")
        graph.add_conditional_edges(
            "quality_check",
            route_quality_decision,
            {
                "PASS": END,
                "REVISION": "write",
                "FAIL": END,
            },
        )
        return graph.compile()

    async def run(self, query: str, *, run_id: str | None = None) -> PipelineState:
        """Run the compiled graph for a query."""

        state = initial_state(query, run_id=run_id, settings=self.settings)
        guard = state["budget_tracker"]
        token = current_budget_guard.set(guard)
        try:
            result = await self.graph.ainvoke(state)
            return cast(PipelineState, result)
        except BudgetExceededError as exc:
            return cast(
                PipelineState,
                {
                    **state,
                    "budget_tracker": guard,
                    "pipeline_status": PipelineStatus.BUDGET_HALTED,
                    "error": PipelineError(str(exc), stage=exc.agent_type),
                },
            )
        finally:
            current_budget_guard.reset(token)
