"""Researcher agent for producing structured findings from search evidence."""

import json
from typing import Any

from pydantic import BaseModel, Field

from agentops.agents.planner import ResearchSubtask
from agentops.config import LLMRole
from agentops.dev.search_cache import CachedSearchClient, SearchResult
from agentops.llm.client import LLMClient, get_llm_client
from agentops.llm.models import LLMRequest


class SourceCitation(BaseModel):
    """A cited source supporting a research finding."""

    url: str
    title: str
    relevance_score: float = Field(ge=0.0, le=1.0)


class ResearchFinding(BaseModel):
    """Validated research finding emitted by the researcher agent."""

    task_id: str
    summary: str = Field(max_length=2000)
    key_facts: list[str] = Field(min_length=3, max_length=7)
    sources: list[SourceCitation]
    confidence_score: float = Field(ge=0.0, le=1.0)
    data_gaps: list[str]


class ResearcherAgent:
    """LLM-backed researcher that summarizes cached search evidence."""

    def __init__(
        self,
        llm_client: LLMClient | None = None,
        search_client: CachedSearchClient | None = None,
    ) -> None:
        self.llm_client = llm_client or get_llm_client(LLMRole.GENERATION)
        self.search_client = search_client or CachedSearchClient()

    async def research(self, subtask: ResearchSubtask) -> ResearchFinding:
        """Search for a subtask and validate the LLM-produced finding."""

        query = " ".join(subtask.search_keywords)
        search_results = await self.search_client.search(query)
        request = LLMRequest(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a research agent. Return only JSON matching "
                        "this ResearchFinding schema: task_id string; summary "
                        "string no longer than 2000 characters; key_facts array "
                        "of 3-7 strings; sources array with url, title, and "
                        "relevance_score from 0.0 to 1.0; confidence_score from "
                        "0.0 to 1.0; data_gaps array of strings."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "task_id": subtask.task_id,
                            "description": subtask.description,
                            "expected_output_type": subtask.expected_output_type,
                            "search_results": [
                                _search_result_payload(result)
                                for result in search_results
                            ],
                        },
                        sort_keys=True,
                    ),
                },
            ],
            model=self.llm_client.model,
            agent_type="researcher",
        )
        response = await self.llm_client.complete(request)
        return ResearchFinding.model_validate(json.loads(response.content))


def _search_result_payload(result: SearchResult) -> dict[str, Any]:
    return result.model_dump()
