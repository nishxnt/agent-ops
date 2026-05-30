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

## Known limitations / follow-ups

- Mock fixtures live in `tests/fixtures`; containerized mock mode will need
  those fixtures moved into package data or mounted explicitly.
- `mock_pipeline_run` assumes at least one search result.
