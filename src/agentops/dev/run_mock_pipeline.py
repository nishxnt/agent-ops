"""PROVISIONAL Milestone-1 stub returning hardcoded data.

This module will be rebuilt in Milestone 3/4 to route through MockLLMClient and
CachedSearchClient. Do not expand this logic before that milestone.
"""

import structlog

from agentops.config import AgentOpsMode, get_settings

logger = structlog.get_logger(__name__)


def run_mock_pipeline() -> dict[str, str]:
    """Return a deterministic pipeline result without external calls."""

    settings = get_settings()
    return {
        "status": "completed",
        "mode": settings.mode.value,
        "query": "What is FAISS?",
        "summary": "Mock pipeline executed with deterministic local data.",
    }


def main() -> None:
    """Console script for `make run-mock`."""

    settings = get_settings()
    if settings.mode is not AgentOpsMode.MOCK:
        raise SystemExit("Only AGENTOPS_MODE=mock is implemented in Milestone 1.")

    result = run_mock_pipeline()
    logger.info("mock_pipeline_completed", **result)


if __name__ == "__main__":
    main()
