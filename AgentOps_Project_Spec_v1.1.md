# AgentOps — Project Specification

**Type:** Individual Portfolio Project
**Author:** Nishant Gupta
**Version:** 1.1 (revised from v1.0)
**Date:** May 2026
**Status:** Pre-development
**Predecessor:** RogueLLM (adversarial testing pipeline — completed)

---

## Changelog from v1.0

| Change | Reason |
|--------|--------|
| Timeline extended from 30 days to 6 content-weeks | v1.0's 5-day Kubernetes phase was unrealistic for a learner with zero prior k8s exposure |
| Phase 0 expanded: dev cache, mock mode, Ollama setup | Free-tier exhaustion (Tavily 1k/mo, Groq RPM) would block dev by week 2 without this |
| Audit log upgraded to hash-chained SQLite | "App-layer append-only" is not tamper-evident; hash chaining is, for ~15 LOC |
| Quality Gate runs cross-family eval | Same-model eval has systematic blind spots; standard practice is cross-family |
| Critic adds deterministic embedding floor | LLM-graded contradiction detection is noisy on its own |
| RogueLLM integration is local editable pip install (pinned commit), not submodule | Submodules hurt CI and contributor onboarding |
| Phoenix disabled in CI via `values.ci.yaml` | Phoenix is heavyweight; CI smoke test should stay fast |
| Recovery state semantics defined explicitly | v1.0 said "retry/degrade" without specifying behavior |
| New objective O9: dev infrastructure (cache + mock + local LLM) | Treated as first-class engineering, not a Phase 6 afterthought |

---

## Table of Contents

