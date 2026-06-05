# AgentOps

AgentOps is a portfolio project for production-oriented multi-agent research workflows. The system will grow into a LangGraph-based research and report generation pipeline with deterministic mock mode, local Ollama mode, cloud mode, budget enforcement, observability, and tamper-evident audit logging.

![CI](https://github.com/nishxnt/agent-ops/actions/workflows/ci.yml/badge.svg)
![Docker](https://github.com/nishxnt/agent-ops/actions/workflows/docker-smoke.yml/badge.svg)
![k8s](https://github.com/nishxnt/agent-ops/actions/workflows/k8s-smoke.yml/badge.svg)

## Status

Phase 5 complete: GitHub Actions CI runs lint + test on every push, builds and smoke-tests the Docker image on every PR, and provisions a minikube cluster to deploy the Helm chart and run one end-to-end mock pipeline query on every PR. Phase 4 work (CLI, async HTTP API, Docker image, raw Kubernetes manifests, Helm chart) is unchanged. The observability stack — hash-chained audit log, OpenTelemetry spans, and optional OTLP export to Arize Phoenix and LangSmith — remains intact.

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

## Deployment

### CLI

```bash
AGENTOPS_MODE=mock uv run agentops-run "What is FAISS?"
```

### HTTP API (local)

```bash
AGENTOPS_MODE=mock uv run agentops-api
curl -s http://localhost:8000/healthz
curl -s -X POST http://localhost:8000/run \
    -H 'content-type: application/json' \
    -d '{"query":"What is FAISS?"}'
```

### Docker

```bash
make docker-build
make docker-smoke    # builds + curls through HTTP
```

The Docker image installs the minimum dependency set required for `AGENTOPS_MODE=mock`. Local mode and cloud mode require additional packages (`sentence-transformers`, `torch`, evaluation libraries) installed outside the container; the Dockerfile is intentionally scoped to the mock-mode API surface used by PR validation and the k8s smoke.

### Kubernetes (raw manifests, for learning)

```bash
make k8s-up          # kustomize apply
make k8s-smoke
make k8s-down
```

### Kubernetes (Helm chart, for real)

```bash
make helm-install
make k8s-smoke       # same smoke target works against the release
make helm-uninstall
```

### What's in the chart

- Single-replica API gateway Deployment with the orchestrator running in-process
- 1Gi RWO PersistentVolumeClaim for the audit DB
- NodePort 30080 in dev / ClusterIP in production
- Non-root container (uid 1000), liveness and readiness probes
- ConfigMap for pipeline tuning; Secret (optional) for LLM API keys

The Helm chart packages the raw manifests from `k8s/` (kept for educational reference) with environment-aware values. `values.yaml` is the production default; `values.dev.yaml` overrides for minikube.
