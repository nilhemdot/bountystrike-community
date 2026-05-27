# BountyStrike v6 — Phased Build Plan

**Version:** 6.0.0
**Date:** May 21, 2026
**Status:** Implementation-Ready, Dependency-Ordered
**Supersedes:** v5.0.0 (Apr 28, 2026)
**Scope:** Dual-product — open-source Community Edition + commercial SaaS (Solo / Enterprise / Sovereign)

---

## How to read this document

This plan is organized as six phases (Phase 0 through Phase 5), each with an objective, the workstreams it contains, concrete tasks, explicit exit criteria, and the dependencies that gate it. The phases are dependency-ordered, not just chronologically listed: each one unlocks the next, and the plan calls out the few places where a workstream must start *earlier* than its phase would suggest (the SOC 2 observation clock is the main one).

The plan reconciles two prior roadmaps — v5's 20-week technical build and the v6 research report's 40-week dual-product expansion — into one 48-week sequence. Three principles govern the ordering. First, **truth-in-claims before anything ships** — the four empirical fixes are cheap and they protect the credibility of everything downstream, so they go first. Second, **open-source credibility before commercial monetization** — the Community Edition and the deterministic verifier moat earn the trust that makes the enterprise sale possible, so they precede the SaaS. Third, **compliance clocks start before the product that needs them** — SOC 2 Type II has a minimum three-month observation window, so it begins during the SaaS build, not at enterprise launch.

---

## Phase 0 — Truth-in-Claims & Foundation (Weeks 1–2)

### Objective
Fix the empirical soft spots in v5 before they propagate into code, cost models, or marketing, and make the two structural decisions (license, repo layout) that constrain every later phase.

### Why this is Phase 0 and not an afterthought
The v6 pressure-test found that ~85% of v5's claims verified cleanly against primary sources, but six did not, and four of those six are load-bearing for engineering or go-to-market. Shipping any of them unfixed risks the credibility of the entire 30,000-word plan the moment a sharp investor, partner, or hire fact-checks it. These fixes cost days, not weeks, and they gate the benchmark publication in Phase 2.

### Workstream 0.1 — Empirical corrections
| Task | Action | Source of truth |
|---|---|---|
| Correct DeepSeek pricing | Replace "$0.14/$0.28" everywhere with **$0.28 input / $0.42 output (cache-miss), $0.028 cache-hit input**. Rebuild the per-scan cost model with an explicit cache-hit ratio. | DeepSeek official API pricing |
| Reframe Anthropic refusal claim | Delete the hard "70%+ refusal rate." Replace with a *mechanism*: a runtime refusal classifier that routes known-refusal payload categories to Venice Dolphin / Hermes-4-70B. | No primary source exists for 70%; describe behavior, not a number |
| Label the XBOW N/A rate | Mark "~25% Informative/N/A" as "industry estimate, not vendor-confirmed," or drop the number and keep the qualitative argument. | Not vendor-confirmed |
| Verify HackerOne structured_scopes deprecation | **Do the 15-minute check against the HackerOne API changelog before writing migration code.** Do not schedule the Week-1 migration sprint until confirmed. | HackerOne API changelog (verify directly) |
| Reframe Welch's t-test | Present as a calibrated engineering heuristic with measured FP/FN rates, not an academically-derived method. | No academic citation found |
| Document EV decay constants | State whether lambda=0.00065 / mu=0.00963 were regression-fit (give the procedure + dataset) or hand-tuned (say so, mark pending calibration). | No derivation found |

### Workstream 0.2 — Competitive set correction
- Remove **Surf AI** from the competitive analysis — it is an agentic security *operations* platform (identity/cloud/SaaS hygiene), not an offensive-security competitor. Keeping it confuses anyone doing diligence.
- Re-rank **Bugcrowd (post-Mayhem acquisition, Nov 4 2025)** as the most credible incumbent threat: a $1B+ bug bounty platform now holding ForAllSecure's coverage-guided fuzzing + symbolic execution, with David Brumley as Chief AI & Science Officer. The dual-product play is explicitly competing with Bugcrowd's AEV trajectory.
- Note the **Mythos pricing ceiling** ($25/$125 per MTok): if Anthropic releases Mythos publicly before the ~July 2026 Glasswing disclosure window closes, the AEV category reprices around that token cost. Build the cost model so the SaaS tiers can be re-derived quickly.

