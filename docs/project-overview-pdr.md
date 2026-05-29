# Project Overview (PDR) — BountyStrike v5

A Product Definition Reference for BountyStrike v5. Consolidates the vision, success criteria, scope, and constraints that govern every build decision. Use this as the single-page anchor before reading anything else under `docs/`.

**Status (2026-05-01):** Phase 1 signed off (4/6 PASS, 2 GAP-deploy). Phase 2 §10.4 dedup recall fixture (recall=1.0) shipped same day. Phase 2 W7-8 sprint closed: scanner + exploit phases wired into orchestrator, T2/T3 approval queue + CLI shipped, T3 plumbing wired (commit `7001be1`), and 5 new field-validation suites passed at TPR=1.0 / FPR=0.0 — SSRF→IMDS (`e9b4b77`), IDOR (`65fe921`), RCE (`5493eea`), SSTI (`6ef4858`), Open Redirect (`1b6eb64`). Phase 2 W9-10 (dedup-prod, kill-switch <5s SLA, SQLi field-validation suite) is the next gate. See [`phase1_signoff.md`](signoffs/phase1_signoff.md).

## Mission

> Operate a swarm of Claude-driven agents that find, verify, and submit real bug bounty reports — autonomously, within scope, under cost ceilings — and continuously beat human-only solo hunters on confirmed-rate × payout while staying below 5% false-positive submissions.

## Five Non-Negotiables

These are hard constraints. Any code, agent, or workflow that violates them is wrong by definition. Drawn verbatim from [`research/01-strategy-architecture.md`](research/01-strategy-architecture.md) §Vision.

1. **Scope enforcement at the network layer.** A scope-JWT (RS256, 4096-bit) is issued by the control plane and validated by every MCP and sandbox before any outbound packet. Targets that fail the in-scope check are dropped at the iptables egress allowlist inside the Firecracker VM, not just at application logic. The JWT carries `wildcards`, `exact_hosts`, `ips`, `exclusions.hostnames`, `exclusions.paths`, `rate_limits.default_rps`, and per-host overrides. See [`scope-mcp`](../mcp/scope-mcp/) and [`control-plane/src/control_plane/domains/scope_management/services/jwt_issuer.py`](../control-plane/src/control_plane/domains/scope_management/services/jwt_issuer.py).

2. **Verification independent of exploitation.** The validator never shares context, model, or sandbox with the exploiter. Each finding goes through a deterministic oracle in [`mcp/oracle-mcp`](../mcp/oracle-mcp/) — XSS via Playwright DOM mutation observer, SSRF via OAST callback, SQLi via Welch's t-test on response timing, etc. — running in a fresh microVM. This is the moat against AnyPoC reward-hacking. Phase 1 closed XSS and SSRF at TPR=1.0, FPR=0.0.

3. **Hash-chained, content-addressable evidence.** Every finding has request/response transcripts, oracle data, and reproduction commands stored under SHA-256 content hashes with a `prev_audit_hash` chain. Daily root hashes can optionally be anchored to Sigstore Rekor. See [`evidence_artifacts`](../infra/sql/01_schema.sql) table and [`mcp/evidence-mcp`](../mcp/evidence-mcp/).

4. **T1 / T2 / T3 human-tier approval gates.** No report leaves the system without crossing the right tier. T0 = auto-confirm low-impact dupes; T1 = LLM-review (Sonnet); T2 = single human approver for medium-impact; T3 = two-person sign-off for high-impact / novel classes. Implemented in [`control-plane/src/control_plane/domains/approval_gate/services.py`](../control-plane/src/control_plane/domains/approval_gate/services.py); enforced by the [`pretool_approval_gate.py`](../.claude/hooks/pretool_approval_gate.py) hook.

5. **Per-program EV ranking, not "scan the world".** A single ranked queue: `EV = f(payout, saturation, ops_load, fit, cve_signal)`. The agent works the top of the list and stops when the per-task or per-scan budget is hit. See [`mcp/ev-mcp`](../mcp/ev-mcp/) + [`control-plane/src/control_plane/domains/program_ranking/services/scoring_service.py`](../control-plane/src/control_plane/domains/program_ranking/services/scoring_service.py). The `kev_match_program` tool in [`mcp/kev-mcp`](../mcp/kev-mcp/) feeds CISA-KEV signals into the `cve_signal` weight.

## Target Outcomes

