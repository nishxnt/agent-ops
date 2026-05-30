"""Mock-mode infrastructure smoke entry point."""

import asyncio
import time

import structlog

from agentops.config import AgentOpsMode, get_settings
from agentops.dev.mocks import mock_pipeline_run

logger = structlog.get_logger(__name__)
MAX_RUNTIME_SECONDS = 5.0


def main() -> None:
    """Console script for `make run-mock`."""

    settings = get_settings()
    if settings.mode is not AgentOpsMode.MOCK:
        raise SystemExit("Only AGENTOPS_MODE=mock is supported by this entry point.")

    started = time.perf_counter()
    result = asyncio.run(mock_pipeline_run("What is FAISS?"))
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    logger.info("mock_pipeline_completed", elapsed_ms=elapsed_ms, **result)
    if elapsed_ms > MAX_RUNTIME_SECONDS * 1000:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
