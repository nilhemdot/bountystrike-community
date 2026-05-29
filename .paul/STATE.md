# Project State

## Project Reference

See: .paul/PROJECT.md (updated 2026-05-29)

**Core value:** Automated bug bounty hunting that produces only verified, non-duplicate findings
**Current focus:** Phase 1 — Community Edition MVP: The Moat

## Current Position

Milestone: v0.1 Community Edition MVP
Phase: 1 of 6 (Community Edition MVP: The Moat) — In Progress (2 of ~7 plans complete)
Plan: 01-02 (Hatchet v1 Workflow Runtime) — LOOP COMPLETE (PLAN ✓ APPLY ✓ UNIFY ✓)
Status: 01-02 closed. hatchet-lite v0.86.18 (own isolated Postgres) live; v1 @hatchet.task bs-heartbeat registers + run SUCCEEDED end-to-end. SUMMARY reconciled (8 ACs pass, 7 deviations). Ready for 01-03 (evidence store / R2).
Last activity: 2026-05-29 — UNIFY 01-02 (loop closed)

Progress:
- Milestone: [███░░░░░░░] ~25% (1 of 6 phases complete + Phase 1 progressing)
- Phase 0: [██████████] 100% (4/4 plans complete)
- Phase 1: [███░░░░░░░] ~29% (2 of ~7 plans complete — 01-01 DB, 01-02 Hatchet)

## Loop Position

Phase 0 loop (00-04) — COMPLETE:
```
PLAN ──▶ APPLY ──▶ UNIFY
  ✓        ✓        ✓     [Loop complete — Phase 0 transition executed]
```

Phase 1 loop (01-01) — COMPLETE:
```
PLAN ──▶ APPLY ──▶ UNIFY
  ✓        ✓        ✓     [Loop closed — DB foundation shipped + verified]
```
Phase 1 loop (01-02) — COMPLETE:
```
PLAN ──▶ APPLY ──▶ UNIFY
  ✓        ✓        ✓     [Loop closed — Hatchet v1 runtime shipped + verified]
```
Note: 01-02 line SPLIT — 01-02 = Hatchet v1 only; 01-03 = evidence store (R2). Downstream +1 (now 7 plans 01-01..01-07).

## Accumulated Context

### Decisions