1. [Motivation](#1-motivation)
2. [Problem Statement](#2-problem-statement)
3. [Project Objectives](#3-project-objectives)
4. [Skills Learned](#4-skills-learned)
5. [System Architecture](#5-system-architecture)
6. [Implementation Phases](#6-implementation-phases)
7. [Technical Stack](#7-technical-stack)
8. [Repository Structure](#8-repository-structure)
9. [Git Workflow](#9-git-workflow)
10. [Evaluation Metrics & Success Criteria](#10-evaluation-metrics--success-criteria)
11. [Week-by-Week Timeline](#11-week-by-week-timeline)
12. [Deliverables](#12-deliverables)
13. [References](#13-references)

---

## 1. Motivation

Agentic AI systems are no longer experimental. Gartner projects that by the end of 2026, over 40% of enterprise applications will include task-specific AI agents — up from less than 5% in 2025. The steepest salary growth across all AI engineering subcategories is currently in multi-agent system design, and the primary bottleneck holding back enterprise adoption is not the capability of individual agents but the **operational infrastructure surrounding them**: reliability, observability, cost control, and governance.

Most publicly available agentic AI projects demonstrate the happy path — a pipeline that works when every API responds correctly and every model output is well-formed. This is not how production systems behave. Production systems deal with partial failures, rate limit exhaustion, malformed model outputs, cost overruns, and silent quality degradation that only becomes visible weeks after deployment. The engineering discipline required to handle these realities — self-healing workflows, token budget enforcement, latency alerting, immutable audit trails, and container orchestration — is what separates a demo from a deployable system.

**AgentOps** builds this operational infrastructure from first principles, using a multi-agent research and report generation system as the vehicle. The use case is chosen deliberately: automated research workflows (competitive intelligence, technical due diligence, literature synthesis) are among the most actively deployed agentic patterns at enterprise companies right now, making every architectural decision in this project directly transferable to industry work.

### Why This Follows RogueLLM

RogueLLM gave you the evaluation layer — you now know how to measure LLM output quality systematically, run adversarial tests, and integrate safety checks into CI/CD. AgentOps builds the production system that *needs* that evaluation layer. The Quality Gate agent in AgentOps will plug directly into your existing RogueLLM evaluation engine — a concrete demonstration of reusable engineering across projects.

Additionally, RogueLLM's v1.1 roadmap identified **token cost telemetry** as a gap. This project closes it as a first-class engineering concern, not an afterthought.

---

## 2. Problem Statement

Multi-agent LLM systems in production fail in four distinct ways that single-agent systems do not:

**1. Cascade failures** — one agent's malformed output corrupts every downstream agent's input. Without schema validation at every handoff boundary, a single bad response propagates silently through the pipeline.

**2. Cost unpredictability** — parallel agent execution multiplies token usage non-linearly. A 5-agent pipeline with no budget enforcement can exhaust a monthly API budget in a single bad run.

**3. Observability blindness** — LangSmith traces individual calls but does not natively provide aggregate dashboards showing system-level health: agent success rates over time, p95 latency by agent type, cost per completed pipeline run, or hallucination drift.

**4. Deployment opacity** — most agentic projects exist only as Python scripts or Docker Compose files. Without Kubernetes manifests, health probes, and a Helm chart, the system cannot be deployed to any production infrastructure.

AgentOps solves all four: schema-validated agent handoffs, per-run budget enforcement, a full observability stack with Arize Phoenix, and a Kubernetes deployment with a Helm chart.

The specific system built is a **multi-agent research and report generation pipeline**: given a research query, a team of specialised agents plans the work, researches in parallel, fact-checks findings, writes a structured report, and validates it against quality thresholds before delivery.

---

## 3. Project Objectives

### Primary Objectives

| ID | Objective | Measurable Outcome |
|----|-----------|-------------------|
| O1 | Build a 5-agent LangGraph orchestration system | Pipeline runs end-to-end: Planner → Researchers → Critic → Writer → Quality Gate |
| O2 | Implement self-healing for agent failures | System recovers from simulated agent failures without crashing; recovery semantics documented in §6 |
| O3 | Deploy full stack to local Kubernetes cluster | `helm install agentops ./charts/agentops` brings up all services; `kubectl get pods` shows all Running |
| O4 | Implement production observability with Arize Phoenix | Token cost, latency (p50/p95), and agent success rate visible on Phoenix dashboard per run |
| O5 | Implement hash-chained immutable audit log | Every agent decision logged with prev-entry SHA-256; tamper-evident chain validated by test |
| O6 | Per-run token budget enforcement | Runs exceeding budget halt with structured error and partial report |
| O7 | Integrate RogueLLM evaluation as cross-family Quality Gate | Quality Gate uses a different model family than the Writer; faithfulness + hallucination metrics gate delivery |
| O8 | CI/CD with k8s smoke test | GitHub Actions runs 1-query smoke test against minikube on every PR to main; Phoenix disabled in CI |
| **O9** | **Dev infrastructure: mock mode, search cache, local LLM** | `AGENTOPS_MODE=mock` runs the full pipeline with no external API calls; search cache reduces Tavily calls by ≥80% during dev |

### Secondary Objectives

- System handles parallel researcher execution with configurable concurrency (N=1 to N=5)
- All configuration externalised to `values.yaml` (no hardcoded values)
- Full reproducibility: `make deploy` brings up the entire system from scratch on any machine with minikube installed
- Honest post-mortem section in README documenting what broke during development and why

---

## 4. Skills Learned

### 4.1 Kubernetes — New, Zero Previous Exposure

By the end of this project you will have written and deployed real Kubernetes manifests, not followed a tutorial. Specifically:

- **Core primitives**: `Deployment`, `Service`, `ConfigMap`, `Secret`, `PersistentVolumeClaim` — what each controls and why they are separated
- **Health probes**: implementing `/healthz` (liveness) and `/readyz` (readiness) endpoints in FastAPI and configuring k8s to use them
- **Resource management**: CPU and memory `requests` and `limits` per container
- **Networking**: `ClusterIP` vs `NodePort`, and why the API gateway is the only externally exposed component
- **Helm**: writing `Chart.yaml`, `values.yaml`, and templated manifests, with per-environment overrides (`values.dev.yaml`, `values.ci.yaml`)
- **minikube**: running a real single-node k8s cluster locally; `kubectl logs`, `exec`, `describe`, `port-forward` for debugging
- **Mental model**: why container orchestration exists, what problems it solves over Docker Compose

### 4.2 Advanced Multi-Agent Orchestration Patterns — New

- **Fan-out / fan-in (scatter-gather)**: dispatching N parallel research subtasks and aggregating results, handling partial-failure correctly
- **Dynamic routing**: orchestrator decides researcher count at runtime based on query complexity
- **Agent memory hierarchy**: short-term (per-run `StateGraph`) vs long-term (cross-run vector store)
- **Schema-validated handoffs**: Pydantic at every inter-agent boundary
- **Circuit breaker pattern**: if an agent fails 3+ consecutive times, switch source or demote the task
- **Self-healing state machine**: RECOVERY states with explicit semantics (see §6)

### 4.3 Production Observability with Arize Phoenix — New

- **Session-level aggregation**: all agent calls within one run grouped as one session
- **Metric dashboards**: token cost per agent, p50/p95 latency, success/failure rates, hallucination trend, budget utilisation
- **Span instrumentation**: OpenTelemetry decorators capturing the full execution tree
- **Cost telemetry**: per-call token counting accumulated to a per-run budget tracker
- **Alert thresholds**: Phoenix flags runs where hallucination score or cost exceed configured limits

### 4.4 Hash-Chained Audit Logging & AI Governance — New

- **Tamper-evident log design**: each entry stores `prev_hash` (SHA-256 of previous entry's canonical serialisation); any modification breaks the chain and is detectable by a verifier
- **NIST AI RMF mapping**: which RMF functions (GOVERN, MAP, MEASURE, MANAGE) each system component satisfies, documented in README
- **Run lineage**: every delivered report traceable back through every agent decision that produced it

### 4.5 Token Budget Enforcement — Deepened from RogueLLM

- **Pre-run estimation** based on query length and configured agent count
- **Real-time enforcement** via `BudgetGuard` middleware; halts on threshold exceedance
- **Partial report delivery** with structured `BudgetExceededError` rather than empty error
- **Per-agent cost attribution** for optimisation

### 4.6 Dev Infrastructure as First-Class Engineering — New

The discipline of building production-realistic dev tooling before writing the production code:

- **Mock-mode toggle**: `AGENTOPS_MODE=mock` swaps all external calls (LLMs, Tavily) for deterministic in-process fakes — unit tests and CI smoke tests use this
- **Search result cache**: disk-backed cache (keyed by SHA-256 of query) reduces Tavily quota usage by ≥80% during dev
- **Local LLM dev mode**: Ollama with `qwen2.5:7b` runs locally for fast iteration without rate limits; Groq used only for integration tests and the live demo
- **Three execution modes** are first-class: `mock` (no network), `local` (Ollama only), `cloud` (Groq + Tavily) — selectable via env var

### 4.7 Skills Deepened from RogueLLM

| Skill | What's New at the AgentOps Level |
|-------|----------------------------------|
| LangGraph | State machine with RECOVERY states, dynamic routing, fan-out/fan-in |
| LangSmith | Session-level cost aggregation, multi-agent trace linking |
| FastAPI | k8s health endpoints, async background tasks, structured error responses |
| GitHub Actions | k8s smoke-test deployment job, minikube provisioning in CI |
| Async Python | `asyncio.gather()` with `return_exceptions=True`, timeout handling |
| Pydantic | Inter-agent contract validation, structured error types, `BaseSettings` |
| Evaluation | RogueLLM engine repurposed as cross-family Quality Gate |

---

## 5. System Architecture

### 5.1 Agent Pipeline

```
                    ┌─────────────────────────────┐
                    │         API Gateway          │
                    │    FastAPI  /run  /status    │
                    │    /healthz  /readyz  /audit │
                    └─────────────┬───────────────┘
                                  │
                    ┌─────────────▼───────────────┐
                    │      Pipeline Orchestrator    │
                    │   LangGraph StateGraph        │
                    │   Budget Guard  │  Audit Log  │
                    └──────┬──────────────────┬────┘
                           │                  │
               ┌───────────▼──────┐    ┌──────▼──────────────┐
               │  Planner Agent   │    │   Observability      │
               │  Query → Subtask │    │   Arize Phoenix      │
               │  decomposition   │    │   LangSmith          │
               └───────────┬──────┘    └─────────────────────┘
                           │  N subtasks (parallel fan-out)
          ┌────────────────┼────────────────┐
          │                │                │
┌─────────▼───┐  ┌─────────▼───┐  ┌────────▼────┐
│ Researcher 1│  │ Researcher 2│  │ Researcher 3│
│ Web + KB    │  │ Web + KB    │  │ Web + KB    │
│ + Cache     │  │ + Cache     │  │ + Cache     │
└─────────┬───┘  └─────────┬───┘  └────────┬────┘
          │                │               │
          └────────────────┼───────────────┘
                           │  fan-in (partial results tolerated)
               ┌───────────▼──────┐
               │   Critic Agent   │
               │  Embedding-      │
               │  contradiction   │
               │  floor + LLM     │
               │  adjudication    │
               └───────────┬──────┘
                           │
               ┌───────────▼──────┐
               │   Writer Agent   │
               │   Structured     │◄──── REVISION loop
               │   report         │      (max 2 revisions)
               └───────────┬──────┘
                           │
               ┌───────────▼──────────────┐
               │   Quality Gate Agent     │
               │   RogueLLM eval engine   │
               │   (different model       │
               │    family than Writer)   │
               │   PASS / REVISION / FAIL │
               └───────────┬──────────────┘
                           │
               ┌───────────▼──────┐
               │ Delivered Report │
               │ + Audit Trail    │
               │ + Cost Summary   │
               └──────────────────┘
```

### 5.2 Self-Healing State Machine

```
                    ┌──────────┐
              ┌────►│ PLANNING │
              │     └────┬─────┘
              │          │ success
              │     ┌────▼────────┐
              │     │ RESEARCHING │◄──────────┐
              │     └────┬────────┘           │
              │          │ ≥1 finding         │
              │     ┌────▼────────┐           │
              │     │ CRITICISING │           │
              │     └────┬────────┘           │
              │          │ proceed            │
              │     ┌────▼────────┐           │
              │     │   WRITING   │           │
              │     └────┬────────┘           │
              │          │                    │
              │     ┌────▼────────────────┐   │
              │     │   QUALITY_CHECK     │   │
              │     └────┬──────┬─────────┘   │
              │          │      │ revision     │
              │          │      └─────────────►┘ (Writer retry, max 2)
              │     PASS │
              │     ┌────▼────┐   ┌──────────────┐
              │     │  DONE   │   │   RECOVERY   │◄── any state failure
              │     └─────────┘   └──────┬───────┘
              │                          │
              └──────────────────────────┘
                  retry | degrade | abort
```

**RECOVERY state semantics** (explicit, not implied):

| Trigger | Action | Max attempts | Fallback |
|---------|--------|--------------|----------|
| Researcher timeout / exception | Retry with same subtask, exponential backoff (1s, 2s, 4s) | 3 | Mark task failed, continue if ≥1 other finding succeeded |
| Critic `proceed_recommendation=False` | Re-run lowest-confidence researchers with broader keywords | 1 | Degrade: proceed to Writer with available findings, flag in report |
| Writer schema validation failure | Retry with explicit error message appended to prompt | 2 | Abort run, return partial findings as raw markdown |
| Quality Gate `REVISION` | Send report back to Writer with flagged claims | 2 (config: `maxRevisions`) | Forced `FAIL`, deliver best version with quality summary |
| BudgetExceededError | No retry — halt immediately | 0 | Deliver partial report with `status: budget_exceeded` |

### 5.3 Kubernetes Deployment Architecture

```
┌────────────────────────── minikube cluster ─────────────────────────┐
│                                                                       │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐  │
│  │   api-gateway   │    │  orchestrator   │    │    phoenix-obs  │  │
│  │   Deployment    │    │   Deployment    │    │   Deployment    │  │
│  │   FastAPI       │    │   LangGraph     │    │   Arize Phoenix │  │
│  │   /1 replica    │    │   /1 replica    │    │   /1 replica    │  │
│  └────────┬────────┘    └────────┬────────┘    └─────────────────┘  │
│           │ NodePort             │ ClusterIP                         │
│           │ 30080                │                                    │
│  ┌────────▼──────────────────────▼─────────────────────────────┐    │
│  │                    ConfigMap: agentops-config                │    │
│  │      model names, timeouts, budget limits, MODE selector     │    │
│  └─────────────────────────────────────────────────────────────┘    │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                    Secret: agentops-secrets                  │    │
│  │              GROQ_API_KEY, TAVILY_API_KEY, LANGSMITH_API_KEY │    │
│  └─────────────────────────────────────────────────────────────┘    │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │              PersistentVolumeClaim: audit-log-pvc            │    │
│  │             hash-chained SQLite audit DB                     │    │
│  └─────────────────────────────────────────────────────────────┘    │
└───────────────────────────────────────────────────────────────────── ┘

External access:  http://$(minikube ip):30080
```

### 5.4 Hash-Chained Audit Log Schema

```sql
CREATE TABLE audit_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          TEXT NOT NULL,
    agent_type      TEXT NOT NULL,
    timestamp_utc   TEXT NOT NULL,
    input_hash      TEXT NOT NULL,         -- SHA-256 of input
    output_hash     TEXT NOT NULL,         -- SHA-256 of output
    model_id        TEXT NOT NULL,
    model_version   TEXT NOT NULL,
    latency_ms      INTEGER NOT NULL,
    prompt_tokens   INTEGER NOT NULL,
    completion_tokens INTEGER NOT NULL,
    confidence_score REAL,
    reasoning_trace TEXT,                  -- JSON, truncated if > 4KB
    parent_run_id   TEXT,
    status          TEXT NOT NULL,         -- SUCCESS, RECOVERED, FAILED, BUDGET_HALTED
    prev_hash       TEXT NOT NULL,         -- SHA-256 of previous row's canonical JSON
    entry_hash      TEXT NOT NULL          -- SHA-256 of this row's canonical JSON
);

-- entry_hash = SHA256(canonical_json(all fields except entry_hash itself))
-- prev_hash of row N = entry_hash of row N-1 (or "0"*64 for row 1)
-- Tamper detection: a verifier walks the chain; any altered row breaks it.
```

A `verify_chain()` utility is implemented and tested. It is run at the end of every integration test asserting log integrity.

---

## 6. Implementation Phases

### Phase 0 — Project Setup & Dev Infrastructure *(Week 1, days 1–4)*

Establish the engineering foundation **including the dev infrastructure that makes the rest of the project possible**. Most agent projects fail not because the agents don't work but because the dev loop is too slow or too expensive. We fix that up front.

**Tasks:**

- Initialise Git repo with `.gitignore`, `README.md`, `LICENSE`, `CLAUDE.md`
- Python 3.11+ env with `uv` and `pyproject.toml`
- `pre-commit` hooks: `black`, `ruff`, `mypy`
- Install and verify `minikube`, `kubectl`, `helm`
- Install Ollama, pull `qwen2.5:7b` model, verify with `ollama run qwen2.5:7b`
- Start Arize Phoenix locally via Docker (`docker run -p 6006:6006 arizephoenix/phoenix`)
- Create skeleton `charts/agentops/` Helm chart
- **Build the three-mode execution toggle:**
  - `AGENTOPS_MODE=mock` → all LLM calls and search calls return deterministic fixtures from `tests/fixtures/`
  - `AGENTOPS_MODE=local` → LLMs go to Ollama; search calls go through disk cache, miss → Tavily
  - `AGENTOPS_MODE=cloud` → LLMs go to Groq; search calls go through disk cache, miss → Tavily
- **Build the search cache** (`src/dev/search_cache.py`): `diskcache`-backed, keyed by SHA-256 of query string, TTL 30 days
- **Build the LLM client abstraction** (`src/llm/client.py`): single `get_llm_client(role)` factory that returns the appropriate client based on mode and role (`generation` vs `evaluation` — different models)
- Write `Makefile` targets: `make test`, `make lint`, `make run-mock`, `make run-local`, `make deploy`, `make teardown`
- Create `.env.example` with all required keys documented

**Phase 0 Deliverable:** Repo skeleton where `make lint` passes, `make run-mock` executes a stubbed pipeline end-to-end in <5 seconds with zero external calls, Ollama responds to a local prompt, and Phoenix UI is accessible at `localhost:6006`.

---

### Phase 1 — Agent Implementations *(Week 1 day 5 → Week 2)*

Build each agent as an independent, testable Python class. Every agent ships with ≥5 unit tests using mock mode.

**Planner Agent** (`src/agents/planner.py`)

```python
class ResearchPlan(BaseModel):
    query: str
    subtasks: list[ResearchSubtask]      # 1-5 items
    estimated_complexity: Literal["low", "medium", "high"]
    recommended_researcher_count: int    # 1-3
```

Uses structured JSON output (`response_format={"type": "json_object"}`). Unit tests assert schema validity on 5 known queries.

**Researcher Agent** (`src/agents/researcher.py`)

```python
class ResearchFinding(BaseModel):
    task_id: str
    summary: str                  # max 500 tokens
    key_facts: list[str]          # 3-7 bullets
    sources: list[SourceCitation]
    confidence_score: float       # 0.0–1.0
    data_gaps: list[str]
```

Uses Tavily Search API (through the Phase 0 cache) + local FAISS KB seeded with Wikipedia/arXiv abstracts. Source citations are structured (URL, title, relevance score).

**Critic Agent** (`src/agents/critic.py`)

```python
class CriticReport(BaseModel):
    verified_facts: list[VerifiedFact]
    contradictions: list[Contradiction]
    low_confidence_items: list[str]   # task_ids with confidence < 0.4
    overall_evidence_quality: float
    proceed_recommendation: bool
```

**Two-stage contradiction detection** (this is new vs v1.0):

1. **Deterministic floor**: compute `sentence-transformers` embeddings for every fact across researcher outputs. Pairs with cosine similarity > 0.85 *and* opposite polarity (detected via simple negation heuristics) are flagged as candidate contradictions.
2. **LLM adjudication**: only the flagged candidate pairs are sent to the LLM for final contradiction classification. This bounds the LLM's role to a constrained judgement, reducing fabricated contradictions.

If `overall_evidence_quality < 0.3`, sets `proceed_recommendation=False` and triggers RECOVERY.

**Writer Agent** (`src/agents/writer.py`)

```python
class ResearchReport(BaseModel):
    title: str
    executive_summary: str          # max 200 words
    sections: list[ReportSection]
    confidence_bands: dict[str, float]
    data_gaps_acknowledged: list[str]
    revision_count: int
```

Section-by-section generation (one LLM call per section, grounded in Critic-verified facts) — measurably better faithfulness than single-prompt generation.

**Quality Gate Agent** (`src/agents/quality_gate.py`)

```python
class QualityDecision(BaseModel):
    decision: Literal["PASS", "REVISION", "FAIL"]
    faithfulness_score: float
    hallucination_score: float
    flagged_claims: list[FlaggedClaim]
    revision_instruction: str | None
```

Runs RAGAS faithfulness + DeepEval hallucination from the RogueLLM eval engine. **The LLM used for evaluation is from a different model family than the Writer's LLM** — configured via `LLM_GENERATION_MODEL` vs `LLM_EVALUATION_MODEL` in ConfigMap. In `local` mode, this means Ollama qwen2.5 for generation, Ollama llama3.1 for eval. In `cloud` mode, this means Groq LLaMA-3.3 for generation, Groq Mixtral for eval.

**RogueLLM integration mechanics**: install as `pip install -e ../rogue-llm` from a sibling directory, with the exact commit hash pinned in `pyproject.toml`. No git submodules.

**Phase 1 Deliverable:** Five agent classes, each with ≥5 unit tests passing in mock mode. Pydantic schemas validated.

---

### Phase 2 — Multi-Agent Orchestration *(Week 3)*

LangGraph `StateGraph` with self-healing, parallel fan-out, budget enforcement.

**State Schema:**

```python
class PipelineState(TypedDict):
    run_id: str
    query: str
    plan: ResearchPlan | None
    findings: list[ResearchFinding]
    failed_tasks: list[str]
    critic_report: CriticReport | None
    report: ResearchReport | None
    quality_decision: QualityDecision | None
    revision_count: int
    recovery_attempts: dict[str, int]    # per-state recovery counter
    budget_tracker: BudgetTracker
    audit_entries: list[AuditEntry]
    pipeline_status: PipelineStatus
    error: PipelineError | None
```

**State Graph:**

```python
graph = StateGraph(PipelineState)
graph.add_node("plan", planning_node)
graph.add_node("research", research_node)
graph.add_node("critique", critique_node)
graph.add_node("write", write_node)
graph.add_node("quality_check", quality_check_node)
graph.add_node("recover", recovery_node)

graph.add_conditional_edges("quality_check", route_quality_decision, {
    "PASS": END, "REVISION": "write", "FAIL": END,
})
graph.add_conditional_edges("critique", route_critique_decision, {
    "proceed": "write", "recover": "recover",
})
graph.add_conditional_edges("recover", route_recovery, {
    "retry_research": "research",
    "degrade_to_write": "write",
    "abort": END,
})
```

**Parallel Researcher Execution:**

```python
async def research_node(state: PipelineState) -> PipelineState:
    tasks = [
        run_researcher_with_timeout(subtask, timeout_s=30)
        for subtask in state["plan"].subtasks
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    findings, failed = [], []
    for subtask, result in zip(state["plan"].subtasks, results):
        if isinstance(result, Exception):
            failed.append(subtask.task_id)
            log_audit(state, subtask.task_id, "RESEARCHER_FAILED", str(result))
        else:
            findings.append(result)
    return {**state, "findings": findings, "failed_tasks": failed}
```

**Budget Guard:**

```python
class BudgetGuard:
    def __init__(self, budget_tokens: int):
        self.budget = budget_tokens
        self.spent = 0

    def check_and_charge(self, prompt_tokens: int, completion_tokens: int,
                         model: str, agent_type: str) -> None:
        cost = prompt_tokens + completion_tokens
        if self.spent + cost > self.budget:
            raise BudgetExceededError(
                spent=self.spent, budget=self.budget,
                agent=agent_type, attempted=cost
            )
        self.spent += cost
```

**Phase 2 Deliverable:** `make run-local` executes a full pipeline end-to-end via Ollama. An integration test injects a researcher timeout and asserts RECOVERY → retry → success.

---

### Phase 3 — Observability & Audit *(Week 4 days 1–4)*

**LangSmith session grouping** — explicit run metadata so all agent calls within one pipeline run group as a single LangSmith session.

**Arize Phoenix instrumentation:**

```python
import phoenix as px
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider

px.launch_app()
provider = TracerProvider()
trace.set_tracer_provider(provider)
tracer = trace.get_tracer(__name__)

def trace_agent(agent_type: str):
    def decorator(func):
        async def wrapper(state, *args, **kwargs):
            with tracer.start_as_current_span(agent_type) as span:
                span.set_attribute("run_id", state["run_id"])
                span.set_attribute("budget_spent", state["budget_tracker"].spent)
                result = await func(state, *args, **kwargs)
                span.set_attribute("tokens_this_call", result.get("tokens_used", 0))
                return result
        return wrapper
    return decorator
```

Phoenix dashboards configured: token cost per agent, p50/p95 latency per stage, agent success rates, hallucination score trend, budget utilisation.

**Hash-chained Audit Log:** see §5.4 for schema. `AuditLogger` class implements `append(entry)` which computes `entry_hash` and sets `prev_hash` from the previous row. `verify_chain()` walks the chain and asserts integrity. Integration tests run `verify_chain()` after every test pipeline run.

**Phase 3 Deliverable:** A complete pipeline run where LangSmith shows the full session, Phoenix dashboard shows token cost + latency, audit DB has a complete entry for every agent call, and `verify_chain()` returns `True`.

---

### Phase 4 — Kubernetes Deployment *(Week 4 day 5 → Week 5)*

Three Dockerised components: `api-gateway`, `orchestrator`, `phoenix-obs` (official image).

**Dockerfile pattern (api-gateway):**

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN pip install uv && uv sync --no-dev
COPY src/ ./src/
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8000/healthz || exit 1
CMD ["uv", "run", "uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**FastAPI Health Endpoints:**

```python
@app.get("/healthz")
async def liveness() -> dict:
    return {"status": "alive"}

@app.get("/readyz")
async def readiness() -> dict:
    checks = {
        "orchestrator": await check_orchestrator_reachable(),
        "audit_db": check_audit_db_writable(),
        "budget_guard": True,
    }
    return {"status": "ready" if all(checks.values()) else "not_ready", "checks": checks}
```

**Helm chart structure:**

```
charts/agentops/
├── Chart.yaml
├── values.yaml              # defaults
├── values.dev.yaml          # minikube/local overrides
├── values.ci.yaml           # CI overrides (phoenix.enabled=false, low budget)
└── templates/
    ├── _helpers.tpl
    ├── configmap.yaml
    ├── secret.yaml
    ├── api-gateway/
    ├── orchestrator/
    ├── phoenix/
    └── audit-log/
```

`values.yaml` excerpt:

```yaml
global:
  image:
    tag: "latest"
  mode: "cloud"               # mock | local | cloud
  budget:
    defaultTokenLimit: 50000
apiGateway:
  replicaCount: 1
  service:
    type: NodePort
    nodePort: 30080
orchestrator:
  replicaCount: 1
  agent:
    maxResearchers: 3
    researcherTimeoutSecs: 30
    maxRevisions: 2
phoenix:
  enabled: true               # set false in values.ci.yaml
  persistence:
    size: 1Gi
```

**Deploy workflow (`make deploy`):**

```bash
minikube start --cpus=4 --memory=6g
eval $(minikube docker-env)
docker build -t agentops-api:latest -f docker/api.Dockerfile .
docker build -t agentops-orchestrator:latest -f docker/orchestrator.Dockerfile .
kubectl create secret generic agentops-secrets \
  --from-env-file=.env --dry-run=client -o yaml | kubectl apply -f -
helm upgrade --install agentops ./charts/agentops -f charts/agentops/values.dev.yaml
kubectl rollout status deployment/agentops-api-gateway
echo "API: http://$(minikube ip):30080"
```

**Phase 4 Deliverable:** `make deploy` completes. `kubectl get pods` shows all Running. `curl` against the NodePort returns a valid pipeline response.

---

### Phase 5 — CI/CD with Kubernetes Smoke Test *(Week 6 days 1–3)*

```yaml
# .github/workflows/ci.yml — every push/PR
jobs:
  lint-test:       # ruff, mypy, pytest (mock mode), coverage

# .github/workflows/e2e-smoke.yml — PR to main touching src/**
jobs:
  k8s-smoke-test:
    runs-on: ubuntu-latest
    steps:
      - uses: medyagh/setup-minikube@latest
        with: { cpus: 2, memory: 4g }
      - name: Build images
        run: |
          eval $(minikube docker-env)
          docker build -t agentops-api:latest -f docker/api.Dockerfile .
          docker build -t agentops-orchestrator:latest -f docker/orchestrator.Dockerfile .
      - name: Deploy (CI values)
        run: |
          kubectl create secret generic agentops-secrets \
            --from-literal=GROQ_API_KEY=${{ secrets.GROQ_API_KEY }} \
            --from-literal=TAVILY_API_KEY=${{ secrets.TAVILY_API_KEY }} \
            --from-literal=LANGSMITH_API_KEY=${{ secrets.LANGSMITH_API_KEY }}
          helm upgrade --install agentops ./charts/agentops \
            -f charts/agentops/values.ci.yaml
          kubectl rollout status deployment/agentops-api-gateway --timeout=180s
      - name: Smoke test
        run: |
          API_URL="http://$(minikube ip):30080"
          RESPONSE=$(curl -sf -X POST "$API_URL/run" \
            -H "Content-Type: application/json" \
            -d '{"query":"What is FAISS?","max_researchers":1}')
          echo "$RESPONSE" | python -c "
          import sys, json
          r = json.load(sys.stdin)
          assert r['status'] in ['completed', 'budget_exceeded']
          "
```

`values.ci.yaml` sets `phoenix.enabled: false` and `global.budget.defaultTokenLimit: 5000` to keep CI fast.

**Phase 5 Deliverable:** Both workflows green. CI smoke test completes in <8 minutes.

---

### Phase 6 — Documentation, Demo & Polish *(Week 6 days 4–5)*

**README sections:** What It Does, Headline Result, Architecture (inline SVG), Quick Start, Agent Design, Kubernetes Guide, Observability, Audit Log Verification, Honest Findings, RogueLLM Integration, Roadmap.

**Demo artifacts:**
- `asciinema` recording of `make deploy` → `curl` → delivered report
- Screenshots: Phoenix dashboard, LangSmith session, `kubectl get pods`
- Example report in `examples/`
- Example audit log SQLite file in `examples/` with `verify_chain()` output

**Honest Findings (required section):** ≥3 things that did not work as planned during development, with root cause and how you handled it.

**Phase 6 Deliverable:** Repo tells its own story without requiring the reader to run anything.

---

## 7. Technical Stack

### Core

| Category | Tool | Notes |
|----------|------|-------|
| Language | Python 3.11+ | |
| Package manager | `uv` | |
| LLM (cloud generation) | Groq LLaMA-3.3-70B | Free tier |
| LLM (cloud eval, different family) | Groq Mixtral-8x7B | Free tier |
| LLM (local dev) | Ollama `qwen2.5:7b` | |
| LLM (local eval) | Ollama `llama3.1:8b` | Cross-family for eval |
| Web Search | Tavily (free tier, 1k/mo) | Behind disk cache |
| Search cache | `diskcache` | SHA-256 keyed, 30-day TTL |
| Agent framework | LangGraph 0.3+ | |
| API framework | FastAPI | |

### Observability

| Tool | Purpose | Cost |
|------|---------|------|
| Arize Phoenix | System dashboards | Free self-hosted |
| LangSmith | Call-level traces | Free tier |
| OpenTelemetry | Span standard | Free |
| structlog | Structured logs | Free |

### Infrastructure

| Tool | Purpose | Cost |
|------|---------|------|
| minikube | Local k8s | Free |
| kubectl, Helm 3 | Cluster mgmt | Free |
| Docker Desktop | Container builds | Free |
| GitHub Actions | CI/CD | Free (2000 min/mo) |

### Evaluation (from RogueLLM, installed as editable pip package)

| Tool | Purpose |
|------|---------|
| RAGAS | Faithfulness in Quality Gate |
| DeepEval | Hallucination in Quality Gate |

### Data

| Tool | Purpose |
|------|---------|
| FAISS | Local vector KB |
| sentence-transformers (`all-MiniLM-L6-v2`) | Embeddings (also used by Critic floor) |
| SQLite | Hash-chained audit log |
| Pydantic v2 | Schema validation |

---

## 8. Repository Structure

```
agent-ops/
├── .github/
│   ├── workflows/
│   │   ├── ci.yml
│   │   └── e2e-smoke.yml
│   └── PULL_REQUEST_TEMPLATE.md
├── charts/
│   └── agentops/
│       ├── Chart.yaml
│       ├── values.yaml
│       ├── values.dev.yaml
│       ├── values.ci.yaml
│       └── templates/
├── docker/
│   ├── api.Dockerfile
│   └── orchestrator.Dockerfile
├── k8s/
├── src/
│   ├── __init__.py
│   ├── config.py
│   ├── api/
│   │   ├── main.py
│   │   └── models.py
│   ├── agents/
│   │   ├── base.py
│   │   ├── planner.py
│   │   ├── researcher.py
│   │   ├── critic.py
│   │   ├── writer.py
│   │   └── quality_gate.py
│   ├── orchestration/
│   │   ├── graph.py
│   │   ├── state.py
│   │   ├── nodes.py
│   │   └── routing.py
│   ├── budget/
│   │   └── guard.py
│   ├── observability/
│   │   ├── phoenix_setup.py
│   │   ├── langsmith_setup.py
│   │   └── tracing.py
│   ├── audit/
│   │   ├── log.py             # AuditLogger with hash chaining
│   │   ├── verify.py          # verify_chain()
│   │   └── schema.sql
│   ├── llm/
│   │   ├── client.py          # mode-aware LLM client factory
│   │   └── models.py
│   └── dev/
│       ├── search_cache.py    # diskcache-backed Tavily wrapper
│       ├── mocks.py           # fixtures for mock mode
│       └── ollama_client.py
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── k8s/
│   │   └── smoke_test.py
│   └── fixtures/              # canned LLM and search responses for mock mode
├── examples/
│   ├── query_what_is_faiss.json
│   ├── report_what_is_faiss.md
│   └── audit_log_example.sqlite
├── notebooks/
├── .env.example
├── .gitignore
├── .pre-commit-config.yaml
├── CLAUDE.md
├── IMPLEMENTATION_NOTES.md
├── LICENSE
├── Makefile
├── PROJECT_SPEC.md
├── README.md
├── pyproject.toml
└── uv.lock
```

---

## 9. Git Workflow

Same GitHub Flow as RogueLLM, plus mandatory k8s smoke test before merging to main.

```
main           (protected: PR + CI green + k8s smoke green)
├── dev
│   ├── feat/phase-0-setup
│   ├── feat/phase-1-agents
│   ├── feat/phase-2-orchestration
│   ├── feat/phase-3-observability
│   ├── feat/phase-4-kubernetes
│   ├── feat/phase-5-cicd
│   └── feat/phase-6-polish
```

Commit convention (Conventional Commits): `feat`, `fix`, `test`, `docs`, `ci`, `k8s`, `chore`. One GitHub Issue per phase, milestones with target dates, labels for tracking.

---

## 10. Evaluation Metrics & Success Criteria

### System-Level

| Criterion | Target | How Measured |
|-----------|--------|-------------|
| Pipeline E2E completion | Runs without crash on 5 diverse queries | Manual + CI |
| Self-healing verification | Recovers from injected researcher timeout | Integration test |
| k8s deployment | All pods Running after `make deploy` | `kubectl get pods` |
| Helm chart idempotency | `helm upgrade --install` succeeds repeatedly | CI |
| Budget enforcement | Halts correctly at limit | Unit test |
| Audit log completeness | Every agent call has matching audit entry | Integration test |
| **Audit log integrity** | **`verify_chain()` returns True after any run** | **Integration test** |
| Test coverage | ≥ 80% on `src/` | `pytest --cov` |
| CI pipeline | Both workflows green on PR to main | GitHub Actions |
| Phoenix dashboard | Token cost + latency charts populated | Manual |
| Quality Gate cross-family | Eval LLM is different family from Writer LLM | Config assertion in test |
| Mock-mode runtime | Full pipeline runs in <5s with zero external calls | Timed test |

### Report Quality

| Metric | Target | Source |
|--------|--------|--------|
| Faithfulness | ≥ 0.75 | RAGAS |
| Hallucination | ≤ 0.20 | DeepEval |
| Delivery rate | ≥ 80% of queries PASS within 2 revisions | Run logs |

---

## 11. Week-by-Week Timeline

The project is 6 content-weeks. Calendar time will depend on hours/week available — at ~15 hr/week this is ~10 calendar weeks; at ~25 hr/week it's ~6 calendar weeks.

### Week 1 — Setup, Dev Infrastructure, Start Agents

| Day | Task | Branch |
|-----|------|--------|
| 1 | Phase 0: Repo, uv, pre-commit, minikube/kubectl/helm verify | `feat/phase-0-setup` |
| 2 | Phase 0: Ollama install + qwen2.5:7b pull, Phoenix Docker, Makefile | `feat/phase-0-setup` |
| 3 | Phase 0: Search cache, mock fixtures, three-mode toggle, LLM client factory | `feat/phase-0-setup` |
| 4 | Phase 0: Helm skeleton, .env.example, CLAUDE.md, `make run-mock` passing | `feat/phase-0-setup` |
| 5 | Phase 1: Planner agent + Pydantic + 5 unit tests in mock mode | `feat/phase-1-agents` |

### Week 2 — Agents Complete

| Day | Task | Branch |
|-----|------|--------|
| 6 | Phase 1: Researcher agent + Tavily-through-cache + FAISS KB seeding | `feat/phase-1-agents` |
| 7 | Phase 1: Critic agent (embedding floor + LLM adjudication) + unit tests | `feat/phase-1-agents` |
| 8 | Phase 1: Writer agent (section-by-section) + unit tests | `feat/phase-1-agents` |
| 9 | Phase 1: Quality Gate (cross-family eval, RogueLLM integration) + tests | `feat/phase-1-agents` |
| 10 | Phase 1: Cross-agent integration test in mock mode | `feat/phase-1-agents` |

### Week 3 — Orchestration

| Day | Task | Branch |
|-----|------|--------|
| 11 | Phase 2: StateGraph, PipelineState, linear flow working in mock mode | `feat/phase-2-orchestration` |
| 12 | Phase 2: Parallel researcher fan-out (`asyncio.gather`) | `feat/phase-2-orchestration` |
| 13 | Phase 2: RECOVERY state, all 5 trigger paths from §5.2 | `feat/phase-2-orchestration` |
| 14 | Phase 2: BudgetGuard integration end-to-end | `feat/phase-2-orchestration` |
| 15 | Phase 2: `make run-local` passes (real Ollama LLM, real Tavily-cached search) | `feat/phase-2-orchestration` |

### Week 4 — Observability & Audit

| Day | Task | Branch |
|-----|------|--------|
| 16 | Phase 3: OpenTelemetry + Phoenix instrumentation, decorator pattern | `feat/phase-3-observability` |
| 17 | Phase 3: LangSmith session grouping + cost telemetry | `feat/phase-3-observability` |
| 18 | Phase 3: Hash-chained audit log (`AuditLogger`, `verify_chain`) + tests | `feat/phase-3-observability` |
| 19 | Phase 3: Dashboards configured, end-to-end integration test | `feat/phase-3-observability` |
| 20 | Phase 4: Dockerfiles for api-gateway + orchestrator, local build verified | `feat/phase-4-kubernetes` |

### Week 5 — Kubernetes

| Day | Task | Branch |
|-----|------|--------|
| 21 | Phase 4: k8s manifests (Deployment, Service, ConfigMap, Secret, PVC) | `feat/phase-4-kubernetes` |
| 22 | Phase 4: Helm chart templating, `values.yaml` + `values.dev.yaml` | `feat/phase-4-kubernetes` |
| 23 | Phase 4: `make deploy` works on minikube, all pods Running | `feat/phase-4-kubernetes` |
| 24 | Phase 4: Health probes verified, NodePort tested, `curl` returns valid response | `feat/phase-4-kubernetes` |
| 25 | Phase 4: `values.ci.yaml` (phoenix off, low budget), buffer day for k8s debugging | `feat/phase-4-kubernetes` |

### Week 6 — CI/CD & Polish

| Day | Task | Branch |
|-----|------|--------|
| 26 | Phase 5: `ci.yml` (lint, test, coverage) | `feat/phase-5-cicd` |
| 27 | Phase 5: `e2e-smoke.yml` (minikube provisioning + Helm + smoke) | `feat/phase-5-cicd` |
| 28 | Phase 5: PR status comment automation, both workflows green | `feat/phase-5-cicd` |
| 29 | Phase 6: README, architecture SVG, asciinema recording, screenshots | `feat/phase-6-polish` |
| 30 | Phase 6: IMPLEMENTATION_NOTES, Honest Findings, examples/, `dev → main` | `feat/phase-6-polish` |

---

## 12. Deliverables

| Deliverable | Description |
|-------------|-------------|
| GitHub Repository | Clean, well-documented, fully deployable via `make deploy` |
| Helm Chart | `helm install agentops ./charts/agentops` deploys the full stack |
| Phoenix Dashboard | Screenshot of live token cost + latency from a completed run |
| LangSmith Session | Public link to a real 5-agent pipeline session trace |
| CI/CD Pipeline | Two live GitHub Actions workflows: lint/test + k8s smoke |
| Hash-Chained Audit Log | Example SQLite committed in `examples/` with `verify_chain()` output |
| Example Report | A real pipeline-generated report in `examples/` |
| Mock-Mode Demo | `make run-mock` runs full pipeline in <5s with zero external calls |
| README | Architecture diagram, Phoenix screenshot, `kubectl get pods` screenshot, Honest Findings |

---

## 13. References

**Multi-Agent & Orchestration**
- LangGraph Documentation: https://langchain-ai.github.io/langgraph/
- Scatter-Gather Pattern: https://www.enterpriseintegrationpatterns.com/

**Kubernetes & Helm**
- Kubernetes Documentation: https://kubernetes.io/docs/
- Helm Chart Best Practices: https://helm.sh/docs/chart_best_practices/
- minikube Documentation: https://minikube.sigs.k8s.io/docs/

**Observability**
- Arize Phoenix Documentation: https://docs.arize.com/phoenix
- OpenTelemetry Python: https://opentelemetry.io/docs/instrumentation/python/
- "Observability Engineering" — Charity Majors et al. (O'Reilly, 2022)

**AI Governance & Audit Logging**
- NIST AI Risk Management Framework: https://airc.nist.gov/
- EU AI Act — Annex III: https://eur-lex.europa.eu/
- Hash-chained logs: see Certificate Transparency RFC 6962 §2 for the canonical pattern

**Local LLM**
- Ollama: https://ollama.com/
- Qwen2.5 model card: https://huggingface.co/Qwen/Qwen2.5-7B-Instruct

**Evaluation (from RogueLLM)**
- RAGAS: https://docs.ragas.io/
- DeepEval: https://docs.confident-ai.com/

---

*This document is version-controlled alongside the project codebase.
Update it as implementation decisions evolve — treat deviations from the spec as engineering decisions worth documenting, not failures.*
