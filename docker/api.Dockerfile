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

RUN uv sync --frozen --no-dev --no-editable --no-install-package rogue-llm

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    AGENTOPS_API_HOST=0.0.0.0 \
    AGENTOPS_API_PORT=8000

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --system --gid 1000 agentops \
    && useradd --system --uid 1000 --gid agentops \
        --create-home --shell /usr/sbin/nologin agentops

WORKDIR /app

COPY --from=builder --chown=agentops:agentops /app/.venv /app/.venv
COPY --chown=agentops:agentops src/ /app/src/
COPY --chown=agentops:agentops pyproject.toml /app/pyproject.toml

ENV AUDIT_DB_PATH=/home/agentops/audit.sqlite

USER agentops

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://localhost:8000/healthz || exit 1

CMD ["python", "-m", "uvicorn", "agentops.api.main:app", \
     "--host", "0.0.0.0", "--port", "8000"]
