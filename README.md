# AgentOps

AgentOps is a portfolio project for production-oriented multi-agent research workflows. The system will grow into a LangGraph-based research and report generation pipeline with deterministic mock mode, local Ollama mode, cloud mode, budget enforcement, observability, and tamper-evident audit logging.

## Status

Phase 3 complete: full observability stack with a hash-chained audit log (SQLite, tamper-evident), OpenTelemetry spans on every orchestration node, and optional export to Arize Phoenix and LangSmith via OTLP. Phase 4 (Kubernetes deployment) is next.

## Quick Start

```bash
uv sync
make lint
make test
make run-mock
```

`uv` must be available on `PATH`; do not hardcode a machine-specific `uv` path.

## Execution Modes

- `AGENTOPS_MODE=mock`: deterministic local fixtures only, no external calls.
- `AGENTOPS_MODE=local`: Ollama for LLM calls, cached search for web lookups.
- `AGENTOPS_MODE=cloud`: Groq and Tavily through production adapters.

## Observability

**Audit log** — every LLM call writes one entry to a SHA-256 chained SQLite log. Tamper-evident: `AuditLogger.verify_chain(run_id)` detects any post-hoc row mutation. See `examples/example_run_audit.json` for a sample.

**Tracing** — six OpenTelemetry spans per pipeline run (`plan`, `research`, `critique`, `write`, `quality_check`, `recovery`), with `run_id` and budget telemetry as span attributes. Exports to:

- Arize Phoenix: `PHOENIX_ENDPOINT=http://localhost:6006/v1/traces` (start with `python -m phoenix.server.main serve`)
- LangSmith: `LANGSMITH_ENABLED=true`, `LANGSMITH_API_KEY=...`, optional `LANGSMITH_PROJECT=agentops`

Both backends are independent; either, both, or neither can be enabled. Default is no export; spans are emitted but dropped.

## Kubernetes Deployment (minikube)

```bash
make k8s-up      # build image into minikube, apply manifests
make k8s-smoke   # curl through NodePort, run a pipeline
make k8s-down    # remove all resources
```

Architecture: one API gateway Pod with the orchestrator running in-process. Audit DB on a 1Gi RWO PersistentVolumeClaim. Exposed via NodePort 30080. Single replica because the run registry is in-memory; horizontal scaling is a known follow-up.