| Metric | Target | Current state | Source |
|---|---|---|---|
| Confirmed-rate (submitted → confirmed) | ≥70% | TBD (Phase 4 measurement) | [`research/03-verifier-antislop.md`](research/03-verifier-antislop.md) §SLOs |
| False-positive submission rate | <5% | TBD | same |
| Time-to-validate (hypothesis → validated) | <30 min | TBD | same |
| Time-to-submit (validated → submitted) | <4 h | TBD | same |
| Cost per confirmed bug | <$5 USD | TBD | [`research/02-routing-ev.md`](research/02-routing-ev.md) §Cost Guardrails |
| Scope-violation incidents | 0 | 0 enforced (network layer) | non-negotiable #1 |
| Oracle accuracy (TPR/FPR) | ≥90% | XSS=1.0/0.0, SSRF=1.0/0.0, SSRF→IMDS=1.0/0.0, IDOR=1.0/0.0, RCE=1.0/0.0, SSTI=1.0/0.0, Open Redirect=1.0/0.0 (7 of 8 oracles validated; SQLi field-validation suite pending Phase 2 W9-10) | [`phase1_signoff.md`](signoffs/phase1_signoff.md) Rounds 4 + 6 |
| Dedup recall | >95% | 100% (Phase 2 §10.4 fixture, commit 3d9e915) | [`phase1_signoff.md`](signoffs/phase1_signoff.md) |
| Service uptime | >99.5% | TBD (Phase 4) | — |
| Operator NPS | >50 | TBD (Phase 4 alpha) | — |

## What's In Scope

- **Active scanning** of subdomains, endpoints, parameters, and form fields for the 8 oracle bug classes within JWT-validated scope.
- **Submission** to HackerOne, Bugcrowd, Intigriti, YesWeHack, Immunefi via dedicated MCP submitters. Intigriti currently read-only via the researcher API; submission is a placeholder pending a relay endpoint (per [`research/00c-context7-verifications.md`](research/00c-context7-verifications.md)).
- **Cost discipline** via the model-routing matrix (16 task types × 4 cost tiers) in [`research/02-routing-ev.md`](research/02-routing-ev.md). Bulk triage on DeepSeek ($0.14/M input, cache-hit $0.0028/M) (per api-docs.deepseek.com; see docs/bountystrike_v6_phase0-1_technical_brief.md — corrects the v6 figure); deep reasoning on Opus ($5/M); Tier-S models for security-specific tasks (Pentest-R1, WhiteRabbitNeo).
- **Solo and SaaS deployment** modes. Solo: single docker-compose stack, BYOK, <$30/mo. SaaS: per-tenant Firecracker isolation, signed scope JWTs, Temporal Cloud, LiteLLM proxy.

## What's Out of Scope

- **DoS, brute force, mass exploitation**, anything destructive — explicitly denied by [`pretool_antislop.py`](../.claude/hooks/pretool_antislop.py) and the destructive-payload denylist in [`control-plane/src/control_plane/core/security/validation.py`](../control-plane/src/control_plane/core/security/validation.py).
- **Out-of-band attacks beyond OAST callbacks** (e.g., DNS poisoning, BGP manipulation).
- **Targeting non-bounty assets** — the JWT enforces this; agents physically cannot reach them.
- **Detection-evasion techniques** for malicious purposes. The platform exists to operate inside authorized programs, full stop.

## Design Pillars

### 1. Determinism over LLM trust at the verifier
The verifier is not "another LLM that says yes". It's a Playwright assertion, a Welch t-test, a regex on a callback hostname. The LLM hypothesis-generates; the oracle decides. AnyPoC reward-hacking modes (self-exploit via loopback, mock validation, hallucinated paths, timing artifacts) each have a specific countermeasure documented in [`research/03-verifier-antislop.md`](research/03-verifier-antislop.md) §AnyPoC matrix.

### 2. Scope is a network primitive, not a prompt
The agent CLAUDE.md says "stay in scope" — but the iptables rules inside the VM are what actually enforce it. Prompt injection that talks the agent into pivoting cannot beat the netfilter table. The scope-MCP validates the JWT and emits the firewall rules; the [`scope-guard`](../.claude/agents/scope-guard.md) sub-agent provides a synchronous policy adjudicator for ambiguous cases.

### 3. Single Postgres, no premature scale-out
Per [`research/01-strategy-architecture.md`](research/01-strategy-architecture.md) §Storage: one Postgres 17 with pgvector + pg_trgm + (later) pgvectorscale handles everything up to ~500k findings. No Redis as a primary store, no Elasticsearch, no Kafka. Redis is just the kill-switch flag and approval-gate cache. The audit log is hash-chained inside Postgres; daily root anchored to Rekor only when SaaS multi-tenant lands.

