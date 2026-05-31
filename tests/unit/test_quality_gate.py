import pytest
from src.evaluation.engine import AttackEvaluationInput, MetricResult

from agentops.agents.critic import VerifiedFact
from agentops.agents.quality_gate import QualityGateAgent
from agentops.agents.researcher import SourceCitation
from agentops.agents.writer import ReportSection, ResearchReport


class FakeMetric:
    def __init__(
        self,
        name: str,
        score: float,
        skipped_attack_ids: set[str] | None = None,
    ) -> None:
        self.name = name
        self.judge_model = "fake-model"
        self.judge_version = "fake-v1"
        self.score_value = score
        self.skipped_attack_ids = skipped_attack_ids or set()
        self.call_count = 0
        self.scored_attack_ids: list[str] = []

    async def score(self, attack: AttackEvaluationInput) -> MetricResult:
        self.call_count += 1
        self.scored_attack_ids.append(attack.attack_id)
        if attack.attack_id in self.skipped_attack_ids:
            return MetricResult(
                attack_id=attack.attack_id,
                metric_name=self.name,
                score=None,
                skipped=True,
                reason="fake_skip",
                judge_model=self.judge_model,
                judge_version=self.judge_version,
            )
        return MetricResult(
            attack_id=attack.attack_id,
            metric_name=self.name,
            score=self.score_value,
            evidence={"attack_id": attack.attack_id},
            judge_model=self.judge_model,
            judge_version=self.judge_version,
        )


class PerAttackMetric(FakeMetric):
    def __init__(
        self,
        name: str,
        score: float,
        score_overrides: dict[str, float],
    ) -> None:
        super().__init__(name=name, score=score)
        self.score_overrides = score_overrides

    async def score(self, attack: AttackEvaluationInput) -> MetricResult:
        self.call_count += 1
        self.scored_attack_ids.append(attack.attack_id)
        return MetricResult(
            attack_id=attack.attack_id,
            metric_name=self.name,
            score=self.score_overrides.get(attack.attack_id, self.score_value),
            evidence={"attack_id": attack.attack_id},
            judge_model=self.judge_model,
            judge_version=self.judge_version,
        )


def source() -> SourceCitation:
    return SourceCitation(
        url="https://example.com/source",
        title="Example source",
        relevance_score=0.9,
    )


def verified_facts() -> list[VerifiedFact]:
    return [
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
    ]


def report(revision_count: int = 0) -> ResearchReport:
    return ResearchReport(
        title="Assess FAISS for RAG.",
        executive_summary="FAISS is useful for dense-vector retrieval workflows.",
        sections=[
            ReportSection(
                section_id="task-a",
                heading="Vector Search",
                content="FAISS supports dense vector search and indexing.",
                supporting_fact_ids=["fact-1", "fact-2"],
                confidence=0.85,
            ),
            ReportSection(
                section_id="task-b",
                heading="Operations",
                content="Enterprise RAG needs observability.",
                supporting_fact_ids=["fact-3"],
                confidence=0.6,
            ),
        ],
        confidence_bands={"task-a": 0.85, "task-b": 0.6},
        data_gaps_acknowledged=[],
        revision_count=revision_count,
    )


@pytest.mark.asyncio
async def test_quality_gate_pass_when_scores_clear_thresholds() -> None:
    gate = QualityGateAgent(
        faithfulness=FakeMetric("faithfulness", 0.9),
        hallucination=FakeMetric("hallucination", 0.05),
    )

    decision = await gate.evaluate(report(), verified_facts(), "Assess FAISS.")

    assert decision.decision == "PASS"
    assert decision.revision_instruction is None
    assert decision.flagged_claims == []


@pytest.mark.asyncio
async def test_quality_gate_revision_when_under_max_revisions() -> None:
    gate = QualityGateAgent(
        faithfulness=FakeMetric("faithfulness", 0.5),
        hallucination=FakeMetric("hallucination", 0.05),
    )

    decision = await gate.evaluate(
        report(revision_count=0), verified_facts(), "Assess FAISS."
    )

    assert decision.decision == "REVISION"
    assert decision.revision_instruction is not None
    assert "task-a" in decision.revision_instruction


@pytest.mark.asyncio
async def test_quality_gate_fail_when_max_revisions_reached() -> None:
    gate = QualityGateAgent(
        faithfulness=FakeMetric("faithfulness", 0.5),
        hallucination=FakeMetric("hallucination", 0.05),
    )

    decision = await gate.evaluate(
        report(revision_count=2), verified_facts(), "Assess FAISS."
    )

    assert decision.decision == "FAIL"
    assert decision.revision_instruction is None


@pytest.mark.asyncio
async def test_quality_gate_flags_only_low_scoring_inputs() -> None:
    gate = QualityGateAgent(
        faithfulness=PerAttackMetric(
            "faithfulness",
            0.9,
            {"task-b": 0.5, "executive_summary": 0.5},
        ),
        hallucination=FakeMetric("hallucination", 0.05),
    )

    decision = await gate.evaluate(report(), verified_facts(), "Assess FAISS.")

    flagged_section_ids = {claim.section_id for claim in decision.flagged_claims}
    assert "task-b" in flagged_section_ids
    assert "executive_summary" in flagged_section_ids
    assert "task-a" not in flagged_section_ids


def test_quality_gate_default_judge_models_use_evaluation_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENTOPS_MODE", "local")
    monkeypatch.setenv("LOCAL_GENERATION_MODEL", "qwen2.5:7b")
    monkeypatch.setenv("LOCAL_EVALUATION_MODEL", "llama3.1:8b")

    gate = QualityGateAgent()

    assert gate.faithfulness.judge_model == "llama3.1:8b"
    assert gate.hallucination.judge_model == "llama3.1:8b"
    assert gate.faithfulness.judge_model != "qwen2.5:7b"


@pytest.mark.asyncio
async def test_quality_gate_calls_each_metric_for_every_input() -> None:
    faithfulness = FakeMetric("faithfulness", 0.9)
    hallucination = FakeMetric("hallucination", 0.05)
    gate = QualityGateAgent(
        faithfulness=faithfulness,
        hallucination=hallucination,
    )

    evaluated_report = report()
    await gate.evaluate(evaluated_report, verified_facts(), "Assess FAISS.")

    expected_calls = len(evaluated_report.sections) + 1
    assert faithfulness.call_count == expected_calls
    assert hallucination.call_count == expected_calls
