"""Disk-backed cached search client for development infrastructure."""

import hashlib
import json
from pathlib import Path
from typing import Any, cast

from diskcache import Cache  # type: ignore[import-untyped]
from pydantic import BaseModel, Field

from agentops.config import AgentOpsMode, Settings, get_settings


class SearchResult(BaseModel):
    """Provider-neutral search result."""

    title: str
    url: str
    content: str
    score: float = Field(ge=0.0)


class CachedSearchClient:
    """Search client that caches responses by query hash."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.cache = Cache(self.settings.search_cache_dir)

    async def search(self, query: str) -> list[SearchResult]:
        """Return cached search results, fetching on cache miss."""

        key = hashlib.sha256(query.encode("utf-8")).hexdigest()
        cached = self.cache.get(key)
        if cached is not None:
            return [SearchResult.model_validate(item) for item in cached]

        results = await self._fetch_uncached(query)
        self.cache.set(
            key,
            [result.model_dump() for result in results],
            expire=self.settings.search_cache_ttl_seconds,
        )
        return results

    async def _fetch_uncached(self, query: str) -> list[SearchResult]:
        """Fetch search results from fixtures in mock mode or Tavily otherwise."""

        if self.settings.mode is AgentOpsMode.MOCK:
            payload = _load_mock_search_payload(query)
            return _parse_tavily_results(payload)

        from tavily import TavilyClient  # type: ignore[import-not-found]

        client = TavilyClient(api_key=self.settings.tavily_api_key)
        payload = client.search(query=query)
        return _parse_tavily_results(payload)


def _load_mock_search_payload(query: str) -> dict[str, Any]:
    fixture_dir = Path(__file__).resolve().parents[3] / "tests" / "fixtures"
    search_dir = fixture_dir / "search_responses"
    digest = hashlib.sha256(query.encode("utf-8")).hexdigest()
    fixture_path = search_dir / f"{digest}.json"
    if not fixture_path.exists():
        fixture_path = search_dir / "default.json"
    return cast(dict[str, Any], json.loads(fixture_path.read_text(encoding="utf-8")))


def _parse_tavily_results(payload: dict[str, Any]) -> list[SearchResult]:
    raw_results = payload.get("results", [])
    return [SearchResult.model_validate(item) for item in raw_results]
