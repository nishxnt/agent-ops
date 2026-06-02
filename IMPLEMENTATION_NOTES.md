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

## Phase 3 M2 — Audit Wiring Design

- Audit fires for SUCCESSFUL LLM calls only. Failures (exceptions raised by _do_complete) are not logged because token/latency data is unavailable. Capturing failures is a Phase 4+ follow-up.
- All M2 audit entries have status="SUCCESS". BUDGET_HALTED, RECOVERED, and FAILED statuses are reserved for orchestrator-layer entries that record policy decisions, not raw LLM calls. These will be wired in later milestones.
- Audit append happens BEFORE budget.check_and_charge. Order: LLM call completes → audit recorded → budget policy applied. If budget then raises BudgetExceededError, the audit entry for the call is preserved (the call really happened; the policy halt is separate).
- The AuditLogger is constructed once per PipelineOrchestrator and reused across runs. run_id discriminates entries. Single SQLite file under settings.audit_db_path.

## Phase 3 M3 — OpenTelemetry + Phoenix Design

- The `traced_node` decorator wraps every orchestration node function. Span names match LangGraph node names: `plan`, `research`, `critique`, `write`, `quality_check`, and `recovery`.
- `TracerProvider` is set once per process. The CLI initializes tracing before `PipelineOrchestrator.run()`. Tests attach a shared `InMemorySpanExporter` at module import time and clear it between tests.
- Phoenix export is opt-in via `settings.phoenix_endpoint`. The default empty value means OTel runs without an exporter, so spans are dropped. Users opt in by running `python -m phoenix.server.main serve` separately and setting `PHOENIX_ENDPOINT=http://localhost:6006/v1/traces`.
- `arize-phoenix` remains a main dependency, pinned to `>=4.0,<5` for this milestone, because the CLI exposes Phoenix export as first-class runtime scaffolding.

## Phase 3 M4 — LangSmith Integration Design

- LangSmith is integrated via OTLP HTTP export, not the langsmith Python SDK. The existing OpenTelemetry spans (one per orchestration node, with run_id attributes) are exported to LangSmith's `/otel/v1/traces` endpoint via a BatchSpanProcessor.
- Trade-off: this is dramatically simpler than building a separate LangSmith Run-hierarchy via the SDK (parent run + child runs per agent call), but produces flat span traces rather than nested run trees. Sufficient for "traces visible in LangSmith UI"; richer hierarchy is a post-Phase-3 enhancement.
- LangSmith export is opt-in: requires `LANGSMITH_ENABLED=true` and `LANGSMITH_API_KEY` non-empty. Without both, no LangSmith calls are made.
- Phoenix and LangSmith are independent. Either, both, or neither can be configured.

Manual LangSmith smoke:

1. Get a LangSmith API key from https://smith.langchain.com.
2. In `.env`, set `LANGSMITH_ENABLED=true`, `LANGSMITH_API_KEY=ls_...`, and `LANGSMITH_PROJECT=agentops-dev`.
3. Run `AGENTOPS_MODE=mock uv run agentops-run "What is FAISS?"`.
4. Check `https://smith.langchain.com/o/.../projects/p/agentops-dev` for a trace with spans `plan`, `research`, `critique`, `write`, and `quality_check`.

This is intentionally manual; automating it would require either mocking LangSmith's API or running CI against the real endpoint.

## Phase 3 Wrap-Up — Deferred Items

- **Failed-call audit entries (M2).** When `_do_complete` raises an exception, no audit row is written because token and latency data are unavailable. Capturing failures with `status="FAILED"` plus an `error_message` column is a Phase 4+ enhancement.
- **BUDGET_HALTED / RECOVERED audit entries (M2).** All M2 audits have `status="SUCCESS"`. Policy-decision entries, such as the orchestrator writing rows directly to mark `BUDGET_HALTED` at the moment of halt or `RECOVERED` after a recovery cycle succeeds, are a follow-up.
- **LangSmith Run hierarchy (M4).** Current integration exports flat OTel spans via OTLP. A richer nested-run hierarchy (parent run plus child runs per agent call) would require the langsmith Python SDK and parallel orchestration code. Trade-off chosen: keep the OTel surface unified. Revisit if the LangSmith UX is insufficient.
- **Phoenix/LangSmith screenshots (M5).** Manual procedure documented in README; live captures are part of Phase 6 polish.
