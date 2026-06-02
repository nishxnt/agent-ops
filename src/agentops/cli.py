"""Command-line entry point for the AgentOps research pipeline."""

import argparse
import asyncio
import json
import sys

from agentops.config import get_settings
from agentops.observability.tracing import setup_tracing
from agentops.orchestration.graph import PipelineOrchestrator
from agentops.orchestration.state import PipelineStatus


def main() -> None:
    """Run the AgentOps research pipeline and print a JSON summary."""

    parser = argparse.ArgumentParser(description="Run the AgentOps research pipeline.")
    parser.add_argument("query", nargs="?", default="What is FAISS?")
    parser.add_argument("--run-id", default=None)
    args = parser.parse_args()

    settings = get_settings()
    if settings.tracing_enabled:
        setup_tracing(
            phoenix_endpoint=settings.phoenix_endpoint or None,
            langsmith_endpoint=(
                settings.langsmith_endpoint if settings.langsmith_enabled else None
            ),
            langsmith_api_key=settings.langsmith_api_key,
            langsmith_project=settings.langsmith_project,
        )

    orchestrator = PipelineOrchestrator(settings=settings)
    state = asyncio.run(orchestrator.run(args.query, run_id=args.run_id))

    summary = {
        "run_id": state["run_id"],
        "query": state["query"],
        "pipeline_status": state["pipeline_status"].value,
        "decision": (
            state["quality_decision"].decision if state["quality_decision"] else None
        ),
        "revision_count": state["revision_count"],
        "recovery_attempts": dict(state["recovery_attempts"]),
        "report_sections": len(state["report"].sections) if state["report"] else 0,
        "budget_spent": state["budget_tracker"].spent,
        "budget_total": state["budget_tracker"].budget,
        "per_agent_spend": dict(state["budget_tracker"].per_agent_spend),
        "failed_tasks": state["failed_tasks"],
        "error": str(state["error"]) if state["error"] else None,
    }
    print(json.dumps(summary, indent=2, default=str))

    if state["pipeline_status"] != PipelineStatus.DONE:
        sys.exit(1)
