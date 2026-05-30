import pytest

import agentops.llm.client as llm_client
from agentops.config import AgentOpsMode, LLMRole, Settings
from agentops.llm.client import GroqLLMClient, MockLLMClient, OllamaLLMClient
from agentops.llm.models import LLMRequest


def test_factory_returns_mock_client_in_mock_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        llm_client,
        "get_settings",
        lambda: Settings(mode=AgentOpsMode.MOCK),
    )

    client = llm_client.get_llm_client(LLMRole.GENERATION)

    assert isinstance(client, MockLLMClient)


def test_factory_returns_local_and_cloud_types_without_network() -> None:
    local = llm_client._client_for_settings(
        role=LLMRole.GENERATION,
        settings=Settings(mode=AgentOpsMode.LOCAL),
    )
    cloud = llm_client._client_for_settings(
        role=LLMRole.EVALUATION,
        settings=Settings(mode=AgentOpsMode.CLOUD),
    )

    assert isinstance(local, OllamaLLMClient)
    assert isinstance(cloud, GroqLLMClient)


@pytest.mark.asyncio
async def test_mock_llm_client_is_deterministic_and_counts_tokens() -> None:
    client = MockLLMClient(model="qwen2.5:7b")
    request = LLMRequest(
        messages=[{"role": "user", "content": "What is FAISS?"}],
        model="qwen2.5:7b",
    )

    first = await client.complete(request)
    second = await client.complete(request)

    assert first == second
    assert first.prompt_tokens > 0
    assert first.completion_tokens > 0
    assert client.invocation_count == 2
