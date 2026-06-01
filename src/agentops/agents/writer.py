"""Writer agent for section-by-section report generation."""

import json
from collections import defaultdict
from typing import Any

from pydantic import BaseModel, Field

from agentops.agents.critic import CriticReport, VerifiedFact
from agentops.config import LLMRole
from agentops.llm.client import LLMClient, get_llm_client
from agentops.llm.models import LLMRequest


class ReportSection(BaseModel):
    """A report section grounded in critic-verified facts."""

    section_id: str
    heading: str
    content: str
    supporting_fact_ids: list[str]
    confidence: float = Field(ge=0.0, le=1.0)


class ResearchReport(BaseModel):
    """Final report assembled by the writer agent."""

    title: str
    executive_summary: str = Field(max_length=1200)
    sections: list[ReportSection]
    confidence_bands: dict[str, float]
    data_gaps_acknowledged: list[str]
    revision_count: int = Field(ge=0, le=2)


class _ExecutiveSummary(BaseModel):
    executive_summary: str = Field(max_length=1200)


class WriterAgent:
    """LLM-backed writer that constructs reports one section at a time."""

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self.llm_client = llm_client or get_llm_client(LLMRole.GENERATION)

    async def write(self, critic_report: CriticReport, query: str) -> ResearchReport:
        """Generate a report with exactly one LLM call per section plus summary."""

        fact_records = _fact_records(critic_report.verified_facts)
        grouped_facts = _group_by_primary_task(fact_records)
        sections: list[ReportSection] = []

        for task_id, facts in grouped_facts.items():
            sections.append(await self._write_section(task_id, facts))

        executive_summary = await self._write_executive_summary(query, sections)
        confidence_bands = {
            section.section_id: _section_confidence(section, fact_records)
            for section in sections
        }

        return ResearchReport(
            title=query,
            executive_summary=executive_summary.executive_summary,
            sections=sections,
            confidence_bands=confidence_bands,
            data_gaps_acknowledged=critic_report.low_confidence_items,
            revision_count=0,
        )

    async def _write_section(
        self,
        task_id: str,
        facts: list[dict[str, Any]],
    ) -> ReportSection:
        request = LLMRequest(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You write one grounded research report section. Return "
                        "only ReportSection JSON with section_id, heading, "
                        "content, supporting_fact_ids, and confidence."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "section_id": task_id,
                            "heading": f"Findings from {task_id}",
                            "facts": facts,
                        },
                        sort_keys=True,
                    ),
                },
            ],
            model=self.llm_client.model,
            agent_type="writer",
        )
        response = await self.llm_client.complete(request)
        return ReportSection.model_validate(json.loads(response.content))

    async def _write_executive_summary(
        self,
        query: str,
        sections: list[ReportSection],
    ) -> _ExecutiveSummary:
        request = LLMRequest(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You write the executive summary for an assembled "
                        "research report. Return only JSON with "
                        "executive_summary."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "query": query,
                            "sections": [section.model_dump() for section in sections],
                        },
                        sort_keys=True,
                    ),
                },
            ],
            model=self.llm_client.model,
            agent_type="writer",
        )
        response = await self.llm_client.complete(request)
        return _ExecutiveSummary.model_validate(json.loads(response.content))


def _fact_records(verified_facts: list[VerifiedFact]) -> list[dict[str, Any]]:
    return [
        {
            "fact_id": f"fact-{index + 1}",
            "text": fact.text,
            "source_task_ids": fact.source_task_ids,
            "confidence": fact.confidence,
        }
        for index, fact in enumerate(verified_facts)
    ]


def _group_by_primary_task(
    fact_records: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for fact in fact_records:
        source_task_ids = cast_list(fact["source_task_ids"])
        primary_task_id = source_task_ids[0] if source_task_ids else "unattributed"
        grouped[primary_task_id].append(fact)
    return dict(grouped)


def _section_confidence(
    section: ReportSection,
    fact_records: list[dict[str, Any]],
) -> float:
    confidence_by_id = {
        str(fact["fact_id"]): float(fact["confidence"]) for fact in fact_records
    }
    confidences = [
        confidence_by_id[fact_id]
        for fact_id in section.supporting_fact_ids
        if fact_id in confidence_by_id
    ]
    if not confidences:
        return section.confidence
    return sum(confidences) / len(confidences)


def cast_list(value: object) -> list[str]:
    return [str(item) for item in value] if isinstance(value, list) else []
