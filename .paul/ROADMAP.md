# Roadmap: BountyStrike-AIv7

## Overview

Six dependency-ordered phases over 48 weeks: fix empirical soft spots and split the repo (Phase 0), build the deterministic verifier moat and ship AGPLv3 Community Edition (Phase 1), complete all nine subagents and publish honest benchmarks (Phase 2), launch Solo Cloud SaaS and start the SOC 2 clock (Phase 3), ship Enterprise/AEV tier inside Gartner CTEM (Phase 4), add air-gapped Sovereign deployment and FedRAMP 20x pilot (Phase 5).

## Current Milestone

**v0.1 Community Edition MVP** (v0.1.0)
Status: In progress
Phases: 1 of 6 complete

## Phases

| Phase | Name | Plans | Status | Completed |
|-------|------|-------|--------|-----------|
| 0 | Truth-in-Claims & Foundation | 4 | Complete | 2026-05-29 |
| 1 | Community Edition MVP: The Moat | TBD | Active (next) | - |
| 2 | Full Agent Fleet, Anti-Slop & Benchmark | TBD | Not started | - |
| 3 | Solo SaaS (Cloud) | TBD | Not started | - |
| 4 | Enterprise / AEV | TBD | Not started | - |
| 5 | Sovereign / Government | TBD | Not started | - |

## Phase Details

### Phase 0: Truth-in-Claims & Foundation

**Goal:** Fix 6 empirical soft spots, correct competitive set, scaffold monorepo with license split
**Depends on:** Nothing (root phase)
**Research:** Likely (HackerOne changelog verification required before writing migration code)
**Research topics:** HackerOne structured_scopes API changelog; DeepSeek official pricing; EV decay constant derivation

