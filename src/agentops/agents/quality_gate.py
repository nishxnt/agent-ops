"""Quality gate backed by RogueLLM evaluation metrics."""

import importlib
from typing import Any, Literal, Protocol, cast

from pydantic import BaseModel, Field

from agentops.agents.critic import VerifiedFact
from agentops.agents.writer import ResearchReport
from agentops.config import AgentOpsMode, LLMRole, Settings, get_settings

try:
    _faithfulness_module = importlib.import_module(
        "src.evaluation.metrics.faithfulness"
    )
    _hallucination_module = importlib.import_module(
        "src.evaluation.metrics.hallucination"
    )
except ModuleNotFoundError:
    FaithfulnessMetric: Any = None
    HallucinationMetric: Any = None
else:
    FaithfulnessMetric = cast(Any, _faithfulness_module).FaithfulnessMetric
    HallucinationMetric = cast(Any, _hallucination_module).HallucinationMetric


class AttackEvaluationInput(BaseModel):
    attack_id: str
    owasp_category: str
    attack_prompt: str
    target_response: str
    retrieved_chunks: list[str]


class MetricResult(BaseModel):
    attack_id: str
    metric_name: str
    score: float | None
    judge_model: str
    judge_version: str
    skipped: bool = False
    evidence: dict[str, Any] = Field(default_factory=dict)


class EvaluationMetric(Protocol):
    async def score(self, attack: AttackEvaluationInput) -> MetricResult: ...


class FlaggedClaim(BaseModel):
    """A report unit whose quality metric violated a gate threshold."""

    section_id: str
    metric_name: Literal["faithfulness", "hallucination"]
    score: float
    threshold: float
    evidence: dict[str, Any] = Field(default_factory=dict)


class QualityDecision(BaseModel):
    """Quality gate decision for a generated report."""

    decision: Literal["PASS", "REVISION", "FAIL"]
    faithfulness_score: float
    hallucination_score: float
    section_scores: dict[str, dict[str, float | None]]
    flagged_claims: list[FlaggedClaim]
    revision_instruction: str | None = None


class _FixedScoreMetric:
    """Mock-mode metric stub. Constant score per call."""

    def __init__(self, name: str, score: float) -> None:
        self.name = name
        self.judge_model = "mock-stub"
        self.judge_version = "v1"
        self._score = score

    async def score(self, attack: AttackEvaluationInput) -> MetricResult:
        return MetricResult(
            attack_id=attack.attack_id,
            metric_name=self.name,
            score=self._score,
            judge_model=self.judge_model,
            judge_version=self.judge_version,
        )


