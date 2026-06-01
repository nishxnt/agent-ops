import pytest

from agentops.orchestration.graph import PipelineOrchestrator
from agentops.orchestration.state import PipelineStatus


@pytest.mark.asyncio
async def test_pipeline_e2e_mock_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End-to-end pipeline run in mock mode via the production factory."""

    monkeypatch.setenv("AGENTOPS_MODE", "mock")
    monkeypatch.setenv("BUDGET_TOKEN_LIMIT", "100000")

    orchestrator = PipelineOrchestrator()
    state = await orchestrator.run("What is FAISS?")

    assert state["pipeline_status"] == PipelineStatus.DONE
    assert state["quality_decision"] is not None
    assert state["quality_decision"].decision == "PASS"
    assert state["report"] is not None
    assert state["budget_tracker"].spent > 0
    assert state["budget_tracker"].per_agent_spend["planner"] > 0
    assert state["budget_tracker"].per_agent_spend["researcher"] > 0
