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

## Phase 4 M1 — FastAPI Gateway Design

- **Async API model.** `POST /run` returns 202 immediately with a `run_id`. Pipeline executes in an `asyncio.Task`. `GET /status/{run_id}` polls completion. Sync API (block-and-return) was rejected because 10+ second blocking endpoints don't survive load balancer timeouts in real deployments.
- **In-memory run registry.** Single-process scope. Multi-replica deployments would need Redis-backed or DB-backed registry. The k8s Deployment in M3 will have `replicas: 1`, which makes this acceptable.
- **Health probe semantics.** `/healthz` is process liveness only (always 200 if the process responds). `/readyz` checks orchestrator and audit DB writability; returns 503 (not 200 + `not_ready`) when checks fail, because k8s reads HTTP status code.
- **Background task safety.** `_execute_pipeline` catches all exceptions and records them on the run record. An unhandled exception in a background task would otherwise be silently lost by asyncio with only a log warning.

## Phase 4 M2 — Container Design

- **Multi-stage build.** Stage 1 (builder, approximately 400MB) resolves dependencies into `/app/.venv` via uv. Stage 2 (runtime, approximately 200MB) copies only the `.venv` plus source. uv itself, curl-for-install, and build toolchain stay out of the runtime image.
- **Non-root user (uid 1000).** Required by most production k8s security profiles (PodSecurityStandards "restricted"). Adding it now avoids retrofitting in M3.
- **HEALTHCHECK in Dockerfile.** For `docker run` only; k8s ignores this and uses livenessProbe/readinessProbe configured in the Deployment manifest (M3). Both are intended, and they serve different contexts.
- **AUDIT_DB_PATH default in image.** Set to `/home/agentops/audit.sqlite`, which the non-root user owns. In k8s, this path will be replaced by a PVC mount; M3 will set `AUDIT_DB_PATH` to a PVC-backed location.
- **Single-process container.** The API gateway runs the orchestrator in-process. No separate orchestrator container. Splitting them is a post-portfolio enhancement.
- **Mock image dependency boundary.** The Docker build skips the local editable `rogue-llm` package so the image can be built from this repository alone. MOCK mode uses fixed quality-gate metric stubs; LOCAL/CLOUD container modes would require publishing or vendoring RogueLLM as an installable package.

## Phase 4 M3 — Raw Kubernetes Manifests Design

- **Single-replica Deployment.** The FastAPI gateway keeps run state in an in-memory `RunRegistry`, so multiple replicas would split `/run` submission and `/status/{run_id}` polling across independent processes. Horizontal scaling requires a Redis-backed or DB-backed registry.
- **Recreate rollout strategy.** The audit log uses a ReadWriteOnce PVC. `RollingUpdate` would briefly try to run two Pods mounting the same volume and can leave the replacement Pod pending. `Recreate` terminates the old Pod before the new one mounts the PVC.
- **SecurityContext matches Dockerfile.** The Pod runs as uid/gid 1000 with `runAsNonRoot=true` and `fsGroup=1000`, matching the container user and ensuring the mounted PVC is writable by the non-root process.
- **Minikube exposure and image loading.** Service type is NodePort on 30080 for simple local access without a load balancer or Ingress controller. `imagePullPolicy=Never` tells minikube to use the image built into its local Docker daemon via `eval $(minikube docker-env)`.
- **Resource sizing.** Requests are `256Mi` memory and `250m` CPU; limits are `512Mi` and `500m`. This is enough for the mock-mode API gateway while keeping minikube resource use bounded.

## Phase 4 M4 — Helm Chart Design

- **Meaningful values only.** The chart parameterizes values that naturally change between environments: image repository/tag/pullPolicy, replica count, service type/port/nodePort, resources, budget/runtime config, audit storage size/class/access mode, and optional placeholder secret creation.
- **Deliberately fixed values.** The securityContext is not parameterized because non-root uid/gid 1000 is a security baseline, not a tuning knob. Probe paths (`/healthz`, `/readyz`) are API contracts. The internal audit mount layout and standard label structure are fixed to avoid accidental drift.
- **Chart version versus app version.** `Chart.yaml` uses `version: 0.1.0` for the chart package and `appVersion: "0.5.0"` for the application. The image tag defaults to `appVersion` when `.Values.image.tag` is empty, but dev overrides it to `dev`.
- **Raw manifests remain.** The `k8s/` directory is kept alongside the chart as the educational raw-primitives artifact. The Helm chart is the parameterized deployment artifact, not a reason to delete the M3 manifests.
- **Ephemeral CI support.** `audit.persistence.enabled=false` omits both the PVC and Deployment volume mount, which allows chart rendering and lightweight CI smoke paths without provisioning storage.

## Phase 4 Wrap-Up — Deferred Items

