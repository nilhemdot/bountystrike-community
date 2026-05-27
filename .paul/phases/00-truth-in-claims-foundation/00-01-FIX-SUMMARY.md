# 00-01-FIX — Summary

**Completed:** 2026-05-27
**Type:** fix (corrects defect in plan 00-01)
**Status:** All 4 ACs PASS

## What the defect was

Plan 00-01 trusted the v6 plan's "Correction #1" and set DeepSeek pricing to **$0.28 input / $0.42 output (cache-hit $0.028)** across 7 docs, with provenance citations claiming "DeepSeek official API pricing, verified v6 2026-05-27". The Phase 0/1 technical brief (primary source: api-docs.deepseek.com/quick_start/pricing) proved that figure wrong — the v6 "correction" was itself an error, AND it propagated through 00-01 into 7 docs.

## What was fixed

Correct primary-source figure now in all 7 docs: **$0.14 cache-miss input / $0.0028 cache-hit input / $0.28 output per 1M tokens**.

| File | Change |
|------|--------|
| docs/architecture/bountystrike_v5_build_plan.md | 9 sites: pricing + cost-model arithmetic (500K × $0.14 = $0.07; per-100 total back to ~$0.51) + citations |
| docs/research/02-routing-ev.md | 4 sites: routing-table cell, pricing note, cost model (cache-miss $0.51 / cache-hit ~$0.44) + citation |
| docs/research/01-strategy-architecture.md | 1 site (line 77) |
| docs/research/06-roadmap.md | 2 sites (glossary + citation table) |
| docs/project-overview-pdr.md | 1 site (line 44) |
| docs/beyond bountystrike.md | 3 sites: V4-Flash + V3.2 table rows ($/scan cells went DOWN) + prose |
| docs/claude-code-bug-bounty-build-plan.md | 1 site (line 219) |

Citations now point at primary source: "(per api-docs.deepseek.com; see docs/bountystrike_v6_phase0-1_technical_brief.md — corrects the v6 figure)".

## Verification

- grep "0.42" → zero DeepSeek-pricing hits in the 7 docs (remaining hits: v6 correction record, brief's refutation table, a Shodan cost example, a cosine-similarity score — all legitimate)
- grep "0.0028" → present in all 7 FIX-target docs
- Cost model consistent; per-scan $0.0051 cache-miss / $0.0044 cached << $0.20 target

## Method

Delegated to 3 parallel opus subagents (file-disjoint), then independently grep-verified — did not trust agent self-reports.

## Boundaries respected

- v6 docs left untouched (correction record, separately flagged superseded by brief)
- Other 6 corrections from 00-01 (refusal/XBOW/Welch/EV/competitive) untouched — brief re-audited them valid

## Carry-forward

- **Phase 1 infra task (not this plan):** DeepSeek V4 Pro 75%-off promo expires 2026-05-31 15:59 UTC; hardcoded pricing overcharges after. Brief recommends daily cron to re-fetch pricing.
- **research/02-routing-ev.md:68-78** HackerOne migration block has wrong date ("April 16" vs actual April 7) + lacks scope_exclusions — fix in a Phase 1 scope-ingestion plan (gate now RESOLVED, see STATE).
