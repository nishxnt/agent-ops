# AgentOps

AgentOps is a portfolio project for production-oriented multi-agent research workflows. The system will grow into a LangGraph-based research and report generation pipeline with deterministic mock mode, local Ollama mode, cloud mode, budget enforcement, observability, and tamper-evident audit logging.

Current status: Phase 0 foundation.

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

Only mock mode is stubbed in this milestone.
