"""LLM clients and execution-mode-aware factory."""

import hashlib
import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, cast

from groq import AsyncGroq
from ollama import AsyncClient as AsyncOllamaClient

from agentops.budget.context import current_budget_guard
from agentops.config import AgentOpsMode, LLMRole, Settings, get_settings
from agentops.llm.models import LLMError, LLMRequest, LLMResponse


class LLMClient(ABC):
    """Abstract provider-neutral LLM client."""

    def __init__(self, *, model: str) -> None:
        self.model = model

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Complete a chat request."""

        response = await self._do_complete(request)
        guard = current_budget_guard.get()
        if guard is not None:
            guard.check_and_charge(
                prompt_tokens=response.prompt_tokens,
                completion_tokens=response.completion_tokens,
                model=response.model,
                agent_type=request.agent_type,
            )
        return response

    @abstractmethod
    async def _do_complete(self, request: LLMRequest) -> LLMResponse:
        """Provider-specific completion implementation."""


class MockLLMClient(LLMClient):
    """Deterministic fixture-backed LLM client for network-free development."""

    def __init__(self, model: str, fixture_dir: Path | None = None) -> None:
        super().__init__(model=model)
        self.fixture_dir = fixture_dir or _fixture_root() / "llm_responses"
        self.invocation_count = 0

    async def _do_complete(self, request: LLMRequest) -> LLMResponse:
        """Return deterministic fixture content for a request."""

        self.invocation_count += 1
        fixture = self._load_fixture(request)
        if fixture.get("error"):
            raise LLMError(str(fixture["content"]), provider="mock")

        content = str(fixture["content"])
        prompt_text = json.dumps(request.messages, sort_keys=True)
        return LLMResponse(
            content=content,
            model=request.model,
            prompt_tokens=min(10, _estimate_tokens(prompt_text)),
            completion_tokens=min(10, _estimate_tokens(content)),
        )

    def _load_fixture(self, request: LLMRequest) -> dict[str, Any]:
        payload = json.dumps(request.messages, sort_keys=True)
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        fixture_dir = self.fixture_dir
        agent_fixture_dir = fixture_dir / request.agent_type
        if agent_fixture_dir.is_dir():
            fixture_dir = agent_fixture_dir

        fixture_path = fixture_dir / f"{digest}.json"
        if not fixture_path.exists():
            fixture_path = fixture_dir / "default.json"
        if (
            request.agent_type == "writer"
            and "executive_summary" in payload
            and (fixture_dir / "executive_summary.json").exists()
        ):
            fixture_path = fixture_dir / "executive_summary.json"
        return cast(
            dict[str, Any],
            json.loads(fixture_path.read_text(encoding="utf-8")),
        )


class OllamaLLMClient(LLMClient):
    """Ollama-backed local LLM client."""

    def __init__(self, model: str, base_url: str) -> None:
        super().__init__(model=model)
        self.client = AsyncOllamaClient(host=base_url)

    async def _do_complete(self, request: LLMRequest) -> LLMResponse:
        """Complete a request via Ollama."""

        try:
            response = await self.client.chat(
                model=request.model,
                messages=request.messages,
                options={
                    "temperature": request.temperature,
                    "num_predict": request.max_tokens,
                },
            )
        except Exception as exc:  # pragma: no cover - provider boundary
            raise LLMError(str(exc), provider="ollama") from exc

        content = str(response["message"]["content"])
        prompt_text = json.dumps(request.messages, sort_keys=True)
        prompt_tokens = int(
            response.get("prompt_eval_count", _estimate_tokens(prompt_text))
        )
        completion_tokens = int(response.get("eval_count", _estimate_tokens(content)))
        return LLMResponse(
            content=content,
            model=request.model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )


class GroqLLMClient(LLMClient):
    """Groq-backed cloud LLM client."""

    def __init__(self, model: str, api_key: str | None) -> None:
        super().__init__(model=model)
        self.client = AsyncGroq(api_key=api_key or "missing-api-key")

    async def _do_complete(self, request: LLMRequest) -> LLMResponse:
        """Complete a request via Groq."""

        try:
            response = await self.client.chat.completions.create(
                messages=cast(Any, request.messages),
                model=request.model,
                max_tokens=request.max_tokens,
                temperature=request.temperature,
            )
        except Exception as exc:  # pragma: no cover - provider boundary
            raise LLMError(str(exc), provider="groq") from exc

        content = response.choices[0].message.content or ""
        usage = response.usage
        completion_tokens = (
            usage.completion_tokens if usage else _estimate_tokens(content)
        )
        return LLMResponse(
            content=content,
            model=request.model,
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=completion_tokens,
        )


def get_llm_client(role: LLMRole) -> LLMClient:
    """Return the correct LLM client for the configured execution mode."""

    settings = get_settings()
    return _client_for_settings(role=role, settings=settings)


def _client_for_settings(role: LLMRole, settings: Settings) -> LLMClient:
    model = settings.model_for(role)
    if settings.mode is AgentOpsMode.MOCK:
        return MockLLMClient(model=model)
    if settings.mode is AgentOpsMode.LOCAL:
        return OllamaLLMClient(model=model, base_url=settings.ollama_base_url)
    return GroqLLMClient(model=model, api_key=settings.groq_api_key)


def _fixture_root() -> Path:
    return Path(__file__).resolve().parents[3] / "tests" / "fixtures"


def _estimate_tokens(text: str) -> int:
    return max(1, (len(text) + 3) // 4)