class QualityGateAgent:
    """Evaluate report quality with RogueLLM faithfulness and hallucination metrics."""

    FAITHFULNESS_THRESHOLD = 0.75
    HALLUCINATION_THRESHOLD = 0.20

    def __init__(
        self,
        faithfulness: EvaluationMetric | None = None,
        hallucination: EvaluationMetric | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        eval_model = self.settings.model_for(LLMRole.EVALUATION)
        if self.settings.mode == AgentOpsMode.MOCK:
            faithfulness = faithfulness or _FixedScoreMetric("faithfulness", 0.9)
            hallucination = hallucination or _FixedScoreMetric("hallucination", 0.05)
        else:
            if FaithfulnessMetric is None or HallucinationMetric is None:
                msg = "RogueLLM metrics are required outside MOCK mode."
                raise RuntimeError(msg)
            faithfulness = faithfulness or FaithfulnessMetric(judge_model=eval_model)
            hallucination = hallucination or HallucinationMetric(judge_model=eval_model)
        self.faithfulness = faithfulness
        self.hallucination = hallucination
        self.max_revisions = self.settings.quality_gate_max_revisions

    async def evaluate(
        self,
        report: ResearchReport,
        verified_facts: list[VerifiedFact],
        query: str,
    ) -> QualityDecision:
        """Evaluate every report section plus executive summary."""

        inputs = _evaluation_inputs(report, verified_facts, query)
        faithfulness_results: list[MetricResult] = []
        hallucination_results: list[MetricResult] = []

        for evaluation_input in inputs:
            faithfulness_results.append(await self.faithfulness.score(evaluation_input))
            hallucination_results.append(
                await self.hallucination.score(evaluation_input)
            )

        faithfulness_score = _aggregate_score(
            faithfulness_results, default_when_all_skipped=0.0
        )
        hallucination_score = _aggregate_score(
            hallucination_results, default_when_all_skipped=1.0
        )
        section_scores = _section_scores(faithfulness_results, hallucination_results)
        flagged_claims = _flagged_claims(faithfulness_results, hallucination_results)

        if (
            faithfulness_score >= self.FAITHFULNESS_THRESHOLD
            and hallucination_score <= self.HALLUCINATION_THRESHOLD
        ):
            decision: Literal["PASS", "REVISION", "FAIL"] = "PASS"
            revision_instruction = None
        elif report.revision_count < self.max_revisions:
            decision = "REVISION"
            revision_instruction = _revision_instruction(flagged_claims)
        else:
            decision = "FAIL"
            revision_instruction = None

        return QualityDecision(
            decision=decision,
            faithfulness_score=faithfulness_score,
            hallucination_score=hallucination_score,
            section_scores=section_scores,
            flagged_claims=flagged_claims,
            revision_instruction=revision_instruction,
        )


def _evaluation_inputs(
    report: ResearchReport,
    verified_facts: list[VerifiedFact],
    query: str,
) -> list[AttackEvaluationInput]:
    inputs = [
        AttackEvaluationInput(
            attack_id=section.section_id,
            owasp_category="agentops_report",
            attack_prompt=query,
            target_response=section.content,
            retrieved_chunks=[
                fact.text
                for fact in verified_facts
                if section.section_id in fact.source_task_ids
            ],
        )
        for section in report.sections
    ]
    inputs.append(
        AttackEvaluationInput(
            attack_id="executive_summary",
            owasp_category="agentops_report",
            attack_prompt=query,
            target_response=report.executive_summary,
            retrieved_chunks=[fact.text for fact in verified_facts],
        )
    )
    return inputs


def _aggregate_score(
    results: list[MetricResult],
    *,
    default_when_all_skipped: float,
) -> float:
    scores = [
        float(result.score)
        for result in results
        if not result.skipped and result.score is not None
    ]
    if not scores:
        return default_when_all_skipped
    return sum(scores) / len(scores)


def _section_scores(
    faithfulness_results: list[MetricResult],
    hallucination_results: list[MetricResult],
) -> dict[str, dict[str, float | None]]:
    scores: dict[str, dict[str, float | None]] = {}
    for result in faithfulness_results:
        scores.setdefault(result.attack_id, {})["faithfulness"] = result.score
    for result in hallucination_results:
        scores.setdefault(result.attack_id, {})["hallucination"] = result.score
    return scores


def _flagged_claims(
    faithfulness_results: list[MetricResult],
    hallucination_results: list[MetricResult],
) -> list[FlaggedClaim]:
    flagged: list[FlaggedClaim] = []
    for result in faithfulness_results:
        if result.skipped or result.score is None:
            continue
        if result.score < QualityGateAgent.FAITHFULNESS_THRESHOLD:
            flagged.append(
                FlaggedClaim(
                    section_id=result.attack_id,
                    metric_name="faithfulness",
                    score=float(result.score),
                    threshold=QualityGateAgent.FAITHFULNESS_THRESHOLD,
                    evidence=result.evidence,
                )
            )
    for result in hallucination_results:
        if result.skipped or result.score is None:
            continue
        if result.score > QualityGateAgent.HALLUCINATION_THRESHOLD:
            flagged.append(
                FlaggedClaim(
                    section_id=result.attack_id,
                    metric_name="hallucination",
                    score=float(result.score),
                    threshold=QualityGateAgent.HALLUCINATION_THRESHOLD,
                    evidence=result.evidence,
                )
            )
    return flagged


def _revision_instruction(flagged_claims: list[FlaggedClaim]) -> str:
    if not flagged_claims:
        return (
            "Revise the report to improve faithfulness and reduce "
            "hallucination risk."
        )
    lines = ["Revise flagged report units:"]
    lines.extend(
        (
            f"- {claim.section_id}: {claim.metric_name} score {claim.score:.3f} "
            f"violated threshold {claim.threshold:.3f}"
        )
        for claim in flagged_claims
    )
    return "\n".join(lines)
