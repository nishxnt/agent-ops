import json
from pathlib import Path

import pytest
from src.evaluation.engine import AttackEvaluationInput, MetricResult

from agentops.agents.critic import CriticAgent, CriticReport
from agentops.agents.planner import PlannerAgent, ResearchPlan
from agentops.agents.quality_gate import QualityDecision, QualityGateAgent
from agentops.agents.researcher import ResearcherAgent, ResearchFinding
from agentops.agents.writer import ResearchReport, WriterAgent
from agentops.dev.search_cache import SearchResult
from agentops.llm.client import LLMClient, MockLLMClient
from agentops.llm.models import LLMRequest, LLMResponse

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


class FakeEmbedder:
    def __init__(self, vectors: list[list[float]]) -> None:
        self.vectors = vectors

    def encode(self, sentences: list[str]) -> list[list[float]]:
        return self.vectors[: len(sentences)]


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


class FakeMetric:
    def __init__(self, name: str, score: float) -> None:
        self.name = name
        self.judge_model = "fake-model"
        self.judge_version = "fake-v1"
        self.score_value = score

    async def score(self, attack: AttackEvaluationInput) -> MetricResult:
        return MetricResult(
            attack_id=attack.attack_id,
            metric_name=self.name,
            score=self.score_value,
            evidence={"attack_id": attack.attack_id},
            judge_model=self.judge_model,
            judge_version=self.judge_version,
        )


async def _run_phase1_chain(
    *,
    faithfulness_score: float,
    revision_count: int = 0,
) -> tuple[
    ResearchPlan,
    list[ResearchFinding],
    CriticReport,
    ResearchReport,
    QualityDecision,
    SpySearchClient,
]:
    query = "What is FAISS?"
    planner = PlannerAgent(
        llm_client=MockLLMClient(
            model="qwen2.5:7b",
            fixture_dir=FIXTURE_DIR / "planner",
        )
    )
    search_client = SpySearchClient()
    researcher = ResearcherAgent(
        llm_client=MockLLMClient(
            model="qwen2.5:7b",
            fixture_dir=FIXTURE_DIR / "researcher",
        ),
        search_client=search_client,  # type: ignore[arg-type]
    )
    critic = CriticAgent(
        llm_client=MockLLMClient(
            model="qwen2.5:7b",
            fixture_dir=FIXTURE_DIR / "critic",
        ),
        embedder=FakeEmbedder([[1.0, 0.0], [0.0, 1.0], [-1.0, 0.0]]),
    )

    plan = await planner.plan(query)
    findings = [await researcher.research(subtask) for subtask in plan.subtasks]
    critic_report = await critic.review(findings)
    writer = WriterAgent(
        llm_client=FixtureSequenceLLMClient(
            ["default.json"] * len(plan.subtasks) + ["executive_summary.json"]
        )
    )
    report = await writer.write(critic_report, query)
    report.revision_count = revision_count
    quality_gate = QualityGateAgent(
        faithfulness=FakeMetric("faithfulness", faithfulness_score),
        hallucination=FakeMetric("hallucination", 0.05),
    )
    decision = await quality_gate.evaluate(
        report,
        critic_report.verified_facts,
        query,
    )

    return plan, findings, critic_report, report, decision, search_client


@pytest.mark.asyncio
async def test_phase1_happy_path_pass() -> None:
    plan, findings, critic_report, report, decision, search_client = (
        await _run_phase1_chain(faithfulness_score=0.9)
    )

    assert isinstance(plan, ResearchPlan)
    assert all(isinstance(finding, ResearchFinding) for finding in findings)
    assert isinstance(critic_report, CriticReport)
    assert isinstance(report, ResearchReport)
    assert isinstance(decision, QualityDecision)
    assert decision.decision == "PASS"
    assert len(report.sections) == len(plan.subtasks)
    assert search_client.call_count == len(plan.subtasks)


@pytest.mark.asyncio
async def test_phase1_revision_path_returns_revision_decision() -> None:
    *_, decision, _search_client = await _run_phase1_chain(
        faithfulness_score=0.5,
        revision_count=0,
    )

    assert decision.decision == "REVISION"
    assert decision.revision_instruction