- **Single-replica deployment (M3, M4).** The in-memory `RunRegistry` from M1 does not survive across replicas. Horizontal scaling requires a Redis-backed or DB-backed registry. Documented as a known limitation, not a bug.
- **In-cluster Phoenix sidecar (M3, M4).** Phoenix is an opt-in external endpoint via `PHOENIX_ENDPOINT`; the Helm chart does not bring up Phoenix in-cluster. Adding a Phoenix Deployment and Service would be a Phase 6+ enhancement.
- **Ingress / TLS (M3, M4).** Only NodePort exposure in dev. Real Ingress with cert-manager or Let's Encrypt is a deployment-target-specific concern, out of scope for the portfolio Helm chart.
- **Helm chart museum / registry publishing (M4).** Chart is consumed by `helm install ./charts/agentops` locally. Publishing to a chart repo (OCI or Chart Museum) would be a release-engineering follow-up.
- **k8s/ raw manifests retained (M4).** The raw manifests in `k8s/` are kept alongside the Helm chart in `charts/agentops/`. They are not a parallel deployment path; they are an educational artifact showing each k8s primitive in isolation. The chart is the canonical deployment surface.

## Phase 5 M1 — GitHub Actions CI Design

- **Single sequential job.** The workflow uses one `lint-test` job with lint before tests. Lint failures should be fixed first because they are usually fast and mechanical; running tests after lint keeps the first failure signal focused.
- **Sibling repository checkout.** `agent-ops` is checked out to `./agent-ops` and `rogue-llm` is checked out to `./rogue-llm`. This preserves the `../rogue-llm` relative path declared in `pyproject.toml`. Checking out `agent-ops` at the workspace root would make `../rogue-llm` point above `$GITHUB_WORKSPACE`.
- **Public RogueLLM dependency.** CI clones `nishxnt/rogue-llm` through the public GitHub repository, not a private mirror or token-authenticated substitute, so the workflow reflects how a fresh external checkout resolves the sibling dependency.
- **Frozen uv sync with lockfile cache.** CI runs `uv sync --frozen` so drift between `pyproject.toml` and `uv.lock` fails immediately. The uv cache key includes `uv.lock`, which reuses dependency resolves while the lockfile is unchanged and invalidates the cache when dependencies change.
- **Deployment-tooling tests deferred.** The M1 workflow excludes tests marked `docker`, `k8s`, or `helm` with `-m "not docker and not k8s and not helm"`. Those tests are covered by dedicated M2/M3 workflows because they require heavier runner setup and should not run on every commit.
- **Push and PR triggers.** Pushes to every branch run CI so feature branches get status before a PR opens. Pull requests to `dev` or `main` also run CI against the merge candidate.
- **Concurrency cancellation.** The concurrency group uses the workflow name and Git ref, with `cancel-in-progress: true`, so newer commits cancel stale runs on the same branch instead of spending minutes on obsolete code.

## Phase 5 M2 — Docker Smoke Workflow Design

- **Separate workflow.** `docker-smoke.yml` is intentionally separate from `ci.yml`. Lint + test runs on every push, while Docker build + container smoke is slower and runs only on pull requests to `dev`/`main` plus manual `workflow_dispatch`.
- **Local image validation only.** The workflow uses `docker/build-push-action` with `load: true` so the built image is loaded into the runner's Docker daemon for pytest. It does not push to GHCR or any registry in M2.
- **BuildKit GitHub Actions cache.** `cache-from: type=gha` and `cache-to: type=gha,mode=max` preserve build layers between runs when the Dockerfile and dependency inputs are unchanged. `mode=max` keeps all layers, not just the final image.
- **One smoke assertion path.** CI runs `uv run pytest tests/integration/test_docker_smoke.py -v`, the same assertion logic used by the local Docker smoke path. The `built_image` fixture now reuses `agentops-api:pytest` when the workflow pre-builds it, and only builds from scratch when the tag is absent locally.
- **Mock API image boundary.** The Docker image installs the minimal dependency set needed by the mock API path and excludes heavyweight non-mock evaluation/search packages (`sentence-transformers`, `torch`, RogueLLM metrics, Ragas, Deepeval, Phoenix, FAISS). Mock mode uses deterministic local stubs and copied test fixtures, so the container smoke validates the production API surface without turning PR validation into a multi-GB ML image build.
- **Image size diagnostics.** The final image-size step uses `if: always()` so failed smoke runs still report the produced image size, which helps distinguish runtime failures from unexpectedly bloated builds.

## Phase 5 M2.5 — Reconciliation audit

### Phase 5 M2.5 — A. Env var consistency