| Decision | Phase | Impact |
|----------|-------|--------|
| AGPLv3 Community + proprietary Enterprise + Apache 2.0 shared primitives | Init | Governs all licensing and repo layout |
| Deterministic verifier is the moat — no submission without evidence artifact | Init | Shapes Phase 1 scope and oracle TPR=1.0/FPR=0.0 requirement |
| SOC 2 clock must start at Phase 3 launch (Week 19), not enterprise launch | Init | Hard constraint on Phase 3 exit criteria |
| Position as AEV inside Gartner CTEM, not "bug bounty tool" | Init | Shapes Phase 4 marketing, pricing, and competitive framing |
| 2026-05-27: Enterprise audit on 00-01. Applied 3 must-have + 2 strongly-recommended. Verdict: conditionally acceptable → ready | Phase 0 | Plan now enforces full doc coverage, inline provenance, cost-overrun stop |
| 2026-05-27: 00-01 edit scope = v5 plan + research/ + support docs (NOT v6 docs, which hold the corrections as source-of-truth). v5 build plan edited in place despite being superseded, for fact-check consistency | Phase 0 | Stale claims corrected wherever they appear as live assertions; v6 docs left as correction record |
| 2026-05-27: Git committer identity set repo-local (3x3by3@gmail.com / nilhem) to enable baseline commit | Phase 0 | One-time; no global config touched |
| 2026-05-27: Monorepo approach = HYBRID (keep uv workspace, layer pnpm/Turborepo on top; no physical code move). Repo was already a uv workspace, not greenfield | Phase 0 | 00-02 scaffolds license roots + task layer; physical reorg deferred |
| 2026-05-27: Phase 0 split 2→3 plans (00-03 = OpenFeature + custom Unleash provider, separated due to no official Python provider per brief) | Phase 0 | Feature flags own plan |
| 2026-05-27: Audit on 00-02 added license-text integrity (verbatim canonical), LICENSES.md code↔license map, AGPL §13 network-use clause | Phase 0 | License posture audit-defensible before code ships |
| 2026-05-27: Audit on 00-03 — tier-enterprise flag is a config/rollout gate, NOT an authz boundary. Entitlement enforced server-side vs signed plan. Provider: TLS + secrets token + fail-closed on malformed response; context untrusted | Phase 0 | Prevents flag-as-authz privilege-escalation; sets the doctrine for all later tier gating |
| 2026-05-29: Audit on 00-04 — 5 must-have + 6 strongly-rec applied; 4 deferred. Verdict: conditionally acceptable. Caught 2 release-blocking license defects (foreign/.venv AGPL-stamping; AGPL-vs-Apache root collision) + unsound import-ban canary test. Doctrine: SPDX sweep uses six-root ALLOW-LIST (not git-walk+deny), shebang/PEP-263-cookie ordering, byte-equality idempotency proof, canary inside contract source_modules w/ trap-cleanup | Phase 0 | License sweep audit-defensible; import-ban enforcement sound. Residual risk: APPLY must encode allow-list, not regress to git-walk |
| 2026-05-29: Phase 1 split — 01-01 line (5 subsystems) split into 01-01 DB foundation (PG17 custom image pgvector+vectorscale+pg_search) + 01-02 Hatchet v1 + evidence store; downstream plans renumbered +1 (now 6 plans). Matches PAUL 2-3 task sizing | Phase 1 | Single-concern plans; DB foundation isolated from workflow/evidence wiring |
| 2026-05-29: Enterprise audit on 01-01 (DB foundation). Applied 4 must-have + 4 strongly-rec; deferred 3. Verdict: conditionally acceptable (was not-acceptable as written). Caught 2 release-blocking SQL defects — BM25 migration indexed non-existent findings.title/description cols, and used the DEPRECATED `paradedb.create_bm25()` API (current = `CREATE INDEX … USING bm25 … WITH (key_field='id')`, verified Context7). Also: zero version pins despite "reproducible" claim (pinned pgvector 0.8.0 / vectorscale 0.9.0 / pg_search v0.23.x + fixed base tag); Alpine/musl build unverified (added glibc bookworm fallback, AC-1 = empirical gate); incomplete cargo-pgrx invocation (match version + `pgrx init`); CONCURRENTLY in initpath → plain CREATE INDEX (INVALID-index masking); added AC-7 pins, AC-8 idempotency-on-re-apply, AC-3 functional .so smoke. Doctrine: migrations must target verified-existing columns; pg_search uses CREATE INDEX USING bm25 (not legacy CALL); pin all extensions+base; first-boot init = no CONCURRENTLY; verify extensions functionally not by catalog row | Phase 1 | DB foundation audit-defensible + reproducible; plan can now satisfy its own ACs at apply time |
| 2026-05-29: APPLY 01-02 (Hatchet v1). hatchet-lite v0.86.18 + dedicated hatchet-postgres in compose; all 8 ACs verified LIVE (engine healthy, worker registered bs-heartbeat, triggered run returned result/SUCCEEDED). 7 deviations: (1) topology = hatchet-lite Postgres-only (plan said engine+RabbitMQ) — lite uses PG as both store+queue, AC-8 isolation kept, 1 fewer container; (2) replaced a PRE-EXISTING broken `hatchet` service (engine pointed at app DB, no broker, + YAML bug: networks nested under healthcheck); (3) gRPC 7070→7077 (lite default); (4) `uv sync --all-packages` REQUIRED — plain root sync exits 0 but skips workspace-member deps; (5) sdk pin 1.33.6 (PyPI latest; trap #2 floor >=1.33.5; no `__version__` attr — use importlib.metadata); (6) client token session-ephemeral via `hatchet-admin token create --config /config` (path is /config not /hatchet/config) for seeded Default tenant 707d0855-…, NOT committed; (7) healthcheck `/api/ready`. HARNESS NOTE: severe tool-output corruption this session (fabricated/merged results + parallel-cancel cascades); first APPLY pass fabricated success w/ nothing on disk — caught, redone strict-sequential, every claim re-verified against disk/sandbox. | Phase 1 | Durable-execution backbone live. Doctrine: hatchet-lite for solo self-host (PG-only, isolated DB); workspace deps need `uv sync --all-packages`; self-host worker needs HATCHET_CLIENT_TOKEN + TLS_STRATEGY=none; under harness corruption switch to strict-sequential + re-verify on disk. Open: in-container worker token wiring (later plan) |
| 2026-05-29: APPLY/UNIFY 01-01. Custom bs-postgres:pg17 built + ALL ACs verified live (PG17.10, 3 extensions active, DiskANN+BM25 apply+idempotent). 3 deviations: (1) glibc postgres:17-bookworm base not Alpine — pgrx+ParadeDB are glibc-only (plan-permitted fallback); (2) added `-c shared_preload_libraries=pg_search` to compose command — pg_search BM25 AM requires preload at server start (Context7-verified), absent from Task 2 spec; (3) `ruff check .` not clean — 40 PRE-EXISTING errors all in non-01-01 .py (control-plane/mcp/scripts/tests); 01-01 touched zero .py so introduced none; AC-6 "ruff exits 0" unsatisfiable w/o violating no-domain boundary. pgrx auto-matched to 0.16.1 via cargo metadata. | Phase 1 | DB foundation shipped. Doctrine: pg_search MUST be in shared_preload_libraries; custom PG ext images use glibc base + cargo-pgrx version-match. Open: pre-existing ruff debt needs separate triage (out of 01-01 scope) |

### Deferred Issues

| Issue | Origin | Effort | Revisit |
|-------|--------|--------|---------|
| ~~HackerOne structured_scopes changelog verification~~ **RESOLVED 2026-05-27** via primary source (api.hackerone.com changelog, in docs/bountystrike_v6_phase0-1_technical_brief.md). Only program-level WRITE removed (Apr 7 2026); READ endpoint CURRENT; NEW scope_exclusions endpoint (Apr 11 2026). Phase 1 W1.2 UNBLOCKED: implement structured_scopes READ + scope_exclusions READ + merge; skip program-level WRITE. research/02-routing-ev.md:66-76 migration spec has WRONG date ("April 16" vs actual April 7) + needs scope_exclusions added — fix in a future Phase 1 plan. | Init (v6 plan) | DONE | Closed — see brief |
| DeepSeek pricing correction + cost model rebuild | Init (v6 plan) | S | Phase 0, Day 1 |
| EV decay constants derivation (lambda=0.00065 / mu=0.00963) — regression-fit or hand-tuned? | Init (v6 plan) | M | Phase 0 |

### Blockers/Concerns

| Blocker | Origin | Status |
|---------|--------|--------|
| ~~No container runtime in WSL distro~~ **RESOLVED 2026-05-29** — Docker enabled (`docker info` UP). Custom image built exit 0; all empirical ACs verified live. | APPLY 01-01 (2026-05-29) | CLOSED |

## Session Continuity

Last session: 2026-05-29
Stopped at: 01-02 LOOP CLOSED (UNIFY ✓). Hatchet v1 runtime shipped + verified. SUMMARY at .paul/phases/01-community-edition-mvp/01-02-SUMMARY.md.
Next action: /paul:plan 01-03 — evidence store (R2-write step runs inside a Hatchet task).
Resume file: .paul/phases/01-community-edition-mvp/01-02-SUMMARY.md
Resume context:
- Phase 1: 2 of ~7 plans done. NOT phase-complete (01-03..01-07 remain).
- 01-02 shipped Hatchet v1: workflows/ pkg (client.py shared Hatchet(), tasks.py bs-heartbeat @hatchet.task, worker.py). compose: hatchet-lite v0.86.18 + dedicated hatchet-postgres (isolated from bs-postgres). orchestrator.py trigger-heartbeat seam. hatchet-sdk==1.33.6.
- LIVE STATE: bs-hatchet + bs-hatchet-postgres containers UP + healthy (engine left running). Background worker STOPPED. Client token NOT committed (session-ephemeral, regen via runbook in SUMMARY).
- OPEN: in-container worker token wiring (later plan); pre-existing ruff debt (40 errors non-01-02 .py) still untriaged.
- Nothing committed yet — git working tree holds 01-01 + 01-02 changes uncommitted.
- HARNESS: tool-output corruption hit this session; recovered via strict-sequential + disk/sandbox re-verification. If it recurs next session, default to one-tool-at-a-time.

---
*STATE.md — Updated after every significant action*
