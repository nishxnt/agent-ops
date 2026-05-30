# AgentOps — Development Notes (read before any work)

## Reference
The authoritative design is AgentOps_Project_Spec_v1.1.md. Follow it for any
architectural decision. If it is unclear or seems wrong, STOP and ask
Nishant — never improvise silently.

## Engineering conventions
- Python 3.12 (pinned in .python-version).
- Type hints on every function/method. mypy --strict must pass.
- Pydantic v2 for all data models. TypedDict only for LangGraph state.
- Logging: structlog only. No print, no stdlib logging.
- Config: pydantic-settings BaseSettings only. Never hardcode model names,
  endpoints, budgets, or paths.
- I/O: async via httpx.AsyncClient. Never use requests.
- Call uv by name. Never commit absolute home-directory paths.

## Git workflow (spec §9)
- main = protected baseline. dev = integration. One feature branch per phase
  off dev: feat/phase-N-...
- Conventional Commits scoped by phase: feat(phase-1): ..., chore(phase-0): ...

## Phase discipline
- Work only within the current phase. Do not pull later-phase work forward.
- During Phase 0, create files (beyond __init__.py) only in: src/agentops/
  top level, src/agentops/llm/, src/agentops/dev/, and tests/. Do NOT create
  other files in agents/, orchestration/, api/, observability/, audit/,
  budget/, docker/, k8s/, or charts/agentops/templates/.

## Milestone gates
- Stop at each milestone gate; wait for explicit approval before continuing.