### 4. Hooks are the control plane
Claude Code's PreToolUse / PostToolUse / SubagentStart lifecycle is where security policy lives. Four hooks ship today (kill switch, antislop, openrouter routing, approval gate). The 26-event hook stack documented in [`research/04-skills-mcps.md`](research/04-skills-mcps.md) is the path to richer enforcement (cost ceilings, per-task budgets, scope re-validation on every tool call).

### 5. Evidence is the product
The agent's job is not "find the bug". It's to produce a hash-chained, reproducible artifact that a human triager can replay against the live system. Every finding ships with: request transcript, response transcript, oracle data, reproduction command, scope JWT JTI, sandbox VM ID. See [`evidence_artifacts`](../infra/sql/01_schema.sql).

## Risk Register Highlights

Full register in [`research/06-roadmap.md`](research/06-roadmap.md) §Risks (17 entries). Top:

| ID | Severity | Risk | Mitigation owner |
|---|---|---|---|
| R01 | CRITICAL | AI-slop reports erode platform trust | Validator sub-agent + 7-criteria report quality gate ([`research/03`](research/03-verifier-antislop.md)) |
| R02 | CRITICAL | Prompt injection breaks scope | Network-layer egress allowlist (non-negotiable #1) + scope-guard adjudicator |
| R03 | HIGH | CFAA / authorized-testing liability | JWT-bound scope is the legal artifact; never ingest a program without verified authorization |
| R08 | MED | EU CRA 24h disclosure deadline (effective 2026-09-11) | Phase 3 compliance hooks: 24h ack / 72h preliminary / 14d update timers |

## Phase Roadmap (current state)

| Phase | Window | State |
|---|---|---|
| 0 | Weeks 1-2 | DONE — repo scaffold, scope-MCP TypeScript, EV MVP, schema |
| 1 | Weeks 3-6 | DONE (2026-05-01 signoff): 4/6 PASS, 2 GAP-deploy (recon container image, R2 credentials) |
| 2 | Weeks 7-10 | IN PROGRESS — W7-8 closed: dedup recall=1.0 (`3d9e915`), scanner+exploit wired into orchestrator, T2/T3 approval queue shipped, T3 plumbing wired (`7001be1`), 5 field-validation suites at TPR=1.0/FPR=0.0 (SSRF→IMDS, IDOR, RCE, SSTI, Open Redirect). W9-10 open: dedup-prod, kill-switch <5s SLA, SQLi field-validation, schema-vs-spec contract test |
| 3 | Weeks 11-15 | NOT STARTED — solo-mode polish, alpha hunter onboarding |
| 4 | Weeks 16-20 | NOT STARTED — SaaS multi-tenant, Temporal Cloud, compliance hooks |

Latest git: `e9b4b77` (today) — SSRF→IMDS field-validation suite at TPR=1.0/FPR=0.0. Earlier today: `b7ec4e3` added `kev_match_program` for CISA-KEV ↔ tech-stack cross-reference (feeds Phase 2 EV-signal calibration); then 5 oracle field-validation suites + T3 orchestrator plumbing landed in rapid succession.

## Decision Boundaries

When a tradeoff appears, default to:

- **Determinism > coverage.** A verifier that misses a class is fine; a verifier that confirms a non-bug is not.
- **Network enforcement > prompt enforcement.** Always.
- **One Postgres > many specialized stores.** Until measured otherwise.
- **Open-source / MCP-adopted > in-house.** Don't rebuild what Burp/Caido/HexStrike/Garak already do well.
- **BYOK + per-task ceiling > flat-rate spending.** Cost discipline is a feature.
- **Hand-curated docs > regenerated boilerplate.** This file is hand-edited; let it stay that way.

## See Also

- [`codebase-summary.md`](codebase-summary.md) — file map, dependencies, MCP inventory
- [`system-architecture.md`](system-architecture.md) — Mermaid diagrams of component graph, data flow, ER, trust boundaries
- [`code-standards.md`](code-standards.md) — DDD layout, ruff rules, MCP template, hook authoring
- [`architecture/bountystrike_v5_build_plan.md`](architecture/bountystrike_v5_build_plan.md) — the full 20-week spec (4,525 LOC)
- [`research/06-roadmap.md`](research/06-roadmap.md) — phase exit criteria + risk register + glossary
