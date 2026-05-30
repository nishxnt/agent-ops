"""Mock-mode infrastructure smoke entry point."""

import asyncio

import structlog

from agentops.config import AgentOpsMode, get_settings
from agentops.dev.mocks import mock_pipeline_run

logger = structlog.get_logger(__name__)


def main() -> None:
    """Console script for `make run-mock`."""

    settings = get_settings()
    if settings.mode is not AgentOpsMode.MOCK:
        raise SystemExit("Only AGENTOPS_MODE=mock is supported by this entry point.")

    result = asyncio.run(mock_pipeline_run("What is FAISS?"))
    logger.info("mock_pipeline_completed", **result)


if __name__ == "__main__":
    main()