- **A.1 Current state.** `docker/api.Dockerfile` sets `AGENTOPS_SEARCH_CACHE_DIR=/home/agentops/.agentops-cache/search` and `AUDIT_DB_PATH=/home/agentops/audit.sqlite` for the standalone mock-mode image. **Decision.** Keep those Dockerfile defaults because `/home/agentops` is owned by uid 1000 in the image. **Action taken.** No Dockerfile ENV change.
- **A.2 Current state.** `src/agentops/config.py` has `search_cache_dir`, but its local-development default is `.agentops-cache/search`, not the container default. Runtime code reads `AGENTOPS_SEARCH_CACHE_DIR` through `Settings`, so the Dockerfile and k8s/Helm env vars override the local default in containerized runs. **Decision.** Keep the local default for non-container developer workflows. **Action taken.** No config change.
- **A.3 Current state.** `k8s/configmap.yaml` did not set either path, while `k8s/api-gateway/deployment.yaml` set `AUDIT_DB_PATH=/var/lib/agentops/audit.sqlite` and mounted the PVC at `/var/lib/agentops`. **Decision.** Make both runtime paths explicit in the raw ConfigMap; keep the deployment audit env aligned with the PVC. **Action taken.** Added `AGENTOPS_SEARCH_CACHE_DIR=/home/agentops/.agentops-cache/search` and `AUDIT_DB_PATH=/var/lib/agentops/audit.sqlite` to the raw ConfigMap.
- **A.4 Current state.** `charts/agentops/templates/configmap.yaml` did not render either path, while the chart deployment hard-coded `AUDIT_DB_PATH=/var/lib/agentops/audit.sqlite`. **Decision.** Pin both paths through values so rendered manifests expose the full runtime contract. **Action taken.** Added `config.searchCacheDir`, `audit.dbPath`, ConfigMap rendering, and deployment consumption of `audit.dbPath`.

### Phase 5 M2.5 — B. Audit DB path and PVC mount

- **B.1 Current state.** Phase 4 raw k8s mounted the audit PVC at `/var/lib/agentops` and set `AUDIT_DB_PATH=/var/lib/agentops/audit.sqlite`. It did not use `/data` or `/home/agentops` in k8s. **Decision.** Keep `/var/lib/agentops` as the k8s/Helm persistent audit location. **Action taken.** No raw mount path change.
- **B.2 Current state.** The Dockerfile standalone default `/home/agentops/audit.sqlite` does not match the k8s/Helm PVC mount path. In cluster, the env override points to `/var/lib/agentops/audit.sqlite`, which does match the mount. **Decision.** Treat `/home/agentops/audit.sqlite` as standalone-container default and `/var/lib/agentops/audit.sqlite` as deployment default. **Action taken.** Made the k8s/Helm deployment default explicit in raw ConfigMap and Helm values.
- **B.3 Current state.** Without the deployment override, a Pod would write outside the PVC. The current raw and Helm deployments already override the audit path, but Helm hid the value in a template literal. **Decision.** Keep the PVC mount path and audit DB path aligned at `/var/lib/agentops`. **Action taken.** Added `audit.dbPath` and `audit.mountPath` values and used them in the Helm deployment.
- **B.4 Current state.** Raw and Helm Pod specs set `runAsUser: 1000`, `runAsGroup: 1000`, and `fsGroup: 1000`; the Dockerfile runtime user is uid/gid 1000. **Decision.** This is the correct storage permission baseline for PVC-backed runs. **Action taken.** No securityContext change.

### Phase 5 M2.5 — C. Lockfile vs direct-pin Dockerfile

- **C.1 Current state.** The Dockerfile uses `uv pip install` with a hand-curated dependency list, so production image versions are not governed by `uv.lock`. **Decision.** Document this as an intentional mock-mode image boundary. **Action taken.** Added Dockerfile and implementation-note rationale.
- **C.2 Current state.** Moving the list into a PEP 735 dependency group would reconnect the image to `uv.lock`, but it would expand this milestone beyond reconciliation. **Decision.** Keep the direct-pin Dockerfile for v1 portfolio scope. **Action taken.** No install-command change.
- **C.3 Current state.** The direct-pin list excludes `sentence-transformers`, `torch`, RogueLLM eval metrics, Ragas, DeepEval, Arize Phoenix, and FAISS. **Decision.** Dockerfile is the source of truth for the production mock API image; the lockfile governs development. Changes to `pyproject.toml` main dependencies must review the Dockerfile list in the same PR. **Action taken.** Documented this guarantee here and in the Dockerfile comment.
- **C.4 Current state.** The Dockerfile had no header explaining why it does not run `uv sync --frozen`. **Decision.** Add a concise comment header only. **Action taken.** Added the 4-6 line note above the `uv pip install` block without changing the install command.

### Phase 5 M2.5 — Image dependency strategy

The Dockerfile is the source of truth for the production image's dependency set. The lockfile governs the dev environment. This is deliberate for v1: the image validates and serves the mock-mode API surface without installing heavyweight non-mock packages.

