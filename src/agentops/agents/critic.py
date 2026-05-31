"""Critic agent for evidence review and contradiction detection."""

import json
import math
import re
from collections.abc import Iterable
from typing import Protocol, cast

from pydantic import BaseModel, Field

from agentops.agents.researcher import ResearchFinding, SourceCitation
from agentops.config import LLMRole
from agentops.llm.client import LLMClient, get_llm_client
from agentops.llm.models import LLMRequest

NEGATION_TOKENS = {
    "not",
    "no",
    "never",
    "without",
    "cannot",
    "doesn't",
    "isn't",
    "wasn't",
    "false",
}


class Embedder(Protocol):
    """Minimal embedding interface used by the critic."""

    def encode(self, sentences: list[str]) -> object:
        """Encode a batch of sentences."""


class VerifiedFact(BaseModel):
    """A fact that survived contradiction review."""

    text: str
    source_task_ids: list[str]
    supporting_sources: list[SourceCitation]
    confidence: float = Field(ge=0.0, le=1.0)


class Contradiction(BaseModel):
    """A confirmed contradiction between two facts."""

    fact_a: str
    fact_b: str
    task_id_a: str
    task_id_b: str
    explanation: str


class CriticReport(BaseModel):
    """Structured output from critic review."""

    verified_facts: list[VerifiedFact]
    contradictions: list[Contradiction]
    low_confidence_items: list[str]
    overall_evidence_quality: float = Field(ge=0.0, le=1.0)
    proceed_recommendation: bool


class _Adjudication(BaseModel):
    is_contradiction: bool
    explanation: str


class _FactCandidate(BaseModel):
    text: str
    task_id: str
    sources: list[SourceCitation]
    confidence: float = Field(ge=0.0, le=1.0)


class CriticAgent:
    """Two-stage critic: deterministic candidate floor, then LLM adjudication."""

    def __init__(
        self,
        llm_client: LLMClient | None = None,
        embedder: Embedder | None = None,
    ) -> None:
        self.llm_client = llm_client or get_llm_client(LLMRole.GENERATION)
        self.embedder = embedder or _default_embedder()

    async def review(self, findings: list[ResearchFinding]) -> CriticReport:
        """Review findings and return verified facts plus contradictions."""

        facts = _flatten_facts(findings)
        candidates = _stage_one_candidates(facts, self.embedder)
        contradictions: list[Contradiction] = []

        for index_a, index_b in candidates:
            fact_a = facts[index_a]
            fact_b = facts[index_b]
            adjudication = await self._adjudicate(fact_a, fact_b)
            if adjudication.is_contradiction:
                contradictions.append(
                    Contradiction(
                        fact_a=fact_a.text,
                        fact_b=fact_b.text,
                        task_id_a=fact_a.task_id,
                        task_id_b=fact_b.task_id,
                        explanation=adjudication.explanation,
                    )
                )

        contradicted_texts = {
            fact_text
            for contradiction in contradictions
            for fact_text in (contradiction.fact_a, contradiction.fact_b)
        }
        verified_facts = [
            VerifiedFact(
                text=fact.text,
                source_task_ids=[fact.task_id],
                supporting_sources=fact.sources,
                confidence=fact.confidence,
            )
            for fact in facts
            if fact.text not in contradicted_texts
        ]
        low_confidence_items = [
            finding.task_id for finding in findings if finding.confidence_score < 0.4
        ]
        mean_confidence = (
            sum(finding.confidence_score for finding in findings) / len(findings)
            if findings
            else 0.0
        )
        overall_evidence_quality = _clamp(mean_confidence - 0.1 * len(contradictions))

        return CriticReport(
            verified_facts=verified_facts,
            contradictions=contradictions,
            low_confidence_items=low_confidence_items,
            overall_evidence_quality=overall_evidence_quality,
            proceed_recommendation=overall_evidence_quality >= 0.3,
        )

    async def _adjudicate(
        self,
        fact_a: _FactCandidate,
        fact_b: _FactCandidate,
    ) -> _Adjudication:
        request = LLMRequest(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You adjudicate possible contradictions. Return only "
                        "JSON with is_contradiction boolean and explanation "
                        "string."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "fact_a": fact_a.text,
                            "fact_b": fact_b.text,
                            "task_id_a": fact_a.task_id,
                            "task_id_b": fact_b.task_id,
                        },
                        sort_keys=True,
                    ),
                },
            ],
            model=self.llm_client.model,
        )
        response = await self.llm_client.complete(request)
        return _Adjudication.model_validate(json.loads(response.content))


def _default_embedder() -> Embedder:
    from sentence_transformers import SentenceTransformer

    return cast(Embedder, SentenceTransformer("all-MiniLM-L6-v2"))


def _flatten_facts(findings: list[ResearchFinding]) -> list[_FactCandidate]:
    return [
        _FactCandidate(
            text=fact,
            task_id=finding.task_id,
            sources=finding.sources,
            confidence=finding.confidence_score,
        )
        for finding in findings
        for fact in finding.key_facts
    ]


def _stage_one_candidates(
    facts: list[_FactCandidate],
    embedder: Embedder,
) -> list[tuple[int, int]]:
    if len(facts) < 2:
        return []

    embeddings = _as_vectors(embedder.encode([fact.text for fact in facts]))
    candidates: list[tuple[int, int]] = []
    for index_a in range(len(facts)):
        for index_b in range(index_a + 1, len(facts)):
            if _cosine_similarity(
                embeddings[index_a], embeddings[index_b]
            ) > 0.85 and _opposite_polarity(facts[index_a].text, facts[index_b].text):
                candidates.append((index_a, index_b))
    return candidates


def _as_vectors(raw_embeddings: object) -> list[list[float]]:
    return [
        [float(value) for value in embedding]
        for embedding in cast(Iterable[Iterable[float]], raw_embeddings)
    ]


def _cosine_similarity(vector_a: list[float], vector_b: list[float]) -> float:
    dot_product = sum(a * b for a, b in zip(vector_a, vector_b, strict=True))
    norm_a = math.sqrt(sum(value * value for value in vector_a))
    norm_b = math.sqrt(sum(value * value for value in vector_b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot_product / (norm_a * norm_b)


def _opposite_polarity(text_a: str, text_b: str) -> bool:
    return _contains_negation(text_a) != _contains_negation(text_b)


def _contains_negation(text: str) -> bool:
    lowered = text.lower()
    return any(
        re.search(rf"(?<!\w){re.escape(token)}(?!\w)", lowered) is not None
        for token in NEGATION_TOKENS
    )


def _clamp(value: float) -> float:
    return min(max(value, 0.0), 1.0)
