import shutil
from pathlib import Path

import pytest
from pydantic import ValidationError

from agentops.agents.planner import ResearchSubtask
from agentops.agents.researcher import ResearcherAgent, ResearchFinding
from agentops.dev.search_cache import SearchResult
from agentops.llm.client import MockLLMClient

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "llm_responses"


class SpySearchClient:
    def __init__(self) -> None:
        self.call_count = 0
        self.queries: list[str] = []
        self.results = [
            SearchResult(
                title="FAISS documentation",
                url="https://faiss.ai/",
                content=(
                    "FAISS is a library for efficient similarity search and "
                    "clustering of dense vectors."
                ),
                score=0.98,
            ),
            SearchResult(
                title="FAISS GitHub",
                url="https://github.com/facebookresearch/faiss",
                content="FAISS contains algorithms that search in sets of vectors.",
                score=0.93,
            ),
        ]

    async def search(self, query: str) -> list[SearchResult]:
        self.call_count += 1
        self.queries.append(query)
        return self.results


def researcher_client(
    tmp_path: Path,
    fixture_name: str = "default.json",
) -> MockLLMClient:
    fixture_dir = FIXTURE_DIR / "researcher"
    if fixture_name == "default.json":
        return MockLLMClient(model="qwen2.5:7b", fixture_dir=fixture_dir)

    scenario_dir = tmp_path / fixture_name.removesuffix(".json")
    scenario_dir.mkdir()
    shutil.copyfile(fixture_dir / fixture_name, scenario_dir / "default.json")
    return MockLLMClient(model="qwen2.5:7b", fixture_dir=scenario_dir)


def subtask() -> ResearchSubtask:
    return ResearchSubtask(
        task_id="task-1",
        description="Find core facts about FAISS and its use in vector search.",
        search_keywords=["FAISS", "similarity search", "vector database"],
        expected_output_type="factual",
    )


@pytest.mark.asyncio
async def test_researcher_returns_valid_finding_with_search_hits(
    tmp_path: Path,
) -> None:
    search_client = SpySearchClient()
    client = researcher_client(tmp_path)
    agent = ResearcherAgent(llm_client=client, search_client=search_client)  # type: ignore[arg-type]

    finding = await agent.research(subtask())

    assert finding.task_id == "task-1"
    assert len(finding.key_facts) >= 3
    assert finding.confidence_score >= 0.0
    assert client.invocation_count == 1


@pytest.mark.asyncio
async def test_researcher_sources_are_populated_from_search_results(
    tmp_path: Path,
) -> None:
    search_client = SpySearchClient()
    agent = ResearcherAgent(
        llm_client=researcher_client(tmp_path),
        search_client=search_client,  # type: ignore[arg-type]
    )

    finding = await agent.research(subtask())

    search_urls = {result.url for result in search_client.results}
    assert finding.sources
    assert {source.url for source in finding.sources}.issubset(search_urls)


@pytest.mark.asyncio
async def test_researcher_calls_search_client(tmp_path: Path) -> None:
    search_client = SpySearchClient()
    agent = ResearcherAgent(
        llm_client=researcher_client(tmp_path),
        search_client=search_client,  # type: ignore[arg-type]
    )

    await agent.research(subtask())

    assert search_client.call_count == 1
    assert search_client.queries == ["FAISS similarity search vector database"]


@pytest.mark.asyncio
async def test_researcher_raises_validation_error_on_malformed_output(
    tmp_path: Path,
) -> None:
    agent = ResearcherAgent(
        llm_client=researcher_client(tmp_path, "missing_key_facts.json"),
        search_client=SpySearchClient(),  # type: ignore[arg-type]
    )

    with pytest.raises(ValidationError):
        await agent.research(subtask())


@pytest.mark.asyncio
async def test_researcher_returns_low_confidence_finding(tmp_path: Path) -> None:
    agent = ResearcherAgent(
        llm_client=researcher_client(tmp_path, "low_confidence.json"),
        search_client=SpySearchClient(),  # type: ignore[arg-type]
    )

    finding = await agent.research(subtask())

    assert isinstance(finding, ResearchFinding)
    assert finding.confidence_score < 0.4