The hand-curated Dockerfile list excludes `sentence-transformers`, `torch`, RogueLLM evaluation metrics, Ragas, DeepEval, Arize Phoenix, and FAISS by design. When `pyproject.toml` main dependencies change, the Dockerfile install list must be reviewed and updated in the same PR.

### Phase 5 M2.5 — D. Critic embedder lazy import

- **D.1 Current state.** `src/agentops/agents/critic.py` imports `sentence_transformers` inside `_default_embedder()` only after checking `get_settings().mode != AgentOpsMode.MOCK`; it is not imported at module top level. **Decision.** Keep the implementation. **Action taken.** No critic source change.
- **D.2 Current state.** Existing critic tests did not assert that mock-mode import avoids `sentence_transformers` or exercise the lazy branch. **Decision.** Add focused unit coverage. **Action taken.** Added tests that reload the critic module in mock mode without importing `sentence_transformers` and exercise `_default_embedder()` in non-mock mode with a fake `sentence_transformers` module.
- **D.3 Current state.** The lazy-embedder pattern was not documented. **Decision.** Document why mock-mode containers need lazy ML imports. **Action taken.** Added the subsection below.

### Phase 5 M2.5 — Lazy ML imports for mock-mode container

Mock mode is a first-class deployment mode, so modules imported by the API startup path must not require heavyweight local/cloud-only ML packages. `CriticAgent` keeps its default embedder behind `_default_embedder()`: mock mode returns a deterministic in-repo embedder, while non-mock mode lazily imports `sentence_transformers` only when that path is selected.

### Phase 5 M2.5 — E. Test fixtures in production image

- **E.1 Current state.** `MockLLMClient` resolves LLM fixtures from `Path(__file__).resolve().parents[3] / "tests" / "fixtures"`, and mock search resolves search fixtures the same way. In the container, `PYTHONPATH=/app/src`, so this resolves to `/app/tests/fixtures`. **Decision.** Keep copying fixtures into `/app/tests/fixtures`. **Action taken.** No Dockerfile COPY change.
- **E.2 Current state.** `.dockerignore` does not exclude `tests/fixtures`; it excludes cache files, SQLite files, and deployment/source artifact directories. **Decision.** Fixtures remain part of the build context. **Action taken.** No `.dockerignore` change.
- **E.3 Current state.** The Dockerfile copies only `tests/fixtures/`, not test modules. **Decision.** Mock-mode fixtures are part of the production image surface because mock mode is a first-class deployment mode for this project (used in PR validation, k8s smoke testing, and portfolio demos). Tests under `tests/unit/` and `tests/integration/` are NOT copied; only the fixture data. **Action taken.** Documented this policy.

### Phase 5 M2.5 — F. README and deployment docs

- **F.1 Current state.** README status said only "Phase 4 complete." **Decision.** Clarify that Phase 5 is in progress and k8s smoke CI is next. **Action taken.** Updated the status sentence.
- **F.2 Current state.** Quick Start still uses `make run-mock`. **Decision.** Keep it and validate it after the lazy-import change. **Action taken.** Validation gate runs `AGENTOPS_MODE=mock uv run agentops-run "What is FAISS?"`.
- **F.3 Current state.** README Docker docs did not state the mock-only image scope. **Decision.** Make the image boundary explicit. **Action taken.** Added Docker section text explaining the minimal mock-mode dependency set.

### Phase 5 M2.5 — G. Helm chart values

- **G.1 Current state.** `values.yaml` did not expose audit DB path or search cache dir, while deployment/configmap templates used hard-coded or hidden defaults. **Decision.** Pin path strings in values to avoid hidden defaults before M3. **Action taken.** Added `audit.dbPath=/var/lib/agentops/audit.sqlite`, `audit.mountPath=/var/lib/agentops`, and `config.searchCacheDir=/home/agentops/.agentops-cache/search`.
- **G.2 Current state.** The Helm deployment mounted the audit PVC at `/var/lib/agentops` and set the audit DB path under that mount. **Decision.** Preserve that relationship while rendering it from values. **Action taken.** Updated the Helm deployment template and will validate with `helm template ... -f values.dev.yaml`.

### Phase 5 M2.5 — H. Makefile targets

- **H.1 Current state.** `make k8s-up` builds `agentops-api:dev`; `k8s/api-gateway/deployment.yaml` references `agentops-api:dev` with `imagePullPolicy: Never`. **Decision.** The raw manifest image tag matches the Makefile target. **Action taken.** No Makefile or raw image change.
- **H.2 Current state.** `make helm-install` builds `agentops-api:dev`; `charts/agentops/values.dev.yaml` sets `image.tag: "dev"` with repository `agentops-api`. **Decision.** The Helm dev image tag matches the Makefile target. **Action taken.** No Makefile or dev values image change.
