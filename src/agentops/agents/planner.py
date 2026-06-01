"""Planner agent for decomposing a research query into bounded subtasks."""

import json
from typing import Literal

from pydantic import BaseModel, Field

from agentops.config import LLMRole
from agentops.llm.client import LLMClient, get_llm_client
from agentops.llm.models import LLMRequest


class ResearchSubtask(BaseModel):
    """A focused unit of research work."""

    task_id: str
    description: str
    search_keywords: list[str] = Field(min_length=1, max_length=8)
    expected_output_type: Literal["factual", "comparative", "analytical"]


class ResearchPlan(BaseModel):
    """Validated plan emitted by the planner agent."""

    query: str
    subtasks: list[ResearchSubtask] = Field(min_length=1, max_length=5)
    estimated_complexity: Literal["low", "medium", "high"]
    recommended_researcher_count: int = Field(ge=1, le=3)


class PlannerAgent:
    """LLM-backed planner for producing structured research plans."""

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self.llm_client = llm_client or get_llm_client(LLMRole.GENERATION)

    async def plan(self, query: str) -> ResearchPlan:
        """Create and validate a structured research plan for a user query."""

        request = LLMRequest(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a planning agent. Return only JSON matching "
                        "this ResearchPlan schema: query string; subtasks array "
                        "of 1-5 objects with task_id string, description string, "
                        "search_keywords array of 1-8 strings, and "
                        "expected_output_type one of factual, comparative, "
                        "analytical; estimated_complexity one of low, medium, "
                        "high; recommended_researcher_count integer from 1 to 3."
                    ),
                },
                {"role": "user", "content": query},
            ],
            model=self.llm_client.model,
            agent_type="planner",
        )
        response = await self.llm_client.complete(request)
        return ResearchPlan.model_validate(json.loads(response.content))
