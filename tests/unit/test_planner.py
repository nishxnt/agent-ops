import shutil
from pathlib import Path

import pytest
from pydantic import ValidationError

from agentops.agents.planner import PlannerAgent
from agentops.llm.client import MockLLMClient

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "llm_responses"


def planner_client(tmp_path: Path, fixture_name: str = "default.json") -> MockLLMClient:
    fixture_dir = FIXTURE_DIR / "planner"
    if fixture_name == "default.json":
        return MockLLMClient(model="qwen2.5:7b", fixture_dir=fixture_dir)

    scenario_dir = tmp_path / fixture_name.removesuffix(".json")
    scenario_dir.mkdir()
    shutil.copyfile(fixture_dir / fixture_name, scenario_dir / "default.json")
    return MockLLMClient(model="qwen2.5:7b", fixture_dir=scenario_dir)


@pytest.mark.asyncio
async def test_planner_returns_valid_plan_for_simple_query(tmp_path: Path) -> None:
    client = planner_client(tmp_path)
    agent = PlannerAgent(llm_client=client)

    plan = await agent.plan("What is FAISS?")

    assert plan.query == "What is FAISS?"
    assert len(plan.subtasks) == 1
    assert plan.estimated_complexity == "low"
    assert client.invocation_count == 1


@pytest.mark.asyncio
async def test_planner_returns_multi_subtask_plan_for_complex_query(
    tmp_path: Path,
) -> None:
    agent = PlannerAgent(llm_client=planner_client(tmp_path, "complex_query.json"))

    plan = await agent.plan(
        "Compare vector database options for a regulated enterprise RAG platform."
    )

    assert len(plan.subtasks) >= 3
    assert plan.estimated_complexity == "high"


@pytest.mark.asyncio
async def test_planner_subtasks_have_non_empty_search_keywords(
    tmp_path: Path,
) -> None:
    agent = PlannerAgent(llm_client=planner_client(tmp_path, "complex_query.json"))

    plan = await agent.plan("Compare vector databases.")

    assert all(subtask.search_keywords for subtask in plan.subtasks)


@pytest.mark.asyncio
async def test_planner_recommended_researcher_count_within_bounds(
    tmp_path: Path,
) -> None:
    agent = PlannerAgent(llm_client=planner_client(tmp_path, "complex_query.json"))

    plan = await agent.plan("Compare vector databases.")

    assert 1 <= plan.recommended_researcher_count <= 3


@pytest.mark.asyncio
async def test_planner_raises_validation_error_on_malformed_output(
    tmp_path: Path,
) -> None:
    agent = PlannerAgent(llm_client=planner_client(tmp_path, "malformed.json"))

    with pytest.raises(ValidationError):
        await agent.plan("Return a malformed plan.")
