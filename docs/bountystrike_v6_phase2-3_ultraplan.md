# BountyStrike v6 — Phase 2 & Phase 3 Ultraplan

**Version:** 6.0.0
**Date:** May 21, 2026
**Effort mode:** /effort ultraplan — atomized, dependency-ordered, machine-executable
**Scope:** Phase 2 (full agent fleet, anti-slop, benchmark publication) + Phase 3 (Solo SaaS / Cloud)
**Continues from:** Phase 0–1 Implementation Brief (task IDs 000–999)
**Conventions:** identical to Phase 0–1 — `tasks/<id>/task.yaml` with `id`, `depends_on`, `files_created`, `acceptance`, `idempotent`, `estimated_minutes`; TodoWrite spine; Stop-hook completion gate; idempotent acceptance-first scripts.

---

## How this continues the one-shot

Phase 0–1 left the repo at a specific, verifiable state: a working Community Edition that ingests scope, issues RS256 scope JWTs, runs a recon subagent through an MCP, verifies five vulnerability classes deterministically, and stores hash-chained evidence in R2. The acceptance suite at `tasks/999-acceptance-suite/` passes end-to-end for a single operator against a single program.

Phase 2 takes that spine and does three things: it fills in the remaining four subagents so the kill chain is complete (exploit, validator, dedup, reporter — plus the supervisory orchestrator and the AI-vuln-hunter and cloud-recon specialists), it hardens the anti-slop discipline into measurable SLOs rather than a doctrine, and it publishes honest benchmark numbers that become the platform's marketing anchor. Phase 3 then wraps that single-operator engine in a multi-tenant boundary and ships it as a hosted product — and, critically, starts the SOC 2 Type II observation clock the day the cloud goes live, because that clock has a hard three-month minimum and gates every enterprise sale in Phase 4.

The task numbering continues the Phase 0–1 scheme. Phase 2 uses the 100–199 band; Phase 3 uses the 200–299 band. Each task remains a PR-sized unit with an executable acceptance test. The same Stop-hook gate applies: the lead agent cannot declare completion until every task's acceptance command exits zero.

The single most important sequencing rule in this plan: **`200-soc2-observation-start` has no code dependencies and must be triggered the moment the Phase 3 multi-tenant core is deployable.** It is placed early in the 200 band on purpose. If it slips to the end of Phase 3, the enterprise tier in Phase 4 is blocked for the full observation window with nothing to show for the wait.

---

# PHASE 2 — Full Agent Fleet, Anti-Slop & Benchmark Publication (Weeks 11–18)

## Objective
Complete the nine-agent fleet, convert anti-slop doctrine into instrumented SLOs, and publish reproducible benchmark numbers (both XBOW variants, with cost) that anchor every downstream marketing and sales claim.

## Dependency map (Phase 2 internal)
```
100-orchestrator ──┬─> 110-exploit-agent ──> 111-refusal-classifier ──> 112-payload-fallback
                   ├─> 120-validator-agent (consumes Phase 1 verifier oracles)
                   ├─> 130-dedup-agent ──> 131-pgvector-embedder ──> 132-fingerprint-index
                   ├─> 140-ai-vuln-hunter ──> 141-garak-mcp ─┬─> 142-promptfoo-mcp
                   │                                          └─> 143-pyrit-mcp
                   ├─> 150-cloud-recon ──> 151-cloud-mcp (cloud_enum/S3Scanner/Prowler/ScoutSuite)
                   └─> 160-reporter-agent ──> 161-platform-formatters ──> 162-approval-tiers
160 ──> 170-antislop-slo ──> 171-confirmed-rate-meter ──> 172-killswitch ──> 173-anypoc-guards
170 ──> 180-benchmark-harness ──> 181-xbow-blackbox ──> 182-xbow-whitebox ──> 183-cost-attribution ──> 184-benchmark-publish
```

---

## Workstream 2.1 — Orchestrator & remaining subagents (Weeks 11–14)

### task 100-orchestrator
**Title:** Supervisory orchestrator subagent + scope-guard defer escalation
**depends_on:** [041-recon-subagent, 035-no-verify-no-submit-trigger, 024-scope-jwt-issuer]
**files_created:**
- `.claude/agents/orchestrator.md`
- `.claude/agents/scope-guard.md`
- `.claude/hooks/scope-defer.py`
- `packages/community/orchestrator/kill_chain.py`
- `tests/unit/test_kill_chain_state.py`

