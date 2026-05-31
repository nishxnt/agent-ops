import shutil
from pathlib import Path

import pytest
from pydantic import ValidationError

from agentops.agents.critic import CriticAgent
from agentops.agents.researcher import ResearchFinding, SourceCitation
from agentops.llm.client import MockLLMClient

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "llm_responses"


class FakeEmbedder:
    def __init__(self, vectors: list[list[float]]) -> None:
        self.vectors = vectors
        self.call_count = 0
        self.sentences: list[str] = []

    def encode(self, sentences: list[str]) -> list[list[float]]:
        self.call_count += 1
        self.sentences = sentences
        return self.vectors[: len(sentences)]


def critic_client(tmp_path: Path, fixture_name: str = "default.json") -> MockLLMClient:
    fixture_dir = FIXTURE_DIR / "critic"
    if fixture_name == "default.json":
        return MockLLMClient(model="qwen2.5:7b", fixture_dir=fixture_dir)

    scenario_dir = tmp_path / fixture_name.removesuffix(".json")
    scenario_dir.mkdir()
    shutil.copyfile(fixture_dir / fixture_name, scenario_dir / "default.json")
    return MockLLMClient(model="qwen2.5:7b", fixture_dir=scenario_dir)


def source() -> SourceCitation:
    return SourceCitation(
        url="https://example.com/source",
        title="Example source",
        relevance_score=0.9,
    )


def finding(
    task_id: str,
    key_facts: list[str],
    confidence_score: float = 0.8,
) -> ResearchFinding:
    return ResearchFinding(
        task_id=task_id,
        summary=f"Summary for {task_id}",
        key_facts=key_facts,
        sources=[source()],
        confidence_score=confidence_score,
        data_gaps=[],
    )


def contradiction_findings(confidence_score: float = 0.8) -> list[ResearchFinding]:
    return [
        finding(
            "task-a",
            [
                "FAISS supports GPU search",
                "FAISS indexes dense vectors",
                "FAISS supports clustering",
            ],
            confidence_score=confidence_score,
        ),
        finding(
            "task-b",
            [
                "FAISS does not support GPU search",
                "Vector search uses embeddings",
                "Dense retrieval ranks neighbors",
            ],
            confidence_score=confidence_score,
        ),
    ]


def contradiction_vectors() -> list[list[float]]:
    return [
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
        [0.99, 0.01, 0.0],
        [0.0, -1.0, 0.0],
        [0.0, 0.0, -1.0],
    ]


@pytest.mark.asyncio
async def test_critic_returns_report_without_contradictions_and_skips_llm(
    tmp_path: Path,
) -> None:
    findings = [
        finding(
            "task-a",
            [
                "FAISS supports vector search",
                "FAISS indexes dense vectors",
                "FAISS supports clustering",
            ],
        )
    ]
    embedder = FakeEmbedder([[1.0, 0.0], [0.99, 0.01], [0.98, 0.02]])
    client = critic_client(tmp_path)
    agent = CriticAgent(llm_client=client, embedder=embedder)

    report = await agent.review(findings)

    assert report.contradictions == []
    assert len(report.verified_facts) == 3
    assert client.invocation_count == 0
    assert embedder.call_count == 1


@pytest.mark.asyncio
async def test_critic_stage_one_flags_opposite_polarity_pair(tmp_path: Path) -> None:
    client = critic_client(tmp_path, "default.json")
    agent = CriticAgent(
        llm_client=client,
        embedder=FakeEmbedder(contradiction_vectors()),
    )

    await agent.review(contradiction_findings())

    assert client.invocation_count == 1


@pytest.mark.asyncio
async def test_critic_stage_two_confirms_candidate(tmp_path: Path) -> None:
    agent = CriticAgent(
        llm_client=critic_client(tmp_path, "contradiction_confirmed.json"),
        embedder=FakeEmbedder(contradiction_vectors()),
    )

    report = await agent.review(contradiction_findings())

    assert len(report.contradictions) == 1
    assert report.contradictions[0].task_id_a == "task-a"
    assert report.contradictions[0].task_id_b == "task-b"


@pytest.mark.asyncio
async def test_critic_blocks_proceed_when_evidence_quality_is_low(
    tmp_path: Path,
) -> None:
    agent = CriticAgent(
        llm_client=critic_client(tmp_path, "contradiction_confirmed.json"),
        embedder=FakeEmbedder(contradiction_vectors()),
    )

    report = await agent.review(contradiction_findings(confidence_score=0.35))

    assert report.overall_evidence_quality < 0.3
    assert report.proceed_recommendation is False


@pytest.mark.asyncio
async def test_critic_populates_low_confidence_items(tmp_path: Path) -> None:
    findings = contradiction_findings(confidence_score=0.8)
    findings[1] = finding("task-b", findings[1].key_facts, confidence_score=0.25)
    agent = CriticAgent(
        llm_client=critic_client(tmp_path),
        embedder=FakeEmbedder(contradiction_vectors()),
    )

    report = await agent.review(findings)

    assert report.low_confidence_items == ["task-b"]


@pytest.mark.asyncio
async def test_critic_raises_validation_error_on_malformed_adjudication(
    tmp_path: Path,
) -> None:
    agent = CriticAgent(
        llm_client=critic_client(tmp_path, "malformed.json"),
        embedder=FakeEmbedder(contradiction_vectors()),
    )

    with pytest.raises(ValidationError):
        await agent.review(contradiction_findings())
