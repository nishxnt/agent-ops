import json
from pathlib import Path

import pytest
from src.evaluation.engine import AttackEvaluationInput, MetricResult

from agentops.agents.critic import CriticAgent
from agentops.agents.planner import PlannerAgent
from agentops.agents.quality_gate import QualityGateAgent
from agentops.agents.researcher import ResearcherAgent
from agentops.agents.writer import WriterAgent
from agentops.dev.search_cache import SearchResult
from agentops.llm.client import LLMClient, MockLLMClient
from agentops.llm.models import LLMRequest, LLMResponse
from agentops.orchestration.graph import PipelineOrchestrator
from agentops.orchestration.nodes import write_node
from agentops.orchestration.state import PipelineStatus, initial_state

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "llm_responses"


class SpySearchClient:
    def __init__(self) -> None:
        self.call_count = 0
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

    async def complete(self, request: LLMRequest) -> LLMResponse:
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
            judge_model=self.judge_model,
            judge_version=self.judge_version,
        )


class StepwiseMetric:
    def __init__(self, name: str, scores: list[float]) -> None:
        self.name = name
        self.judge_model = "fake-model"
        self.judge_version = "fake-v1"
        self.scores = scores
        self.call_count = 0

    async def score(self, attack: AttackEvaluationInput) -> MetricResult:
        idx = min(self.call_count, len(self.scores) - 1)
        self.call_count += 1
        return MetricResult(
            attack_id=attack.attack_id,
            metric_name=self.name,
            score=self.scores[idx],
            judge_model=self.judge_model,
            judge_version=self.judge_version,
        )


class CountingWriter:
    def __init__(self, writer: WriterAgent) -> None:
        self.writer = writer
        self.write_call_count = 0

    async def write(self, *args: object, **kwargs: object) -> object:
        self.write_call_count += 1
        return await self.writer.write(*args, **kwargs)  # type: ignore[arg-type]


def _planner() -> PlannerAgent:
    return PlannerAgent(
        llm_client=MockLLMClient(
            model="qwen2.5:7b",
            fixture_dir=FIXTURE_DIR / "planner",
        )
    )


def _researcher() -> ResearcherAgent:
    return ResearcherAgent(
        llm_client=MockLLMClient(
            model="qwen2.5:7b",
            fixture_dir=FIXTURE_DIR / "researcher",
        ),
        search_client=SpySearchClient(),  # type: ignore[arg-type]
    )


def _critic() -> CriticAgent:
    return CriticAgent(
        llm_client=MockLLMClient(
            model="qwen2.5:7b",
            fixture_dir=FIXTURE_DIR / "critic",
        ),
        embedder=FakeEmbedder([[1.0, 0.0], [0.0, 1.0], [-1.0, 0.0]]),
    )


def _writer(max_invocations: int = 1) -> WriterAgent:
    return WriterAgent(
        llm_client=FixtureSequenceLLMClient(
            ["default.json", "executive_summary.json"] * max_invocations
        )
    )


def _orchestrator(
    *,
    faithfulness: FakeMetric | StepwiseMetric,
    hallucination: FakeMetric | StepwiseMetric | None = None,
    writer: WriterAgent | CountingWriter | None = None,
) -> PipelineOrchestrator:
    return PipelineOrchestrator(
        planner=_planner(),
        researcher=_researcher(),
        critic=_critic(),
        writer=writer or _writer(),
        quality_gate=QualityGateAgent(
            faithfulness=faithfulness,
            hallucination=hallucination or FakeMetric("hallucination", 0.05),
        ),
    )


def test_graph_compiles() -> None:
    orchestrator = _orchestrator(faithfulness=FakeMetric("faithfulness", 0.9))

    assert orchestrator.graph is not None


@pytest.mark.asyncio
async def test_happy_path_completes_with_done_status() -> None:
    orchestrator = _orchestrator(faithfulness=FakeMetric("faithfulness", 0.9))

    state = await orchestrator.run("What is FAISS?")

    assert state["pipeline_status"] == PipelineStatus.DONE
    assert state["quality_decision"] is not None
    assert state["quality_decision"].decision == "PASS"
    assert state["plan"] is not None
    assert state["report"] is not None
    assert state["revision_count"] == 0


@pytest.mark.asyncio
async def test_revision_loop_passes_after_one_revision() -> None:
    counting_writer = CountingWriter(_writer(max_invocations=2))
    orchestrator = _orchestrator(
        faithfulness=StepwiseMetric("faithfulness", [0.5, 0.5, 0.9, 0.9]),
        writer=counting_writer,
    )

    state = await orchestrator.run("What is FAISS?")

    assert state["revision_count"] == 1
    assert state["quality_decision"] is not None
    assert state["quality_decision"].decision == "PASS"
    assert counting_writer.write_call_count == 2


@pytest.mark.asyncio
async def test_fail_when_max_revisions_exhausted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QUALITY_GATE_MAX_REVISIONS", "1")
    counting_writer = CountingWriter(_writer(max_invocations=2))
    orchestrator = _orchestrator(
        faithfulness=StepwiseMetric("faithfulness", [0.5]),
        writer=counting_writer,
    )

    state = await orchestrator.run("What is FAISS?")

    assert state["pipeline_status"] == PipelineStatus.FAILED
    assert state["quality_decision"] is not None
    assert state["quality_decision"].decision == "FAIL"
    assert counting_writer.write_call_count == 2


def test_initial_state_defaults() -> None:
    state = initial_state("hello")

    assert state["run_id"]
    assert state["query"] == "hello"
    assert state["plan"] is None
    assert state["findings"] == []
    assert state["revision_count"] == 0
    assert state["pipeline_status"] == PipelineStatus.PLANNING


@pytest.mark.asyncio
async def test_write_node_propagates_revision_count_into_report() -> None:
    setup_orchestrator = _orchestrator(faithfulness=FakeMetric("faithfulness", 0.9))
    state = await setup_orchestrator.run("What is FAISS?")
    state["revision_count"] = 2

    updated = await write_node(state, writer=_writer())

    assert updated["report"] is not None
    assert updated["report"].revision_count == 2
