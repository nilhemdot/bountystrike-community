# Project State

## Project Reference

See: .paul/PROJECT.md (updated 2026-05-29)

**Core value:** Automated bug bounty hunting that produces only verified, non-duplicate findings
**Current focus:** Phase 1 — Community Edition MVP: The Moat

## Current Position

Milestone: v0.1 Community Edition MVP
Phase: 1 of 6 (Community Edition MVP: The Moat) — Not started
Plan: 01-01 (not yet started)
Status: Phase 0 COMPLETE (4/4 plans unified). Ready to plan Phase 1.
Last activity: 2026-05-29 — UNIFY 00-04, Phase 0→1 transition

Progress:
- Milestone: [███░░░░░░░] ~22% (1 of 6 phases complete)
- Phase 0: [██████████] 100% (4/4 plans complete)
- Phase 1: [░░░░░░░░░░] 0% (not started)

## Loop Position

Phase 0 loop (00-04) — COMPLETE:
```
PLAN ──▶ APPLY ──▶ UNIFY
  ✓        ✓        ✓     [Loop complete — Phase 0 transition executed]
```

Phase 1 loop — IDLE:
```
PLAN ──▶ APPLY ──▶ UNIFY
  ◉                       [Ready to plan 01-01]
```

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

### Deferred Issues

| Issue | Origin | Effort | Revisit |
|-------|--------|--------|---------|
| ~~HackerOne structured_scopes changelog verification~~ **RESOLVED 2026-05-27** via primary source (api.hackerone.com changelog, in docs/bountystrike_v6_phase0-1_technical_brief.md). Only program-level WRITE removed (Apr 7 2026); READ endpoint CURRENT; NEW scope_exclusions endpoint (Apr 11 2026). Phase 1 W1.2 UNBLOCKED: implement structured_scopes READ + scope_exclusions READ + merge; skip program-level WRITE. research/02-routing-ev.md:66-76 migration spec has WRONG date ("April 16" vs actual April 7) + needs scope_exclusions added — fix in a future Phase 1 plan. | Init (v6 plan) | DONE | Closed — see brief |
| DeepSeek pricing correction + cost model rebuild | Init (v6 plan) | S | Phase 0, Day 1 |
| EV decay constants derivation (lambda=0.00065 / mu=0.00963) — regression-fit or hand-tuned? | Init (v6 plan) | M | Phase 0 |

### Blockers/Concerns

None yet.

## Session Continuity

Last session: 2026-05-29
Stopped at: Phase 0→1 transition complete (UNIFY 00-04 + phase commit)
Next action: /paul:plan 01-01 (Phase 1, first plan — Community Edition MVP: The Moat)
Resume file: .paul/phases/00-truth-in-claims-foundation/00-04-SUMMARY.md

---
*STATE.md — Updated after every significant action*
