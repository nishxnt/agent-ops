import pytest

from agentops.dev.mocks import mock_pipeline_run


@pytest.mark.asyncio
async def test_mock_pipeline_run_uses_mock_clients() -> None:
    result = await mock_pipeline_run("What is FAISS?")

    assert set(result) == {
        "status",
        "mode",
        "query",
        "summary",
        "total_prompt_tokens",
        "total_completion_tokens",
        "note",
    }
    assert result["status"] == "completed"
    assert result["mode"] == "mock"
    assert result["summary"]
    assert result["total_prompt_tokens"] > 0
    assert result["total_completion_tokens"] > 0