**Scope:**
- Fix 6 empirical claims (DeepSeek pricing, Anthropic refusal framing, XBOW N/A rate, HackerOne changelog, Welch's framing, EV decay constants)
- Correct competitive set (remove Surf AI, re-rank Bugcrowd post-Mayhem)
- AGPLv3 + monorepo scaffold (bountystrike-core / bountystrike-community / bountystrike-enterprise)
- OpenFeature SDK + Unleash wired; license headers + CONTRIBUTING/CLA

**Plans:**
- [x] 00-01: Empirical corrections + competitive set fix — done 2026-05-27 (required FIX cycle for DeepSeek pricing)
- [x] 00-02: Hybrid scaffold — 3-root license split + pnpm/Turborepo over uv + CONTRIBUTING/CLA — done 2026-05-27
- [x] 00-03: OpenFeature SDK + custom Unleash provider (no official Python provider — brief), fail-closed tier=enterprise gate — done 2026-05-29
- [x] 00-04: SPDX license-header sweep across 250 source files (6-root allow-list, idempotent script) + CI import-ban enforcement — done 2026-05-29

Note: Phase 0 grew 2→4 plans. (1) repo was already a uv workspace → monorepo is a hybrid layer (00-02). (2) feature-flag SDK its own plan due to OpenFeature→Unleash Python gap (00-03). (3) 243-file SPDX header sweep split from 00-03 to keep design vs. mechanical-sweep separate (00-04). Completing 00-04 triggers Phase 0→1 transition.

### Phase 1: Community Edition MVP — The Moat

**Goal:** Ship self-hostable AGPLv3 Community Edition with deterministic verifier as the centrepiece
**Depends on:** Phase 0 (all); Workstream 1.2 gated by HackerOne changelog check
**Research:** Unlikely (patterns established in v5)

**Scope:**
- Postgres 17 + pgvectorscale (DiskANN) + ParadeDB (BM25)
- Federated scope ingestion (arkadiyt/bounty-targets-data, bbscope v2, projectdiscovery); RS256 scope JWT
- Deterministic verifier: XSS (Playwright), SSRF (OAST/interactsh), SQLi (Welch's t-test), open-redirect, SSTI
- Recon agent full pipeline (subfinder → dnsx → httpx → naabu → katana)
- One-line installer on Hetzner + Coolify; public AGPLv3 release

**Plans:**
- [ ] 01-01: DB Foundation (Postgres 17 + custom image: pgvector + vectorscale + pg_search; DiskANN + BM25 migrations) — planned 2026-05-29
- [ ] 01-02: Hatchet v1 + evidence store (R2, SHA-256 content-addressable + hash-chain audit)
- [ ] 01-03: Scope ingestion + RS256 JWT + scope-diff notifications
- [ ] 01-04: Deterministic verifier oracles (XSS + SSRF + SQLi + open-redirect + SSTI)
- [ ] 01-05: Recon agent pipeline + rate-limiting token bucket
- [ ] 01-06: One-line installer + public release

### Phase 2: Full Agent Fleet, Anti-Slop & Benchmark

**Goal:** All 9 subagents operational; confirmed-rate SLO >70%; published XBOW benchmark
**Depends on:** Phase 1 (verifier + evidence chain); benchmark gated by Phase 0 cost-model correction
**Research:** Likely (XBOW benchmark methodology; Firecracker microVM pool setup)

**Scope:**
- Remaining subagents: exploit (dual-track routing), validator, dedup (3-layer), ai-vuln-hunter, cloud-recon, reporter, orchestrator+scope-guard
- Anti-slop gates: evidence-gated triage, confirmed-rate SLO instrumentation, 3-layer kill switch
- Published benchmark: XBOW black-box (~85% reference) + white-box/source-aware (Shannon 100/104)

**Plans:**
- [ ] 02-01: Exploit + validator + dedup agents
- [ ] 02-02: ai-vuln-hunter + cloud-recon + reporter agents
- [ ] 02-03: Anti-slop gates + confirmed-rate SLO instrumentation
- [ ] 02-04: Benchmark run + publication (both variants + cost)

### Phase 3: Solo SaaS (Cloud)

**Goal:** Launch $29/user/mo Solo Cloud tier; start SOC 2 Type II observation clock (Week 19)
**Depends on:** Phase 2 (full fleet)
**Research:** Likely (Temporal Cloud, WorkOS AuthKit, Stripe usage-based metering, Firecracker/E2B pool)

**Scope:**
- Multi-tenant control plane: Temporal Cloud, Postgres RLS, Turbopuffer, WorkOS AuthKit
- Firecracker/E2B microVM pool for per-job isolation
- Next.js 16 + shadcn/ui dashboard with SSE agent-reasoning stream + evidence inspector
- Stripe usage-based metering + BYOK option
- SOC 2 Type II observation started (Vanta or Drata engaged Week 19)

**Plans:**
- [ ] 03-01: Multi-tenant core (Temporal + Postgres RLS + Turbopuffer + WorkOS)
- [ ] 03-02: Killer UX baseline (Next.js dashboard + SSE stream + evidence inspector)
- [ ] 03-03: Billing + onboarding + SOC 2 vendor engagement

### Phase 4: Enterprise / AEV

**Goal:** Enterprise tier as AEV inside Gartner CTEM; SOC 2 report issued; first 3 pilots signed
**Depends on:** Phase 3 (multi-tenant + SOC 2 clock started)
**Research:** Unlikely (patterns from Phase 3; SOC 2 is external process)

**Scope:**
- Feature flags gate 5 CTEM stages along subagent boundaries (no forked code paths)
- SSO (SAML 2.0/OIDC) + SCIM via WorkOS; audit log export; BYOK with AWS KMS/Vault
- ServiceNow / Jira / SOAR integrations; AEV/CTEM compliance reports
- CRA Companion: EU Article 14 draft notification generator (targets Sept 11 2026 ENISA go-live)
- Glasswing/AISLE-style expert-guided program (5–10 OSS maintainers)

**Plans:**
- [ ] 04-01: CTEM feature-flag gating across all 9 subagents
- [ ] 04-02: SSO/SCIM + audit log + BYOK + SOAR integrations
- [ ] 04-03: CRA Companion + EU market hook
- [ ] 04-04: Expert-guided AI program launch

### Phase 5: Sovereign / Government

**Goal:** Air-gapped on-prem deployment; FedRAMP 20x Moderate pilot; 1+ sovereign design partner
**Depends on:** Phase 4 (enterprise + SOC 2)
**Research:** Likely (FedRAMP 20x automation-first track; self-hosted model selection)

**Scope:**
- Air-gapped deployment (Foundation-Sec-8B, Deep Hat V2, WhiteRabbitNeo V3, Pentest-R1 fallback)
- HashiCorp Vault full secrets isolation; no external LLM calls
- FedRAMP 20x Moderate pilot application (target Q3 2026 openings)
- Hadrian-style per-test pricing as procurement-friction-free sales motion

**Plans:**
- [ ] 05-01: Air-gapped deployment + self-hosted model stack
- [ ] 05-02: FedRAMP 20x application + sovereign design partner

---
*Roadmap created: 2026-05-27*
*Last updated: 2026-05-29 — Phase 1 plan list split (01-01 DB foundation; Hatchet+evidence → 01-02); 6 plans*
