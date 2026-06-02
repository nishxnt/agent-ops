from pathlib import Path

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from agentops.orchestration.graph import PipelineOrchestrator
from agentops.orchestration.state import PipelineStatus

_EXPORTER = InMemorySpanExporter()
_PROVIDER = TracerProvider()
trace.set_tracer_provider(_PROVIDER)
_ACTIVE_PROVIDER = trace.get_tracer_provider()
if isinstance(_ACTIVE_PROVIDER, TracerProvider):
    _ACTIVE_PROVIDER.add_span_processor(SimpleSpanProcessor(_EXPORTER))


@pytest.mark.asyncio
async def test_pipeline_e2e_mock_mode(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """End-to-end pipeline run in mock mode via the production factory."""

    _EXPORTER.clear()
    monkeypatch.setenv("AGENTOPS_MODE", "mock")
    monkeypatch.setenv("BUDGET_TOKEN_LIMIT", "100000")
    monkeypatch.setenv("AUDIT_DB_PATH", str(tmp_path / "audit.sqlite"))

    orchestrator = PipelineOrchestrator()
    state = await orchestrator.run("What is FAISS?")

    assert state["pipeline_status"] == PipelineStatus.DONE
    assert state["quality_decision"] is not None
    assert state["quality_decision"].decision == "PASS"
    assert state["report"] is not None
    assert state["budget_tracker"].spent > 0
    assert state["budget_tracker"].per_agent_spend["planner"] > 0
    assert state["budget_tracker"].per_agent_spend["researcher"] > 0

    audit_logger = orchestrator.audit_logger
    entries = audit_logger.query_by_run_id(state["run_id"])
    assert len(entries) >= 3
    assert audit_logger.verify_chain(state["run_id"]) is True

    agent_types = {entry.agent_type for entry in entries}
    assert "planner" in agent_types
    assert "researcher" in agent_types
    assert "writer" in agent_types

    spans = _EXPORTER.get_finished_spans()
    span_names = {span.name for span in spans}
    assert "plan" in span_names
    assert "research" in span_names
    assert "critique" in span_names
    assert "write" in span_names
    assert "quality_check" in span_names

    for span in spans:
        if span.name == "plan":
            assert span.attributes["run_id"] == state["run_id"]
            break
    else:
        pytest.fail("plan span not found")
