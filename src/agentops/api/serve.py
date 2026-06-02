"""Uvicorn launcher for the AgentOps HTTP gateway."""

import os

import uvicorn


def main() -> None:
    host = os.environ.get("AGENTOPS_API_HOST", "0.0.0.0")
    port = int(os.environ.get("AGENTOPS_API_PORT", "8000"))
    uvicorn.run(
        "agentops.api.main:app",
        host=host,
        port=port,
        reload=False,
        log_level="info",
    )
