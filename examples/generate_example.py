"""Regenerate example artifacts for the Phase 3 demo.

Runs the orchestrator in MOCK mode with a fixed run_id, then writes:
  - example_run_cli_output.json (CLI summary)
  - example_run_audit.json (audit entries + chain verification)
  - example_run_report.json (the produced ResearchReport)

Determinism: run_id is fixed; timestamps still vary, so regeneration
produces small diffs. Re-run only when intentionally refreshing.
"""

import asyncio
import json
import os
from pathlib import Path

EXAMPLES_DIR = Path(__file__).parent
os.environ["AGENTOPS_MODE"] = "mock"
os.environ["AUDIT_DB_PATH"] = str(EXAMPLES_DIR / "_temp_audit.sqlite")

from agentops.orchestration.graph import PipelineOrchestrator  # noqa: E402


def cleanup_temp_db() -> None:
    for path in EXAMPLES_DIR.glob("_temp_audit.sqlite*"):
        path.unlink()


async def main() -> None:
    cleanup_temp_db()

    orchestrator = PipelineOrchestrator()
    state = await orchestrator.run("What is FAISS?", run_id="phase-3-demo-run")

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
    (EXAMPLES_DIR / "example_run_cli_output.json").write_text(
        json.dumps(summary, indent=2, default=str)
    )

    entries = orchestrator.audit_logger.query_by_run_id(state["run_id"])
    audit_export = {
        "run_id": state["run_id"],
        "chain_verified": orchestrator.audit_logger.verify_chain(state["run_id"]),
        "entries": [entry.model_dump() for entry in entries],
    }
    (EXAMPLES_DIR / "example_run_audit.json").write_text(
        json.dumps(audit_export, indent=2, default=str)
    )

    if state["report"]:
        report_export = {
            "title": state["report"].title,
            "executive_summary": state["report"].executive_summary,
            "sections": [
                {"title": section.heading, "content": section.content}
                for section in state["report"].sections
            ],
        }
        (EXAMPLES_DIR / "example_run_report.json").write_text(
            json.dumps(report_export, indent=2, default=str)
        )

    cleanup_temp_db()


if __name__ == "__main__":
    asyncio.run(main())
