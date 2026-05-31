# Implementation Notes

## Milestone 1

- Established the portable Python project foundation with `uv` on `PATH`.
- Pinned Python to 3.12 via `.python-version`.
- Added initial lint, type-check, test, and mock-run commands.
- Kept Phase 0 restricted directories untouched.

## Phase 0 Summary

- Added the portable Python package skeleton under `src/agentops`.
- Added a Helm chart skeleton without Kubernetes templates.
- Added execution-mode settings, LLM client factory plumbing, cached search,
  deterministic fixtures, and a mock infrastructure smoke path.
- Verified `make lint`, `make test`, and `make run-mock`.

## Phase 1 Summary

- Shipped five agents: Planner, Researcher, Critic, Writer, and Quality Gate.
- Each agent has Pydantic schemas and at least five unit tests.
- Critic uses a two-stage review path: embedding-floor candidate detection,
  followed by LLM adjudication for candidate contradictions.
- Writer builds reports section by section from critic-verified facts and
  carries low-confidence evidence into acknowledged data gaps.
- Quality Gate integrates RogueLLM editably and enforces cross-family
  evaluation through the evaluation-model role.
- Cross-agent integration tests prove the five real agent classes compose
  end-to-end in mock mode without LangGraph orchestration.

## Known limitations / follow-ups

- Mock fixtures live in `tests/fixtures`; containerized mock mode will need
  those fixtures moved into package data or mounted explicitly.
- `mock_pipeline_run` assumes at least one search result.
FAISS local KB deferred — Researcher uses CachedSearchClient only in this milestone.
- FAISS local KB remains deferred into Phase 2.
- Real RAGAS/DeepEval live calls are only exercised in cloud mode; mock mode
  uses fake scorers.
- Quality Gate revision loop is not wired yet; Phase 1 returns the REVISION
  decision and instruction only.
