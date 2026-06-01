# Implementation Notes

## Phase 2 Milestone 3 Budget Accounting

- `BudgetGuard` charges calls routed through `agentops.llm.client.LLMClient.complete`.
- RogueLLM metric judges inside `QualityGateAgent` construct their own LLM clients and do not route through `agentops.llm.client`, so those judge calls are not charged against the Phase 2 M3 budget. Track this as a Phase 3 follow-up.
- On `BUDGET_HALTED`, `plan`, `findings`, and later graph state fields are the initial-state values because LangGraph does not surface mid-run state on exception. Only `budget_tracker` is current. Phase 3 audit logging will capture per-node checkpoints.

## Phase 2 Milestone 4 Recovery Scope

- Recovery is retry-only in Phase 2 M4. The spec section 5.2 degrade path that proceeds to critique with partial findings is deferred until after Phase 2 to keep the recovery diff bounded.
