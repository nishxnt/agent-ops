"""OpenTelemetry tracing helpers for orchestration nodes."""

import functools
from collections.abc import Awaitable, Callable
from typing import Any, cast

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

_TRACER_NAME = "agentops.orchestration"
_PROVIDER: TracerProvider | None = None


def setup_tracing(*, endpoint: str | None = None) -> TracerProvider:
    """Initialize the global TracerProvider once per process.

    If endpoint is provided, a BatchSpanProcessor with an OTLP HTTP exporter is
    attached. Otherwise the provider exists but drops spans unless tests attach
    an in-memory span processor.
    """

    global _PROVIDER
    if _PROVIDER is not None:
        return _PROVIDER

    provider = TracerProvider()
    if endpoint:
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint))
        )
    trace.set_tracer_provider(provider)
    _PROVIDER = provider
    return provider


def get_tracer() -> trace.Tracer:
    """Return the orchestration tracer."""

    return trace.get_tracer(_TRACER_NAME)


NodeFn = Callable[..., Awaitable[Any]]


def traced_node(span_name: str) -> Callable[[NodeFn], NodeFn]:
    """Decorator: wrap an async node function in an OTel span."""

    def decorator(fn: NodeFn) -> NodeFn:
        @functools.wraps(fn)
        async def wrapper(state: Any, **kwargs: Any) -> Any:
            tracer = get_tracer()
            with tracer.start_as_current_span(span_name) as span:
                span.set_attribute("run_id", state["run_id"])
                span.set_attribute(
                    "budget.spent_before",
                    state["budget_tracker"].spent,
                )
                span.set_attribute(
                    "pipeline.status_before",
                    state["pipeline_status"].value,
                )
                try:
                    result = await fn(state, **kwargs)
                    span.set_attribute(
                        "budget.spent_after",
                        result["budget_tracker"].spent,
                    )
                    span.set_attribute(
                        "pipeline.status_after",
                        result["pipeline_status"].value,
                    )
                    span.set_status(trace.Status(trace.StatusCode.OK))
                    return result
                except Exception as exc:
                    span.set_status(trace.Status(trace.StatusCode.ERROR, str(exc)))
                    span.record_exception(exc)
                    raise

        return cast(NodeFn, wrapper)

    return decorator