The orchestrator is the lead subagent that drives the seven-phase kill chain (scope → recon → surface → probe → verify → triage → report) and delegates each phase to the specialist subagent. It owns the TodoWrite spine for a single scan run, persists run state to Postgres so a `--resume` restores mid-scan, and enforces phase-gating (phase N+1 cannot start until phase N's evidence is persisted).

The scope-guard is the deferred-decision subagent invoked by the `scope-defer.py` PreToolUse hook (the Phase 0–1 `defer` primitive). The mechanical 95% of scope decisions resolve in the hook's Python without an LLM; only genuinely ambiguous cases (wildcard matches a host that program text excludes by description) trigger `permissionDecision: "defer"`, which pauses the headless session, spawns scope-guard with the relevant program rules, and resumes via `--resume`.

**acceptance:**
- `pytest tests/unit/test_kill_chain_state.py` (state machine rejects out-of-order phase transitions)
- `python -m bountystrike.orchestrator.selftest --dry-run` exits 0 and prints the seven phases in order
- A crafted ambiguous-scope event returns `permissionDecision: "defer"` from `scope-defer.py` (asserted by `tests/integration/test_scope_defer.py`)
**idempotent:** true
**estimated_minutes:** 90

### task 110-exploit-agent
**Title:** Exploit subagent with Firecracker-sandboxed PoC execution
**depends_on:** [100-orchestrator]
**files_created:**
- `.claude/agents/exploit-agent.md`
- `packages/community/exploit/runner.py`
- `infra/firecracker/jailer.config.json`
- `infra/firecracker/rootfs.dockerfile`
- `tests/integration/test_exploit_sandbox_escape.py`

The exploit subagent generates and executes proof-of-concept payloads, but every PoC runs inside a Firecracker microVM with an egress allowlist derived from the active scope JWT, enforced at the `tap0` network layer — never in the agent prompt. The agent model is Sonnet 4.6 for solo. The runner copies the PoC into the microVM, executes with a hard wall-clock and memory cap, captures output to the R2 evidence store, and tears the VM down.

**acceptance:**
- `pytest tests/integration/test_exploit_sandbox_escape.py` — a deliberately malicious PoC that tries to reach a non-scope host is blocked at tap0 (test asserts zero egress packets to the disallowed IP)
- `python -m bountystrike.exploit.runner --selftest` runs a benign PoC end-to-end and writes evidence to R2
**idempotent:** true
**estimated_minutes:** 120

### task 111-refusal-classifier
**Title:** Runtime refusal classifier (replaces the deleted "70% refusal rate" claim with a mechanism)
**depends_on:** [110-exploit-agent]
**files_created:**
- `packages/community/exploit/refusal_classifier.py`
- `tests/unit/test_refusal_classifier.py`

Per Correction #2: there is no hard refusal-rate number. Instead, a lightweight classifier inspects each LLM response for refusal signatures (apology + capability-denial patterns, empty tool-call with hedging prose). On a positive classification for a payload-generation request, the call is re-routed (task 112). The classifier is itself a cheap model call (Haiku) plus a regex prefilter, logged to the cost meter.

**acceptance:**
- `pytest tests/unit/test_refusal_classifier.py` — labeled fixture set of 40 refusals + 40 compliances classified at ≥95% precision/recall
**idempotent:** true
**estimated_minutes:** 45

### task 112-payload-fallback
**Title:** LiteLLM fallback chain to open-weight payload models
**depends_on:** [111-refusal-classifier, 012-litellm-proxy]
**files_created:**
- `infra/litellm/fallback.config.yaml`
- `packages/community/exploit/model_router.py`
- `tests/integration/test_payload_fallback.py`

On a positive refusal classification, the model router re-issues the request through LiteLLM's `default_fallbacks` to an open-weight model (Venice Dolphin / Hermes-4-70B) via OpenRouter or a self-hosted vLLM endpoint. The routing decision and the fallback model are recorded in the audit log so every payload's provenance is traceable.

**acceptance:**
- `pytest tests/integration/test_payload_fallback.py` — a stubbed refusal triggers exactly one fallback call and records provenance
**idempotent:** true
**estimated_minutes:** 60

### task 120-validator-agent
**Title:** Validator subagent consuming the five Phase 1 oracles
**depends_on:** [100-orchestrator, 030-verifier-xss, 031-verifier-ssrf-interactsh, 032-verifier-sqli-welch, 033-verifier-open-redirect, 034-verifier-ssti]
**files_created:**
- `.claude/agents/validator-agent.md`
- `packages/community/validator/dispatch.py`
- `tests/unit/test_validator_dispatch.py`

The validator is deliberately thin: it receives a candidate finding, picks the correct deterministic oracle for the vulnerability class, runs it, and promotes the finding only on a pass. It contains no LLM judgment about whether something is exploitable — that truth comes from the oracle's physics. Findings that fail are tagged `unverified` and filtered by default.

**acceptance:**
- `pytest tests/unit/test_validator_dispatch.py` — each of the five classes routes to the correct oracle; an unknown class raises and does not promote
- `python -m bountystrike.validator.selftest` confirms a known-vulnerable fixture promotes and a known-clean fixture does not
**idempotent:** true
**estimated_minutes:** 75

### task 130-dedup-agent + 131-pgvector-embedder + 132-fingerprint-index
**Title:** Three-layer deduplication (exact fingerprint + pgvector semantic + program cross-check)
**depends_on:** [100-orchestrator, 010-postgres-stack]
**files_created:**
- `.claude/agents/dedup-agent.md`
- `packages/community/dedup/fingerprint.py`
- `packages/community/dedup/embedder.py`
- `packages/community/dedup/cross_check.py`
- `infra/postgres/dedup.sql`
- `tests/unit/test_dedup_layers.py`

Layer one is a structural fingerprint (normalized vuln-class + endpoint + parameter + payload-shape hash). Layer two is pgvector cosine similarity over an embedding of the finding's natural-language description, using the DiskANN index from Phase 1. Layer three is a program-level cross-check against previously submitted findings to catch known dupes before submission. The dedup agent runs cheaply (DeepSeek V4-Flash for the embedding-adjacent reasoning).

**acceptance:**
- `pytest tests/unit/test_dedup_layers.py` — recall ≥95% on a labeled duplicate set, precision ≥90%
- `psql -f infra/postgres/dedup.sql` applies the DiskANN index without error
**idempotent:** true
**estimated_minutes:** 100

### task 140-ai-vuln-hunter + 141/142/143 (garak/promptfoo/pyrit MCPs)
**Title:** OWASP LLM Top 10 specialist + three AI-security MCP servers
**depends_on:** [100-orchestrator, 040-recon-mcp]
**files_created:**
- `.claude/agents/ai-vuln-hunter.md`
- `.claude/skills/ai-prompt-injection/SKILL.md`
- `packages/community/mcp/garak_mcp.py`
- `packages/community/mcp/promptfoo_mcp.py`
- `packages/community/mcp/pyrit_mcp.py`
- `tests/integration/test_ai_vuln_hunter.py`

Activated when recon flags an AI/LLM endpoint. Wraps Garak (probe-based LLM vuln scanning), Promptfoo (eval-based red-teaming), and PyRIT (adversarial orchestration) as MCP servers. The prompt-injection skill bundles indirect-injection chains and RAG-poisoning recipes. Model is Sonnet 4.6 (Haiku is too literal for adversarial creative work).

**acceptance:**
- `pytest tests/integration/test_ai_vuln_hunter.py` — against a deliberately vulnerable local LLM endpoint, detects at least one injection and writes evidence
- Each MCP server starts under `stdio` and lists its tools without writing to stdout (JSON-RPC integrity check)
**idempotent:** true
**estimated_minutes:** 130

### task 150-cloud-recon + 151-cloud-mcp
**Title:** Cloud surface specialist (cloud_enum, S3Scanner, Prowler, ScoutSuite)
**depends_on:** [100-orchestrator, 040-recon-mcp]
**files_created:**
- `.claude/agents/cloud-recon.md`
- `packages/community/mcp/cloud_mcp.py`
- `tests/integration/test_cloud_recon.py`

Treats S3/Azure Blob/GCS buckets, Lambda/Functions, and IAM exposure as first-class asset types. The cloud MCP normalizes each tool's output into the same asset-provenance schema from Phase 1. Read-only posture by default; no destructive cloud operations regardless of scope.

**acceptance:**
- `pytest tests/integration/test_cloud_recon.py` — against a localstack fixture, enumerates a public bucket and records provenance
**idempotent:** true
**estimated_minutes:** 100

### task 160-reporter-agent + 161-platform-formatters + 162-approval-tiers
**Title:** Reporter subagent with per-platform formatters and T0–T3 approval tiers
**depends_on:** [120-validator-agent, 130-dedup-agent]
**files_created:**
- `.claude/agents/reporter-agent.md`
- `packages/community/reporter/formatters/{hackerone,bugcrowd,intigriti,yeswehack,immunefi}.py`
- `packages/community/reporter/approval.py`
- `tests/unit/test_formatters.py`

The reporter takes verified, deduplicated findings and produces platform-formatted submissions. Model is Sonnet 4.6 minimum (report prose quality is part of payout probability). It has no network tools that touch the target — by the report phase, testing is done. The approval tiers gate submission: T0 fully manual, T1 human-approves-each, T2 human-approves-batch, T3 auto-submit (only for the highest-confidence verified classes, off by default in CE).

**acceptance:**
- `pytest tests/unit/test_formatters.py` — each formatter produces valid platform-specific markdown with required fields; a finding lacking an evidence artifact raises before formatting
- `python -m bountystrike.reporter.selftest` produces a HackerOne-formatted draft from a verified fixture
**idempotent:** true
**estimated_minutes:** 110

---

## Workstream 2.2 — Anti-slop gates (Weeks 14–16)

### task 170-antislop-slo
**Title:** Anti-slop SLO framework
**depends_on:** [160-reporter-agent]
**files_created:**
- `packages/community/antislop/slo.py`
- `infra/postgres/slo_metrics.sql`
- `tests/unit/test_slo.py`

Converts the anti-slop doctrine into a measurable SLO: every finding must reference at least one verifiable artifact before it can transition to `submitted`; the confirmed-rate (confirmed ÷ submitted) is tracked per program and globally with a target >70%. The SLO framework is the thing that prevents the curl-style AI-slop failure mode from getting the platform banned.

**acceptance:**
- `pytest tests/unit/test_slo.py` — a finding without an evidence artifact cannot reach `submitted`; confirmed-rate computed correctly on a fixture
**idempotent:** true
**estimated_minutes:** 60

### task 171-confirmed-rate-meter
**Title:** Confirmed-rate instrumentation + dashboard metric
**depends_on:** [170-antislop-slo]
**files_created:**
- `packages/community/antislop/confirmed_rate.py`
- `tests/unit/test_confirmed_rate.py`

**acceptance:**
- `pytest tests/unit/test_confirmed_rate.py` — rolling 30-day confirmed-rate computed; alert fires below 70%
**idempotent:** true
**estimated_minutes:** 40

### task 172-killswitch
**Title:** Three-layer kill switch
**depends_on:** [170-antislop-slo]
**files_created:**
- `packages/community/antislop/killswitch.py`
- `.claude/hooks/killswitch-pretool.py`
- `tests/integration/test_killswitch.py`

Three independent layers: a per-scan token-budget ceiling enforced in the orchestrator (not the prompt); a confirmed-rate floor that pauses submission if the rolling rate drops below threshold; and an operator panic button that halts all running scans and revokes active scope JWTs. The PreToolUse hook layer is the hard enforcement point.

**acceptance:**
- `pytest tests/integration/test_killswitch.py` — each of the three layers independently halts a running scan
**idempotent:** true
**estimated_minutes:** 70

### task 173-anypoc-guards
**Title:** Reward-hacking countermeasures (AnyPoC failure modes)
**depends_on:** [110-exploit-agent, 120-validator-agent]
**files_created:**
- `packages/community/antislop/reward_hacking.py`
- `tests/unit/test_reward_hacking.py`

Guards against the documented agent reward-hacking failure modes: self-exploitation (the agent attacks its own infrastructure to fake a finding), mock validation (the agent fabricates an oracle pass), hallucinated attack paths, and timing coincidence (a slow server mistaken for a SQLi sleep). Each guard is a deterministic check applied before a finding is promoted.

**acceptance:**
- `pytest tests/unit/test_reward_hacking.py` — each of the four failure-mode fixtures is caught and the finding is rejected
**idempotent:** true
**estimated_minutes:** 80

---

## Workstream 2.3 — Benchmark publication (Weeks 16–18)

### task 180-benchmark-harness
**Title:** XBOW benchmark harness (both variants)
**depends_on:** [173-anypoc-guards, 162-approval-tiers]
**files_created:**
- `packages/community/benchmark/harness.py`
- `packages/community/benchmark/xbow_loader.py`
- `tests/integration/test_benchmark_harness.py`

The harness runs the full kill chain against the XBOW challenge set and records pass/fail plus per-challenge cost. It supports both the black-box variant (no source, XBOW's own ~85% reference) and the white-box/source-aware variant (Shannon's 100/104 reference, explicitly labeled as the easier mode). Honesty about which variant produced which number is the whole point — per the v6 pressure-test, conflating them is the credibility trap.

**acceptance:**
- `pytest tests/integration/test_benchmark_harness.py` — harness runs against a 3-challenge smoke subset in both modes and records results
**idempotent:** true
**estimated_minutes:** 90

### task 181-xbow-blackbox / 182-xbow-whitebox
**Title:** Full black-box and white-box benchmark runs
**depends_on:** [180-benchmark-harness]
**files_created:**
- `benchmark-results/blackbox/{date}.json`
- `benchmark-results/whitebox/{date}.json`
**acceptance:**
- Black-box run completes the full set; result JSON validates against `benchmark-results/schema.json`
- White-box run completes; result JSON validates and is tagged `variant: whitebox`
**idempotent:** true (re-running overwrites the dated file)
**estimated_minutes:** 240 (mostly compute wall-time)

### task 183-cost-attribution
**Title:** Per-challenge cost attribution
**depends_on:** [181-xbow-blackbox, 182-xbow-whitebox, 015-cost-meter]
**files_created:**
- `packages/community/benchmark/cost_report.py`
- `benchmark-results/cost-summary.md`

Joins the benchmark results against the LiteLLM cost meter to produce per-challenge and aggregate cost. The defensible public claim this enables: comparable accuracy to best-in-class open-source autonomous pentesters (Deadend CLI ~80% at ~$1.17/challenge) at a fraction of the cost, with deterministic verification on top.

**acceptance:**
- `python -m bountystrike.benchmark.cost_report` produces `cost-summary.md` with per-challenge and aggregate cost; total reconciles within 5% of the LiteLLM ledger
**idempotent:** true
**estimated_minutes:** 50

### task 184-benchmark-publish
**Title:** Reproducible public benchmark report
**depends_on:** [183-cost-attribution]
**files_created:**
- `docs/benchmarks/README.md`
- `docs/benchmarks/reproduce.sh`
**acceptance:**
- `bash docs/benchmarks/reproduce.sh --smoke` reproduces the 3-challenge subset from a clean checkout (third-party reproducibility gate)
**idempotent:** true
**estimated_minutes:** 60

## Phase 2 exit criteria
- [ ] All nine subagents operational and integration-tested (orchestrator, scope-guard, recon, exploit, validator, dedup, ai-vuln-hunter, cloud-recon, reporter)
- [ ] Confirmed-rate SLO >70% on the internal test corpus
- [ ] Dedup recall ≥95% on the labeled duplicate set
- [ ] Published benchmark report covering both variants with cost, reproducible by a third party from a clean checkout
- [ ] 5+ validated findings submitted to real programs by alpha hunters
- [ ] All four AnyPoC reward-hacking guards catch their fixtures

---

# PHASE 3 — Solo SaaS / Cloud (Weeks 19–26)

## Objective
Wrap the single-operator engine in a multi-tenant boundary and ship it as a hosted product at $29/user/month, with a killer-UX dashboard — and start the SOC 2 Type II observation clock the day the cloud is deployable.

## The non-negotiable early-start item
### task 200-soc2-observation-start
**Title:** Engage SOC 2 auditor and begin Type II observation window
**depends_on:** [210-multitenant-core] (deployable state only — NOT feature-complete)
**files_created:**
- `compliance/soc2/scope.md`
- `compliance/soc2/control-matrix.csv`
- `compliance/soc2/vendor-engagement.md`

This is a process task, not a code task, and it is placed first in the 200 band deliberately. SOC 2 Type II has a hard three-month minimum observation window and a realistic 9–12 month first-time program. Engage Vanta or Drata in Week 19 the moment the multi-tenant core is deployable. If this slips to Phase 4, the enterprise tier is blocked for the full window with nothing accruing.

**acceptance:**
- `compliance/soc2/vendor-engagement.md` records a signed auditor engagement date
- `compliance/soc2/control-matrix.csv` maps each Trust Services Criterion to a control owner and exists in the repo
**idempotent:** true (the engagement date, once set, is immutable)
**estimated_minutes:** 30 (in-repo); external process runs for months in the background

## Dependency map (Phase 3 internal)
```
210-multitenant-core ──┬─> 200-soc2-observation-start (process; starts ASAP)
                        ├─> 211-temporal-migration
                        ├─> 212-postgres-rls
                        ├─> 213-turbopuffer-namespaces
                        ├─> 214-microvm-pool
                        └─> 215-workos-authkit
210 ──> 220-dashboard ──┬─> 221-agent-stream-sse
                        ├─> 222-evidence-inspector
                        ├─> 223-command-palette
                        ├─> 224-cost-meter-ui
                        └─> 225-ctem-stage-viz
220 ──> 230-billing ──> 231-stripe-metering ──> 232-byok ──> 233-onboarding-upgrade-flow
```

---

## Workstream 3.1 — Multi-tenant core (Weeks 19–22)

### task 210-multitenant-core
**Title:** Multi-tenant control plane skeleton
**depends_on:** [Phase 2 complete]
**files_created:**
- `packages/enterprise/control-plane/app.py`
- `packages/enterprise/control-plane/tenancy.py`
- `tests/integration/test_tenant_isolation.py`

Introduces the tenant as a first-class entity. Every scan, finding, scope JWT, and evidence artifact is bound to a `tenant_id`. The control plane is the public API surface that the dashboard calls. This task only needs to reach a deployable state to unblock `200-soc2-observation-start`; full feature completeness comes through the rest of the 210 band.

**acceptance:**
- `pytest tests/integration/test_tenant_isolation.py` — a request authenticated as tenant A cannot read tenant B's scans (asserted at the API layer)
**idempotent:** true
**estimated_minutes:** 120

### task 211-temporal-migration
**Title:** Replace Hatchet with Temporal Cloud for durable multi-tenant workflows
**depends_on:** [210-multitenant-core]
**files_created:**
- `packages/enterprise/workflows/scan_workflow.py`
- `packages/enterprise/workflows/worker.py`
- `infra/temporal/config.yaml`
- `tests/integration/test_workflow_durability.py`

Solo mode keeps Hatchet (single Postgres binary). SaaS promotes to Temporal Cloud for per-tenant task queues, idempotent replay, and multi-week scan durability. The scan workflow is rewritten as a Temporal workflow; activities wrap the same subagent invocations. Per-tenant concurrency limits live on the task queue.

**acceptance:**
- `pytest tests/integration/test_workflow_durability.py` — a workflow survives a worker restart mid-scan and resumes from the last completed activity
**idempotent:** true
**estimated_minutes:** 140

### task 212-postgres-rls
**Title:** Row-Level Security across all tenant-scoped tables
**depends_on:** [210-multitenant-core]
**files_created:**
- `infra/postgres/rls.sql`
- `tests/integration/test_rls.py`

Every tenant-scoped table gets an RLS policy keyed on a session-local `app.tenant_id`. The control plane sets the GUC per request. This is defense-in-depth behind the API-layer check — even a query bug cannot cross the tenant boundary.

**acceptance:**
- `pytest tests/integration/test_rls.py` — with `app.tenant_id` set to A, a raw `SELECT *` returns zero of tenant B's rows
**idempotent:** true
**estimated_minutes:** 90

### task 213-turbopuffer-namespaces
**Title:** Per-tenant Turbopuffer vector namespaces (engaged past ~1M findings/tenant)
**depends_on:** [212-postgres-rls, 131-pgvector-embedder]
**files_created:**
- `packages/enterprise/vectors/turbopuffer_client.py`
- `packages/enterprise/vectors/router.py`
- `tests/integration/test_vector_routing.py`

Small tenants stay on the shared pgvector/DiskANN index (cheaper, simpler). Tenants past ~1M findings get promoted to a dedicated Turbopuffer namespace. The router abstracts which backend a tenant uses so the dedup agent is unaware.

**acceptance:**
- `pytest tests/integration/test_vector_routing.py` — a small tenant routes to pgvector, a large-tenant fixture routes to a Turbopuffer namespace; dedup results are equivalent
**idempotent:** true
**estimated_minutes:** 100

### task 214-microvm-pool
**Title:** E2B / Firecracker microVM pool for per-job isolation
**depends_on:** [210-multitenant-core, 110-exploit-agent]
**files_created:**
- `packages/enterprise/sandbox/pool.py`
- `packages/enterprise/sandbox/egress_allowlist.py`
- `tests/integration/test_microvm_egress.py`

In SaaS, each scan job runs in its own microVM rather than a shared Docker container. The egress allowlist is derived from the tenant's active scope JWT and enforced at the VM network layer. Pool management handles warm-VM reuse with full teardown between tenants (no state bleed).

**acceptance:**
- `pytest tests/integration/test_microvm_egress.py` — a job in tenant A's VM cannot reach a host outside A's scope JWT; VM is fully reset before reassignment
**idempotent:** true
**estimated_minutes:** 130

### task 215-workos-authkit
**Title:** WorkOS AuthKit (foundation for SSO/SCIM in Phase 4)
**depends_on:** [210-multitenant-core]
**files_created:**
- `packages/enterprise/auth/workos.py`
- `tests/integration/test_auth.py`

AuthKit handles the user base now and provides the SAML/OIDC/SCIM hooks that Phase 4 enterprise sales require. Solo Cloud users authenticate via AuthKit's hosted flow; per-tenant SSO connections are added per enterprise deal in Phase 4.

**acceptance:**
- `pytest tests/integration/test_auth.py` — a login flow issues a tenant-scoped session; an unauthenticated request to a tenant resource is rejected
**idempotent:** true
**estimated_minutes:** 90

---

## Workstream 3.2 — Killer UX baseline (Weeks 22–25)

### task 220-dashboard
**Title:** Next.js 16 + shadcn/ui dashboard shell
**depends_on:** [215-workos-authkit]
**files_created:**
- `apps/dashboard/` (Next.js 16 app router)
- `apps/dashboard/app/layout.tsx`
- `tests/e2e/dashboard.spec.ts`

The shell: authenticated layout, tenant switcher, run list, navigation. Everything else in the 220 band hangs off this.

**acceptance:**
- `pnpm --filter dashboard build` succeeds
- `pnpm --filter dashboard test:e2e -- --grep "loads authenticated shell"` passes
**idempotent:** true
**estimated_minutes:** 110

### task 221-agent-stream-sse
**Title:** Live agent-reasoning stream (the Cursor/Vercel pattern)
**depends_on:** [220-dashboard, 211-temporal-migration]
**files_created:**
- `apps/dashboard/app/runs/[id]/stream.tsx`
- `packages/enterprise/control-plane/sse.py`
- `tests/e2e/agent_stream.spec.ts`

The run-detail page subscribes via Server-Sent Events to the orchestrator's message stream and renders the agent's reasoning chain, tool calls, and phase transitions in real time. This is where operators spend most of their time — watching scans unfold and intervening on deferred scope decisions.

**acceptance:**
- `pnpm --filter dashboard test:e2e -- --grep "renders live agent stream"` — a simulated run emits events that appear in the UI within 1s
**idempotent:** true
**estimated_minutes:** 120

### task 222-evidence-inspector
**Title:** Evidence inspector with replayable exploit confirmation (the Stripe drill-down pattern)
**depends_on:** [220-dashboard, 013-r2-evidence]
**files_created:**
- `apps/dashboard/app/findings/[id]/evidence.tsx`
- `packages/enterprise/control-plane/evidence_presign.py`
- `tests/e2e/evidence_inspector.spec.ts`

Each finding drills down to its evidence chain: the HTTP transcript, the OAST callback log, the Playwright DOM snapshot or screenshot, the SHA-256 hash, and the hash-chain audit link. Evidence is served via short-TTL presigned R2 URLs generated on demand — never public links. This transparent evidence trail is the UX expression of the anti-slop moat.

**acceptance:**
- `pnpm --filter dashboard test:e2e -- --grep "renders evidence with valid presigned url"` — the inspector loads an artifact via a presigned URL that expires
**idempotent:** true
**estimated_minutes:** 110

### task 223-command-palette
**Title:** Command palette (the Linear pattern)
**depends_on:** [220-dashboard]
**files_created:**
- `apps/dashboard/components/command-palette.tsx`
- `tests/e2e/command_palette.spec.ts`
**acceptance:**
- `pnpm --filter dashboard test:e2e -- --grep "cmd-k opens palette and navigates"` passes
**idempotent:** true
**estimated_minutes:** 70

### task 224-cost-meter-ui
**Title:** Cost meter + budget alarms ("scan paused, top up" UX)
**depends_on:** [220-dashboard, 015-cost-meter, 172-killswitch]
**files_created:**
- `apps/dashboard/components/cost-meter.tsx`
- `tests/e2e/cost_meter.spec.ts`

Surfaces per-scan and per-tenant spend in real time against the budget ceiling. When the killswitch budget layer trips, the UI shows the "scan paused, top up" state rather than a silent failure.

**acceptance:**
- `pnpm --filter dashboard test:e2e -- --grep "shows paused state on budget breach"` passes
**idempotent:** true
**estimated_minutes:** 60

### task 225-ctem-stage-viz
**Title:** CTEM five-stage progress visualization (the differentiator)
**depends_on:** [221-agent-stream-sse]
**files_created:**
- `apps/dashboard/components/ctem-progress.tsx`
- `tests/e2e/ctem_viz.spec.ts`

Maps the active scan onto Gartner's CTEM five stages (Scoping → Discovery → Prioritization → Validation → Mobilization) as a progress visualization. Per the v6 research, no competitor ships this well yet — it is the table-stakes-but-unfilled UX opening and the bridge to the Phase 4 enterprise AEV positioning.

**acceptance:**
- `pnpm --filter dashboard test:e2e -- --grep "maps run phases to CTEM stages"` — a running scan lights up the correct CTEM stage as it progresses
**idempotent:** true
**estimated_minutes:** 80

---

## Workstream 3.3 — Billing & onboarding (Weeks 25–26)

### task 230-billing + 231-stripe-metering
**Title:** Stripe usage-based metering
**depends_on:** [210-multitenant-core, 015-cost-meter]
**files_created:**
- `packages/enterprise/billing/stripe_meter.py`
- `tests/integration/test_billing_accuracy.py`

Per-scan and platform-fee billing through Stripe usage records. Metering must reconcile within 5% of actual LLM cost from the LiteLLM ledger.

**acceptance:**
- `pytest tests/integration/test_billing_accuracy.py` — simulated usage produces Stripe meter events reconciling within 5% of the ledger
**idempotent:** true
**estimated_minutes:** 90

### task 232-byok
**Title:** BYOK option (OpenRouter 1M free BYOK requests/month as the default cheap path)
**depends_on:** [231-stripe-metering, 012-litellm-proxy]
**files_created:**
- `packages/enterprise/billing/byok.py`
- `tests/integration/test_byok.py`

Cost-sensitive tenants supply their own provider keys; the LiteLLM proxy enforces per-tenant budget ceilings independently of the platform key. Note the v6 caveat: BYOK leaks tenant identity into the provider's logs and breaks per-tenant cost prediction, so it is offered as a downgrade, not the default.

**acceptance:**
- `pytest tests/integration/test_byok.py` — a BYOK tenant's calls route through their key with an enforced ceiling
**idempotent:** true
**estimated_minutes:** 70

### task 233-onboarding-upgrade-flow
**Title:** Self-serve onboarding + Community→Cloud upgrade
**depends_on:** [232-byok, 220-dashboard]
**files_created:**
- `apps/dashboard/app/onboarding/`
- `packages/enterprise/billing/upgrade.py`
- `tests/e2e/onboarding.spec.ts`

The funnel: a Community Edition self-hoster can import their config and upgrade to Cloud in a few clicks. This is the conversion path that monetizes the open-source trust earned in Phases 1–2.

**acceptance:**
- `pnpm --filter dashboard test:e2e -- --grep "completes self-serve onboarding"` passes
- `pytest tests/integration/test_upgrade.py` — a CE config imports cleanly into a new Cloud tenant
**idempotent:** true
**estimated_minutes:** 90

## Phase 3 exit criteria
- [ ] Multi-tenant isolation verified by a penetration test (zero cross-tenant access at both API and RLS layers)
- [ ] Temporal workflow survives a server restart mid-scan (durability test green)
- [ ] microVM pool handles 10 concurrent scans with full teardown between tenants
- [ ] Billing metering accurate within 5% of the LLM ledger
- [ ] **SOC 2 Type II observation window started in Week 19 and tracking**
- [ ] 20+ beta hunters at >65% confirmed-rate on the hosted product
- [ ] CTEM five-stage visualization live in the dashboard

---

## Cross-cutting (carries from Phase 0–1, continues here)
- **Engineering hygiene:** property-based tests (Hypothesis / fast-check) and mutation tests (mutmut / Stryker) extended to every new package; adversarial fuzzing of the multi-tenant API with malformed tenant IDs and prompt-injected target HTML.
- **CI/CD:** Sigstore signing on every artifact, SLSA L3 provenance, in-toto attestations, cosign image attestation, Syft SBOM — now also covering the dashboard build and the enterprise control plane.
- **Benchmark cadence:** every release ships updated XBOW (both variants) + cost numbers; the dashboard surfaces the latest published numbers as a trust signal.

## Phase 2–3 top risks
| # | Risk | Phase | Mitigation |
|---|---|---|---|
| R1 | SOC 2 clock started late, blocks Phase 4 enterprise for ~1 year | 3 | `200-soc2-observation-start` placed first in the 200 band; engage auditor Week 19 |
| R2 | Confirmed-rate falls below 70%, risks program bans | 2 | `171-confirmed-rate-meter` alert + `172-killswitch` confirmed-rate-floor layer |
| R3 | Benchmark numbers conflate black-box/white-box (credibility hit) | 2 | `180-benchmark-harness` tags every result with its variant; `184` reproducibility gate |
| R4 | Multi-tenant isolation bug leaks cross-tenant data | 3 | Defense-in-depth: API check (`210`) + RLS (`212`) + per-job microVM (`214`); pentest gate |
| R5 | Temporal Cloud cost/complexity exceeds Hatchet's simplicity at low tenant count | 3 | Keep Hatchet for solo; only SaaS promotes to Temporal; revisit if tenant count < 10 at GA |
| R6 | Reward-hacking agent fakes a finding that passes an oracle | 2 | `173-anypoc-guards` four-failure-mode deterministic checks before promotion |
| R7 | DeepSeek model rename / pricing drift breaks cost meter | 2–3 | daily pricing cron (from Phase 0–1 caveat); model-alias detection in LiteLLM |

## The one-paragraph version
Phase 2 completes the nine-agent fleet on top of the Phase 1 verifier moat — orchestrator and scope-guard to drive the kill chain, exploit (Firecracker-sandboxed, with a refusal classifier and open-weight fallback replacing the deleted refusal-rate claim), validator (thin, oracle-driven), three-layer dedup, the OWASP-LLM ai-vuln-hunter, cloud-recon, and a report-quality reporter with T0–T3 approval tiers — then hardens anti-slop into measurable SLOs (>70% confirmed-rate, three-layer killswitch, four AnyPoC reward-hacking guards) and publishes honest, reproducible XBOW benchmarks in both variants with per-challenge cost as the marketing anchor. Phase 3 wraps that engine in a multi-tenant boundary (Temporal Cloud, Postgres RLS, per-tenant Turbopuffer, per-job microVMs, WorkOS AuthKit), ships a killer-UX dashboard (live agent stream, evidence inspector, command palette, cost meter, and the CTEM five-stage visualization no competitor ships well), and launches Solo Cloud at $29/mo with Stripe metering and a Community→Cloud upgrade funnel — while starting the SOC 2 Type II clock in Week 19, because that three-month-minimum observation window is the hard gate on every enterprise sale in Phase 4.

---

*End of BountyStrike v6 Phase 2 & Phase 3 Ultraplan.*
*Task IDs 100–184 (Phase 2) and 200–233 (Phase 3) continue the Phase 0–1 graph (000–999). All conventions, idempotency rules, and the Stop-hook completion gate carry forward unchanged.*
