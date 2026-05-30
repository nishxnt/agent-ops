from pathlib import Path

import pytest

from agentops.config import AgentOpsMode, Settings
from agentops.dev.search_cache import CachedSearchClient, SearchResult
from tests.fixtures import load_fixture


@pytest.mark.asyncio
async def test_search_cache_populates_then_serves_from_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(mode=AgentOpsMode.MOCK, search_cache_dir=str(tmp_path))
    client = CachedSearchClient(settings=settings)
    calls = 0

    async def fake_fetch(query: str) -> list[SearchResult]:
        nonlocal calls
        calls += 1
        return [
            SearchResult(
                title="Cached result",
                url="https://example.com",
                content=f"Result for {query}",
                score=0.9,
            )
        ]

    monkeypatch.setattr(client, "_fetch_uncached", fake_fetch)

    first = await client.search("cache me")
    second = await client.search("cache me")

    assert first == second
    assert calls == 1


@pytest.mark.asyncio
async def test_search_fixtures_load_in_mock_mode(tmp_path: Path) -> None:
    settings = Settings(mode=AgentOpsMode.MOCK, search_cache_dir=str(tmp_path))
    client = CachedSearchClient(settings=settings)

    results = await client.search("What is FAISS?")

    assert results
    assert results[0].title == "FAISS documentation"


def test_fixture_helper_loads_json() -> None:
    payload = load_fixture("search_responses/default.json")

    assert payload["results"][0]["title"] == "FAISS documentation"
