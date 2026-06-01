import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from agentops.agents.critic import CriticReport, VerifiedFact
from agentops.agents.researcher import SourceCitation
from agentops.agents.writer import WriterAgent
from agentops.llm.client import LLMClient
from agentops.llm.models import LLMRequest, LLMResponse

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "llm_responses"


class FixtureSequenceLLMClient(LLMClient):
    def __init__(self, fixture_names: list[str]) -> None:
        super().__init__(model="qwen2.5:7b")
        self.fixture_names = fixture_names
        self.invocation_count = 0

    async def _do_complete(self, request: LLMRequest) -> LLMResponse:
        fixture_name = self.fixture_names[self.invocation_count]
        self.invocation_count += 1
        fixture = json.loads(
            (FIXTURE_DIR / "writer" / fixture_name).read_text(encoding="utf-8")
        )
        return LLMResponse(
            content=str(fixture["content"]),
            model=request.model,
            prompt_tokens=1,
            completion_tokens=1,
        )


def source() -> SourceCitation:
    return SourceCitation(
        url="https://example.com/source",
        title="Example source",
        relevance_score=0.9,
    )


def critic_report() -> CriticReport:
    return CriticReport(
        verified_facts=[
            VerifiedFact(
                text="FAISS supports dense vector search.",
                source_task_ids=["task-a"],
                supporting_sources=[source()],
                confidence=0.8,
            ),
            VerifiedFact(
                text="FAISS includes indexing algorithms.",
                source_task_ids=["task-a"],
                supporting_sources=[source()],
                confidence=0.9,
            ),
            VerifiedFact(
                text="Enterprise RAG needs observability.",
                source_task_ids=["task-b"],
                supporting_sources=[source()],
                confidence=0.6,
            ),
        ],
        contradictions=[],
        low_confidence_items=["task-c"],
        overall_evidence_quality=0.76,
        proceed_recommendation=True,
    )


@pytest.mark.asyncio
async def test_writer_returns_valid_report_for_two_task_groups() -> None:
    client = FixtureSequenceLLMClient(
        ["default.json", "default.json", "executive_summary.json"]
    )
    agent = WriterAgent(llm_client=client)

    report = await agent.write(critic_report(), "Assess FAISS for RAG.")

    assert report.title == "Assess FAISS for RAG."
    assert report.executive_summary
    assert len(report.sections) == 2
    assert report.revision_count == 0
    assert report.data_gaps_acknowledged == ["task-c"]


@pytest.mark.asyncio
async def test_writer_section_count_matches_distinct_source_task_ids() -> None:
    client = FixtureSequenceLLMClient(
        ["default.json", "default.json", "executive_summary.json"]
    )
    agent = WriterAgent(llm_client=client)

    report = await agent.write(critic_report(), "Assess FAISS for RAG.")

    distinct_task_ids = {
        fact.source_task_ids[0] for fact in critic_report().verified_facts
    }
    assert len(report.sections) == len(distinct_task_ids)


@pytest.mark.asyncio
async def test_writer_llm_call_count_is_sections_plus_summary() -> None:
    client = FixtureSequenceLLMClient(
        ["default.json", "default.json", "executive_summary.json"]
    )
    agent = WriterAgent(llm_client=client)

    report = await agent.write(critic_report(), "Assess FAISS for RAG.")

    assert client.invocation_count == len(report.sections) + 1


@pytest.mark.asyncio
async def test_writer_raises_validation_error_on_malformed_section() -> None:
    client = FixtureSequenceLLMClient(["malformed.json"])
    agent = WriterAgent(llm_client=client)

    with pytest.raises(ValidationError):
        await agent.write(critic_report(), "Assess FAISS for RAG.")


@pytest.mark.asyncio
async def test_writer_propagates_data_gaps_from_critic() -> None:
    report_from_critic = critic_report()
    report_from_critic.low_confidence_items = ["task-c", "task-d"]
    client = FixtureSequenceLLMClient(
        ["default.json", "default.json", "executive_summary.json"]
    )
    agent = WriterAgent(llm_client=client)

    report = await agent.write(report_from_critic, "Assess FAISS for RAG.")

    assert report.data_gaps_acknowledged == ["task-c", "task-d"]
