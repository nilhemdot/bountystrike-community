---
phase: 00-truth-in-claims-foundation
plan: 00-01
completed: 2026-05-27
duration: ~1 session (incl. audit + FIX cycle)
---

# Phase 0 Plan 01: Empirical Corrections + Competitive Set — Summary

Corrected 6 empirical soft spots + competitive set across the doc tree, with inline provenance and a rebuilt cost model. Required one FIX cycle (00-01-FIX) when a primary-source brief revealed the DeepSeek pricing we'd applied was itself wrong.

## What Was Built

| File | Purpose |
|------|---------|
| docs/architecture/bountystrike_v5_build_plan.md | Pricing, refusal, Welch, EV-constant corrections (live-assertion doc, edited despite superseded) |
| docs/research/02-routing-ev.md | Routing-table pricing, cost model rebuild, refusal/EV annotations |
| docs/research/01-strategy-architecture.md | Pricing correction |
| docs/research/06-roadmap.md | Pricing + refusal glossary corrections |
| docs/project-overview-pdr.md | Pricing correction |
| docs/beyond bountystrike.md | XBOW N/A label, Surf AI removal, Bugcrowd re-rank, pricing table |
| docs/claude-code-bug-bounty-build-plan.md | Pricing correction (coverage-gap catch) |
| docs/bountystrike_v6_phase0-1_technical_brief.md | NEW — primary-source authority saved to docs |
| .paul/.../00-01-AUDIT.md | Enterprise audit report (3 must-have + 2 rec applied) |
| .paul/.../00-01-FIX.md + FIX-SUMMARY.md | Pricing re-correction cycle |

## Acceptance Criteria Results

| AC | Description | Status |
|----|-------------|--------|
| AC-1 | DeepSeek pricing corrected everywhere | PASS (via FIX — final figure $0.14/$0.0028/$0.28) |
| AC-2 | Anthropic refusal reframed (no hard %) | PASS |
| AC-3 | XBOW N/A labeled "industry estimate" | PASS |
| AC-4 | HackerOne structured_scopes verified | PASS (resolved via brief primary source) |
| AC-5 | Welch's t-test reframed as heuristic | PASS |
| AC-6 | EV constants annotated pending-calibration | PASS |
| AC-7 | Surf AI removed, Bugcrowd re-ranked | PASS |
| AC-8 | Inline provenance on corrections | PASS (citations now point at brief) |
| AC-9 | Full doc coverage, no partial | PASS |
| AC-10 | Cost-overrun stop | PASS (per-scan $0.0051 << $0.20, no breach) |

## Verification Results

- grep stale `$0.14/$0.28`, `71%`, `70%+` → only v6-correction-record docs retain (intended)
- grep wrong `$0.42` / `$0.028` → zero in the 7 target docs (FIX verified)
- grep correct `$0.0028` → present in all 7 docs
- "Surf AI" → only removal rationale + v6 record

## Deviations

1. **FIX cycle required.** 00-01 applied the v6 plan's DeepSeek figure ($0.28/$0.42), which a later primary-source brief proved wrong. 00-01-FIX re-corrected to $0.14/$0.0028/$0.28. The audit's provenance discipline made this catchable and recoverable. Net lesson: v6 "corrections" are not all primary-sourced — the brief is.
2. **HackerOne Task 1 deferred then resolved out-of-band.** The human-action changelog check was deferred during APPLY, then resolved when the brief supplied the primary source. Gate closed.
3. **Edited a superseded doc** (v5 build plan) by explicit operator decision, for fact-check consistency.

## Key Decisions

- Edit scope = v5 plan + research/ + support docs; v6 docs left as correction record. (Now superseded: brief is the real authority — v6's pricing correction was wrong.)
- Strip all hard refusal numbers (keep Venice 2.2%); pricing numbers only (no model-name changes).

## Skill Audit

No SPECIAL-FLOWS required-skills triggered (00-01 was empirical/docs work; AI-red-team + e2e skills map to ai-vuln-hunter/pipeline work in later phases).

## Next Phase

00-02: Monorepo scaffold (pnpm + Turborepo 2.x, three-root license split) + OpenFeature/Unleash feature-flag SDK + license headers + CONTRIBUTING/CLA. This is the first code-writing plan — build traps in CLAUDE.md Constraints now apply.

---
*Completed: 2026-05-27*
