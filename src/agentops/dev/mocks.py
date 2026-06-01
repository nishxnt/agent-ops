"""Mock-mode infrastructure smoke pipeline."""

from agentops.config import AgentOpsMode, LLMRole, get_settings
from agentops.dev.search_cache import CachedSearchClient
from agentops.llm.client import get_llm_client
from agentops.llm.models import LLMRequest, LLMResponse


async def mock_pipeline_run(query: str) -> dict[str, str | int]:
    """Exercise core dev infrastructure without importing real agents."""

    settings = get_settings()
    generation_client = get_llm_client(LLMRole.GENERATION)
    evaluation_client = get_llm_client(LLMRole.EVALUATION)
    search_results = await CachedSearchClient(settings=settings).search(query)

    generation_response = await generation_client.complete(
        LLMRequest(
            messages=[
                {"role": "system", "content": "Summarize search evidence."},
                {
                    "role": "user",
                    "content": f"Query: {query}\nEvidence: {search_results[0].content}",
                },
            ],
            model=settings.model_for(LLMRole.GENERATION),
            agent_type="dev_generation",
        )
    )
    evaluation_response = await evaluation_client.complete(
        LLMRequest(
            messages=[
                {"role": "system", "content": "Evaluate summary faithfulness."},
                {"role": "user", "content": generation_response.content},
            ],
            model=settings.model_for(LLMRole.EVALUATION),
            agent_type="dev_evaluation",
        )
    )

    responses = [generation_response, evaluation_response]
    return {
        "status": "completed",
        "mode": AgentOpsMode.MOCK.value,
        "query": query,
        "summary": _summary_from_response(generation_response),
        "total_prompt_tokens": sum(response.prompt_tokens for response in responses),
        "total_completion_tokens": sum(
            response.completion_tokens for response in responses
        ),
        "note": "infra smoke test, not the real pipeline",
    }


def _summary_from_response(response: LLMResponse) -> str:
    return response.content
