# Implementation Notes

## Phase 2 Milestone 3 Budget Accounting

- `BudgetGuard` charges calls routed through `agentops.llm.client.LLMClient.complete`.
- RogueLLM metric judges inside `QualityGateAgent` construct their own LLM clients and do not route through `agentops.llm.client`, so those judge calls are not charged against the Phase 2 M3 budget. Track this as a Phase 3 follow-up.
- On `BUDGET_HALTED`, `plan`, `findings`, and later graph state fields are the initial-state values because LangGraph does not surface mid-run state on exception. Only `budget_tracker` is current. Phase 3 audit logging will capture per-node checkpoints.

## Phase 2 Milestone 4 Recovery Scope

- Recovery is retry-only in Phase 2 M4. The spec section 5.2 degrade path that proceeds to critique with partial findings is deferred until after Phase 2 to keep the recovery diff bounded.

## Phase 2 Wrap-Up — Deferred Items

The following deviate from spec §6 Phase 2 and are captured for post-Phase-2 follow-up.

- **Recovery degrade path omitted (M4).** Spec §5.2 describes retry and degrade strategies. M4 implements retry-only. Degrade requires a force-proceed signal to the critic and adds another routing decision — deferred.
- **RogueLLM metric calls not budget-charged (M3).** The faithfulness and hallucination judges inside QualityGateAgent construct their own LLM clients (via RogueLLM) and do not route through `agentops.llm.client.complete()`. Their token spend is not counted toward the BudgetGuard. Closing requires either plumbing a shared LLMClient through RogueLLM, or a separate cost tracker on the agent.
- **Partial state on BUDGET_HALTED (M3).** When BudgetExceededError is caught at the orchestrator boundary, the returned state has plan, findings, critic_report, and report at initial-state values. LangGraph doesn't surface mid-execution state on exception. Only `budget_tracker` reflects actual progress. Phase 3 audit logging will capture per-node checkpoints.
- **MockLLMClient token cap (M3).** Mock responses are capped at 10 prompt + 10 completion tokens per call regardless of fixture content. This makes budget tests deterministic but means mock mode does not reflect realistic token consumption. Real provider clients preserve true usage accounting.
- **Quality Gate mock-mode stubs (M5).** In MOCK mode, QualityGateAgent defaults to fixed-score metric stubs (faithfulness=0.9, hallucination=0.05) rather than RogueLLM judges so mock mode is fully offline. LOCAL and CLOUD modes use real judges.