### Workstream 0.3 — License & repo decision
- **License:** Community Edition under **AGPLv3** (Elastic's resolved 2024 model — OSI-approved, protects against unattributed SaaS-cloning). Enterprise code proprietary. Shared primitives under Apache 2.0.
- **Repo layout:** **pnpm workspaces + Turborepo** monorepo with three roots:
  - `bountystrike-core/` (Apache 2.0) — shared libraries, schemas, MCP client, evidence model
  - `bountystrike-community/` (AGPLv3) — all nine subagents, CLI, self-hosted deployment
  - `bountystrike-enterprise/` (proprietary) — multi-tenant control plane, SSO, AEV reports, integrations
- **Feature-flag layer:** OpenFeature SDK with Unleash (self-hosted) for OSS-visible flags; LaunchDarkly for SaaS tenant flags. Every enterprise-only capability sits behind a single `tier=enterprise` check at the subagent boundary — never forked code paths.

### Exit criteria
- [ ] All six empirical claims corrected or reframed in the master doc
- [ ] HackerOne structured_scopes status confirmed against the changelog (verified true/false)
- [ ] Cost model rebuilt with corrected DeepSeek pricing; <$0.20/solo-scan target re-validated or re-set
- [ ] Monorepo scaffold committed with the three-root split and feature-flag SDK wired
- [ ] License headers and CONTRIBUTING/CLA in place

### Dependencies
None — this is the root. Everything else depends on it.

---

## Phase 1 — Community Edition MVP: The Moat (Weeks 3–10)

### Objective
Ship a self-hostable, AGPLv3 Community Edition that does end-to-end authorized bounty work for a single operator, with the deterministic exploit verifier as the centerpiece. This is the credibility engine — the thing that earns GitHub stars and the trust that later makes the enterprise sale possible.

### Why the verifier comes first
The v6 research confirmed the strategic thesis with hard evidence: curl shut its HackerOne program (Stenberg, Jan 2026, confirmed-rate "below 5%"), HackerOne logged a 210% spike in AI vuln reports, and XBOW's own architecture separates deterministic verification from AI exploration because raw AI output is too noisy to submit. The verifier is not a feature — it is the reason the platform is allowed to exist in the ecosystem. It is also the hardest engineering, so it gets the most runway.

### Workstream 1.1 — Foundation (Weeks 3–4)
- Postgres 17 with pgvector + pgvectorscale (DiskANN) + ParadeDB (BM25)
- Hatchet (single-binary, Postgres-backed) for solo orchestration
- `CLAUDE.md` methodology file: legal posture first, seven-phase kill chain, evidence standard, hard prohibitions
- Content-addressable evidence store (SHA-256 keys to Cloudflare R2) + hash-chained audit log
- Cost meter wired to LiteLLM proxy from day one (corrected DeepSeek pricing)

### Workstream 1.2 — Scope ingestion (Weeks 4–5)
- Federated ingestion: arkadiyt/bounty-targets-data (hourly), bbscope v2 (authenticated, 6–12h), projectdiscovery/public-bugbounty-programs (daily)
- Normalized scope schema across HackerOne, Bugcrowd, Intigriti, YesWeHack, Immunefi
- RS256-signed scope JWT issuance; network-layer egress enforcement (not prompt-layer)
- Scope-diff change events + notification fan-out (Slack/Discord/Telegram/webhook)
- **Gated by Phase 0 HackerOne changelog verification**

### Workstream 1.3 — Deterministic verifier (Weeks 5–8) — THE MOAT
- XSS oracle: Playwright headless-browser execution confirmation (alert/DOM mutation)
- SSRF oracle: interactsh OAST callback verification with own collaborator subdomain
- Blind SQLi oracle: Welch's t-test on response-time distributions — **calibrated against a labeled corpus with published FP/FN rates** (per Phase 0 reframe)
- Open-redirect + SSTI oracles
- "No verification, no submission" enforced at the data model: findings without an evidence artifact are tagged `unverified` and filtered by default

### Workstream 1.4 — Recon agent + evidence chain (Weeks 8–10)
- `recon` subagent (Claude Haiku 4.5 solo) wired as a Claude Code subagent
- subfinder to dnsx to httpx to naabu to katana pipeline behind recon-MCP
- Politeness/rate-limiting token bucket per host
- Every discovered asset persisted with source_tool, confidence, scope_token provenance

### Exit criteria
- [ ] XSS oracle: 0 false positives, >90% true-positive on 20 known-vulnerable targets
- [ ] SQLi oracle: correctly flags time-based blind SQLi at the calibrated threshold, with documented FP/FN
- [ ] SSRF oracle: OAST callback confirmed for 5 known endpoints
- [ ] Recon completes the full pipeline on 3 test programs
- [ ] Every finding carries a SHA-256 evidence artifact + linked hash-chain audit entry + valid scope JWT
- [ ] One-line installer (curl | bash) provisions Community Edition on a Hetzner + Coolify box
- [ ] Public AGPLv3 release on GitHub

### Dependencies
Phase 0 (all). Workstream 1.2 specifically gated by the HackerOne changelog check.

---

## Phase 2 — Full Agent Fleet, Anti-Slop & Benchmark Publication (Weeks 11–18)

### Objective
Complete all nine subagents, implement the anti-slop discipline end-to-end, and publish honest benchmark numbers that become the platform's primary marketing anchor.

### Workstream 2.1 — Remaining subagents (Weeks 11–14)
- `exploit` agent with dual-track model routing (refusal classifier to Venice/Hermes fallback per Phase 0 mechanism), PoCs executed in Firecracker microVMs
- `validator` agent (consumes verifier oracles, promotes only confirmed findings)
- `dedup` agent (three-layer: exact fingerprint + pgvector semantic + program-level cross-check)
- `ai-vuln-hunter` (OWASP LLM Top 10, prompt-injection skill, Garak/Promptfoo/PyRIT MCPs)
- `cloud-recon` (cloud_enum, S3Scanner, Prowler, ScoutSuite)
- `reporter` (platform-specific formatters, T0–T3 approval tiers)
- `orchestrator` + `scope-guard` (defer-based hook escalation, per Claude Code v2.1.89)

### Workstream 2.2 — Anti-slop gates (Weeks 14–16)
- Evidence-gated triage: no finding reaches `submitted` without a verifiable artifact
- Confirmed-rate SLO instrumentation (target >70%)
- Three-layer kill switch
- AnyPoC reward-hacking countermeasures (self-exploitation, mock validation, hallucinated paths, timing coincidence)

### Workstream 2.3 — Benchmark publication (Weeks 16–18)
- Run BountyStrike against **both** XBOW benchmark variants and report honestly:
  - Black-box (XBOW's own ~85% reference)
  - White-box/source-aware (Shannon's 100/104 reference — explicitly noted as the easier variant)
- Publish per-target cost alongside accuracy. The defensible claim: **comparable accuracy to best-in-class open-source autonomous pentesters (Deadend CLI ~80% at ~$1.17/challenge) at a fraction of the cost, with deterministic verification on top.**
- Every subsequent release ships updated benchmark numbers — a public capability audit trail no black-box competitor matches.

### Exit criteria
- [ ] All nine subagents operational and integration-tested
- [ ] Confirmed-rate SLO >70% on internal test corpus
- [ ] Dedup recall >95% on known-duplicate set
- [ ] Published benchmark report (both variants, with cost), reproducible by third parties
- [ ] 5+ validated findings submitted to real programs by alpha hunters

### Dependencies
Phase 1 (verifier + evidence chain). Benchmark publication gated by Phase 0 cost-model correction.

---

## Phase 3 — Solo SaaS (Cloud) (Weeks 19–26)

### Objective
Launch a hosted, multi-tenant "Solo Cloud" tier at $29/user/month — the on-ramp that converts Community Edition users to paying customers and starts the revenue and compliance clocks.

### Critical early-start item
**SOC 2 Type II observation begins HERE, in Week 19 — not at Enterprise launch.** The minimum observation window is three months and the realistic first-time program is 9–12 months. If you wait until Phase 4 to start, you cannot sell to enterprise for nearly a year after the product is ready. Engage Vanta or Drata in Week 19.

### Workstream 3.1 — Multi-tenant core (Weeks 19–22)
- Temporal Cloud replaces Hatchet for durable multi-tenant workflows
- Postgres + Row-Level Security; per-tenant Turbopuffer namespaces engaged past ~1M findings/tenant
- Firecracker/E2B microVM pool for per-job isolation with egress allowlists
- WorkOS AuthKit (foundation for SSO/SCIM later)
- Per-tenant LiteLLM budget ceilings with "scan paused, top up" UX

### Workstream 3.2 — Killer UX baseline (Weeks 22–25)
- Next.js 16 + shadcn/ui dashboard
- Live agent-reasoning stream (SSE) — the Cursor/Vercel pattern
- Evidence inspector with replayable exploit confirmation — the Stripe drill-down pattern
- Command palette (Cmd+K) — the Linear pattern
- Cost meter + budget alarms
- **CTEM five-stage progress visualization** — the differentiator competitors are not yet shipping well

### Workstream 3.3 — Billing & onboarding (Weeks 25–26)
- Stripe usage-based metering (accurate within 5% of actual LLM cost)
- BYOK option (OpenRouter 1M free BYOK requests/month as the default cheap path)
- Self-serve onboarding; Community to Cloud upgrade flow

### Exit criteria
- [ ] Multi-tenant isolation verified by penetration test (zero cross-tenant access)
- [ ] Temporal workflow survives server restart (durability test)
- [ ] microVM pool handles 10 concurrent scans
- [ ] Billing metering accurate within 5%
- [ ] **SOC 2 Type II observation window started (Week 19) and tracking**
- [ ] 20+ beta hunters at >65% confirmed-rate

### Dependencies
Phase 2 (full fleet). SOC 2 vendor engaged Week 19 regardless of other progress.

---

## Phase 4 — Enterprise / AEV (Weeks 27–36)

### Objective
Ship the enterprise tier positioned as an **Adversarial Exposure Validation (AEV)** product inside Gartner's CTEM framework — competing with Pentera, Horizon3/NodeZero, Picus, Cymulate, and post-Mayhem Bugcrowd — not as a "bug bounty tool."

### Workstream 4.1 — Feature gating along CTEM (Weeks 27–30)
Map the nine subagents to CTEM stages and gate accordingly:

| CTEM stage | Subagents | Gating |
|---|---|---|
| Scoping | scope-guard, orchestrator | OSS Free |
| Discovery | recon, cloud-recon | OSS Free |
| Prioritization | ai-vuln-hunter, dedup | OSS solo / **Enterprise: cross-tenant + business context** |
| Validation | exploit, validator | OSS self-hosted / **Enterprise: managed sandbox** |
| Mobilization | reporter | OSS individual / **Enterprise: SOAR/Jira/ServiceNow** |

### Workstream 4.2 — Enterprise requirements (Weeks 30–33)
- SSO (SAML 2.0 / OIDC) + SCIM provisioning via WorkOS
- Audit log export; BYOK with AWS KMS / HashiCorp Vault
- ServiceNow / Jira / SOAR integrations
- AEV/CTEM compliance reports
- SOC 2 Type II report delivered (observation started Week 19, report lands ~Week 31+)

### Workstream 4.3 — EU market hook (Weeks 33–36)
- **CRA Companion**: free tool that turns any BountyStrike finding into an EU CRA Article 14 draft notification (24h early warning / 72h detailed / 14d final). Aligns to the Sept 11, 2026 ENISA Single Reporting Platform go-live. A no-brainer EU funnel hook.
- Treat NIS2 as in-flux (20/27 member states transposed as of Jan 2026; Commission proposed easing amendments Jan 20, 2026) — do not hard-code obligations; gate behind legal review.

### Pricing (from v6 research)
- **Community:** AGPLv3, free forever, self-hosted
- **Solo Cloud:** $29/user/mo
- **Enterprise:** from $25K platform/yr + ~$15–25/asset/yr metered (undercuts NodeZero's entry; below Pentera's ~$100K ACV); target ACV $100–150K
- **Sovereign:** $250K+/yr (Phase 5)

### Exit criteria
- [ ] Feature flags gate all enterprise capabilities behind tier=enterprise (no forked paths)
- [ ] SSO + SCIM live and tested with a real enterprise IdP
- [ ] SOC 2 Type II report issued
- [ ] First 3 enterprise pilots signed
- [ ] CRA Companion shipped and live

### Dependencies
Phase 3 (multi-tenant + SOC 2 clock started). SOC 2 report is the hard gate on enterprise sales.

---

## Phase 5 — Sovereign / Government (Weeks 37–48+)

### Objective
Air-gapped, on-prem deployment for defense, government, and financial-services buyers with data-residency and authorization mandates.

### Workstreams
- Air-gapped deployment (no external LLM calls; self-hosted models — Foundation-Sec-8B, Deep Hat V2, WhiteRabbitNeo V3, Pentest-R1 fallback)
- HashiCorp Vault integration; full secrets isolation
- **FedRAMP 20x Moderate pilot** — the automation-first track (target $100K–$300K vs $500K–$1.5M legacy; new Low/Moderate openings targeted Q3 2026). Initiate application as soon as openings appear.
- Hadrian-style per-test pricing as a procurement-friction-free sales motion for buyers allergic to annual subscriptions

### Anti-slop go-to-market (parallel, can start in Phase 2)
- Run a **Glasswing/AISLE-style "expert-guided AI" program**: partner with 5–10 OSS security maintainers to run BountyStrike on their codebases, AISLE-style (12/12 OpenSSL CVEs, zero invalid reports, public CTO endorsement). This is the strongest possible counter-narrative to the curl AI-slop story and the most credible enterprise trust signal.

### Exit criteria
- [ ] Air-gapped install validated with zero external egress
- [ ] FedRAMP 20x Moderate pilot application submitted
- [ ] 1+ sovereign/government or financial-services design partner
- [ ] Published expert-guided-AI case study with a named OSS maintainer

### Dependencies
Phase 4 (enterprise + SOC 2). FedRAMP gated by external program windows (Q3 2026).

---

## Cross-cutting workstreams (all phases)

### Engineering hygiene
- Property-based testing (fast-check / Hypothesis); mutation testing (Stryker / mutmut)
- Adversarial testing: fuzz the orchestrator with malformed scope ingests and prompt-injected target HTML
- CI/CD: Sigstore signing on every artifact, SLSA L3 provenance, in-toto attestations, cosign image attestation, Syft SBOM — baseline for any security tool sold to enterprise post-Glasswing

### Benchmark cadence
- Every release ships updated XBOW (both variants) + cost numbers — the public capability audit trail

### Infrastructure (validated in v6, keep as-is)
- Solo: Hetzner CCX22 + Coolify + R2 + SOPS/age
- SaaS: Temporal Cloud + Firecracker/E2B + Postgres RLS + Turbopuffer + WorkOS + R2 + Cloudflare Workers + Vault (enterprise secrets)

---

## Top risks (carried from v6, re-prioritized for this sequence)

| # | Risk | Phase exposed | Mitigation |
|---|---|---|---|
| R1 | SOC 2 clock started too late, blocks enterprise sales for ~1 year | Phase 3/4 | Start observation Week 19, non-negotiable |
| R2 | Mythos public release reprices AEV category | Any | Cost model built for fast re-derivation against $25/$125 token cost |
| R3 | Empirical claim found false post-publication | Phase 2 | Phase 0 fixes; benchmark reproducibility |
| R4 | Bugcrowd (post-Mayhem) ships competing dual-product | Phase 4 | Transparency + cost + Claude Code native + CTEM UI differentiation |
| R5 | Prompt injection breaks scope | All | Network-layer JWT enforcement at tap0, never prompt-layer |
| R6 | AI slop gets platform banned from programs | Phase 1+ | Deterministic verifier + >70% confirmed-rate SLO + expert-guided program |
| R7 | NIS2/CRA obligations shift | Phase 4 | Treat as in-flux; legal review before binding features |

---

## The one-paragraph version

Fix the six empirical soft spots and split the repo (Phase 0, 2 weeks). Build the deterministic verifier and ship a free AGPLv3 Community Edition that earns trust (Phase 1, weeks 3–10). Complete the nine-agent fleet, enforce anti-slop, and publish honest benchmarks as the marketing anchor (Phase 2, weeks 11–18). Launch a $29/mo Solo Cloud tier and — critically — start the SOC 2 clock the day it goes live (Phase 3, weeks 19–26). Ship the enterprise AEV tier positioned inside Gartner CTEM, gated by feature flags along the five CTEM stages, with SSO/SCIM, SOC 2 report, and a free EU CRA Companion hook (Phase 4, weeks 27–36). Add air-gapped Sovereign deployment and a FedRAMP 20x pilot for government and finance, and run an AISLE-style expert-guided-AI program as the definitive anti-slop proof (Phase 5, weeks 37–48+). Build the moat first, monetize the trust second, and let the compliance clocks run in the background so they never block a sale.

---

*End of BountyStrike v6 Phased Build Plan.*
*All empirical claims reflect the v6 pressure-test (May 21, 2026). Pricing for third-party competitors is industry-estimated unless vendor-confirmed; see v6 research report caveats.*
