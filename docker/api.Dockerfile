# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS builder

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_NO_INSTALLER_METADATA=1

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && curl -LsSf https://astral.sh/uv/install.sh | sh \
    && mv /root/.local/bin/uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY src/ ./src/

# NOTE: Mock-mode API image. Hand-curated minimal dependency set,
# NOT a full `uv sync --frozen` install. Heavyweight non-mock packages
# (sentence-transformers, torch, RogueLLM eval metrics, Phoenix, FAISS)
# are deliberately excluded. When pyproject.toml main dependencies change,
# this list must be reviewed in the same PR. See IMPLEMENTATION_NOTES.md
# "Phase 5 M2.5 — Image dependency strategy" for full rationale.
RUN uv venv /app/.venv \
    && uv pip install --python /app/.venv/bin/python \
        "diskcache>=5.6" \
        "fastapi>=0.115,<1" \
        "groq>=0.9" \
        "httpx>=0.27,<1" \
        "langgraph>=0.3" \
        "ollama>=0.3" \
        "opentelemetry-api>=1.27,<2" \
        "opentelemetry-exporter-otlp-proto-http>=1.27,<2" \
        "opentelemetry-sdk>=1.27,<2" \
        "pydantic>=2.7" \
        "pydantic-settings>=2.2" \
        "structlog>=24.4" \
        "tavily-python>=0.7.25" \
        "uvicorn[standard]>=0.30,<1"

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH=/app/src \
    AGENTOPS_API_HOST=0.0.0.0 \
    AGENTOPS_API_PORT=8000 \
    AGENTOPS_SEARCH_CACHE_DIR=/home/agentops/.agentops-cache/search \
    AUDIT_DB_PATH=/home/agentops/audit.sqlite

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --system --gid 1000 agentops \
    && useradd --system --uid 1000 --gid agentops \
        --create-home --shell /usr/sbin/nologin agentops \
    && mkdir -p /home/agentops/.agentops-cache/search \
    && chown -R agentops:agentops /home/agentops/.agentops-cache

WORKDIR /app

COPY --from=builder --chown=agentops:agentops /app/.venv /app/.venv
COPY --chown=agentops:agentops src/ /app/src/
COPY --chown=agentops:agentops tests/fixtures/ /app/tests/fixtures/

USER agentops

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://localhost:8000/healthz || exit 1

CMD ["python", "-m", "uvicorn", "agentops.api.main:app", \
     "--host", "0.0.0.0", "--port", "8000"]
