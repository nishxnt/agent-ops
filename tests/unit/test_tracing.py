from typing import Any
from unittest.mock import patch

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.trace import StatusCode

from agentops.budget.guard import BudgetGuard
from agentops.observability import tracing as tracing_module
from agentops.observability.tracing import traced_node
from agentops.orchestration.state import PipelineStatus

_EXPORTER = InMemorySpanExporter()
_PROVIDER = TracerProvider()
trace.set_tracer_provider(_PROVIDER)
_ACTIVE_PROVIDER = trace.get_tracer_provider()
if isinstance(_ACTIVE_PROVIDER, TracerProvider):
    _ACTIVE_PROVIDER.add_span_processor(SimpleSpanProcessor(_EXPORTER))


@pytest.fixture(autouse=True)
def _reset_provider_cache() -> None:
    tracing_module._PROVIDER = None
    yield
    tracing_module._PROVIDER = None


@pytest.fixture
def exporter() -> InMemorySpanExporter:
    _EXPORTER.clear()
    yield _EXPORTER


def _state(*, spent: int = 0) -> dict[str, Any]:
    guard = BudgetGuard(budget_tokens=100_000)
    guard.spent = spent
    return {
        "run_id": "run-test",
        "budget_tracker": guard,
        "pipeline_status": PipelineStatus.PLANNING,
    }


@pytest.mark.asyncio
async def test_traced_node_emits_span_with_name(
    exporter: InMemorySpanExporter,
) -> None:
    @traced_node("example")
    async def node(state: dict[str, Any]) -> dict[str, Any]:
        return state

    await node(_state())

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == "example"


@pytest.mark.asyncio
async def test_traced_node_sets_run_id_and_budget_attributes(
    exporter: InMemorySpanExporter,
) -> None:
    @traced_node("attributes")
    async def node(state: dict[str, Any]) -> dict[str, Any]:
        state["budget_tracker"].spent = 84
        state["pipeline_status"] = PipelineStatus.DONE
        return state

    await node(_state(spent=42))

    span = exporter.get_finished_spans()[0]
    assert span.attributes["run_id"] == "run-test"
    assert span.attributes["budget.spent_before"] == 42
    assert span.attributes["pipeline.status_before"] == PipelineStatus.PLANNING.value
    assert span.attributes["budget.spent_after"] == 84
    assert span.attributes["pipeline.status_after"] == PipelineStatus.DONE.value


@pytest.mark.asyncio
async def test_traced_node_records_exception(
    exporter: InMemorySpanExporter,
) -> None:
    @traced_node("failure")
    async def node(state: dict[str, Any]) -> dict[str, Any]:
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        await node(_state())

    span = exporter.get_finished_spans()[0]
    assert span.status.status_code is StatusCode.ERROR
    assert any(event.name == "exception" for event in span.events)


@pytest.mark.asyncio
async def test_traced_node_preserves_signature(
    exporter: InMemorySpanExporter,
) -> None:
    seen: dict[str, str] = {}

    @traced_node("kwargs")
    async def node(state: dict[str, Any], *, marker: str) -> dict[str, Any]:
        seen["marker"] = marker
        return state

    await node(_state(), marker="passed-through")

    assert seen["marker"] == "passed-through"
    assert exporter.get_finished_spans()[0].name == "kwargs"


def test_setup_tracing_no_backends() -> None:
    with (
        patch.object(tracing_module, "OTLPSpanExporter") as exporter_cls,
        patch.object(tracing_module, "BatchSpanProcessor"),
    ):
        tracing_module.setup_tracing()

    assert exporter_cls.call_count == 0


def test_setup_tracing_phoenix_only() -> None:
    phoenix_endpoint = "http://localhost:6006/v1/traces"

    with (
        patch.object(tracing_module, "OTLPSpanExporter") as exporter_cls,
        patch.object(tracing_module, "BatchSpanProcessor"),
    ):
        tracing_module.setup_tracing(phoenix_endpoint=phoenix_endpoint)

    exporter_cls.assert_called_once_with(endpoint=phoenix_endpoint)


def test_setup_tracing_phoenix_and_langsmith() -> None:
    phoenix_endpoint = "http://localhost:6006/v1/traces"
    langsmith_endpoint = "https://api.smith.langchain.com/otel/v1/traces"

    with (
        patch.object(tracing_module, "OTLPSpanExporter") as exporter_cls,
        patch.object(tracing_module, "BatchSpanProcessor"),
    ):
        tracing_module.setup_tracing(
            phoenix_endpoint=phoenix_endpoint,
            langsmith_endpoint=langsmith_endpoint,
            langsmith_api_key="test-key",
            langsmith_project="myproj",
        )

    assert exporter_cls.call_count == 2
    exporter_cls.assert_any_call(endpoint=phoenix_endpoint)
    exporter_cls.assert_any_call(
        endpoint=langsmith_endpoint,
        headers={"x-api-key": "test-key", "Langsmith-Project": "myproj"},
    )


def test_setup_tracing_langsmith_skipped_without_api_key() -> None:
    with (
        patch.object(tracing_module, "OTLPSpanExporter") as exporter_cls,
        patch.object(tracing_module, "BatchSpanProcessor"),
    ):
        tracing_module.setup_tracing(
            langsmith_endpoint="https://api.smith.langchain.com/otel/v1/traces",
            langsmith_api_key="",
        )

    assert exporter_cls.call_count == 0
