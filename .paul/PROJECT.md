# BountyStrike-AIv7

## What This Is

A Claude Code-native autonomous bug bounty platform that runs recon → scan → validate → report end-to-end for authorized targets. It ships as a dual-product: a free AGPLv3 Community Edition (self-hosted) and a commercial SaaS (Solo Cloud / Enterprise / Sovereign). The deterministic exploit verifier — not raw AI output — is the centerpiece: no finding reaches submission without a SHA-256-linked evidence artifact confirming the vulnerability is real.

## Core Value

Automated bug bounty hunting that produces only verified, non-duplicate findings — giving solo hunters and enterprise security teams a credible alternative to noisy AI-generated submissions.

## Current State

| Attribute | Value |
|-----------|-------|
| Type | Application |
| Version | 0.0.0 |
| Status | Phase 0 Complete — Phase 1 In Progress |
| Last Updated | 2026-05-29 |

## Requirements

### Core Features

- **Recon** — subfinder → dnsx → httpx → naabu → katana pipeline; every asset persisted with source + scope JWT provenance
- **Scan** — nuclei, ffuf, sqlmap, kiterunner, arjun across recon artifacts; normalised Finding rows emitted
- **Validate** — deterministic oracles (XSS/Playwright, SSRF/OAST, SQLi/Welch's t-test, open-redirect, SSTI); no submission without verified evidence artifact
- **Report** — platform-specific formatters (HackerOne, Bugcrowd, Intigriti, YesWeHack, Immunefi); T0–T3 approval tiers
- **Scope enforcement** — RS256 scope JWT at network layer (tap0 egress); never prompt-layer

### Validated (Shipped)
- [x] 15 MCP servers (14 Python FastMCP + 1 TypeScript scope-mcp)
- [x] 9 sub-agent specs (recon, cloud-recon, scanner, ai-vuln-hunter, exploit, validator, reporter, scope-guard, program-selector)
- [x] FastAPI control-plane with DDD domains
- [x] Postgres 17 + pgvector + 13 schema tables
- [x] 8 oracle implementations in oracle-mcp (TPR=1.0/FPR=0.0)
- [x] T3 approval plumbing wired in orchestrator.py
- [x] 5 field-validation suites (SSRF→IMDS, IDOR, RCE, SSTI, Open Redirect)
- [x] Model routing cost optimization matrix
- [x] Empirical corrections: DeepSeek pricing ($0.14/$0.0028/$0.28), HackerOne structured_scopes (READ current), competitive set pruned (Surf AI removed) — Phase 0 plan 00-01
- [x] Hybrid monorepo scaffold: 3-root license split (AGPL-3.0/Apache-2.0/LicenseRef-Proprietary), pnpm/Turborepo layer, CONTRIBUTING.md + CLA stub — Phase 0 plan 00-02
- [x] OpenFeature + custom Unleash Python provider: fail-closed tier=enterprise gate, no official provider workaround — Phase 0 plan 00-03
- [x] SPDX header sweep: 250 source files stamped across 6 roots, idempotent script, CI import-linter community↔enterprise ban — Phase 0 plan 00-04

### Active (In Progress)
None yet.

### Planned (Next)

**Phase 1 — Community Edition MVP (Weeks 3–10) — ACTIVE**
- Federated scope ingestion (arkadiyt/bounty-targets-data, bbscope v2, projectdiscovery)
- Deterministic verifier moat
- One-line installer on Hetzner + Coolify; public AGPLv3 release

**Phase 2 — Full Agent Fleet + Benchmark (Weeks 11–18)**
- All 9 subagents operational; confirmed-rate SLO >70%
- Published XBOW benchmark (both variants, with cost)

**Phase 3 — Solo SaaS (Weeks 19–26)**
- Multi-tenant control plane; $29/user/mo Solo Cloud tier
- SOC 2 Type II observation starts Week 19

**Phase 4 — Enterprise / AEV (Weeks 27–36)**
- Feature flags gate CTEM stages; SSO/SCIM; CRA Companion for EU

**Phase 5 — Sovereign / Government (Weeks 37–48+)**
- Air-gapped deployment; FedRAMP 20x Moderate pilot

### Out of Scope
- NIS2/CRA hard-coded obligations — treat as in-flux; legal review required before binding features
- Surf AI in competitive analysis — agentic security operations, not offensive-security competitor

## Constraints

### Technical Constraints
- All async: httpx.AsyncClient, asyncpg, aioboto3 — no blocking calls in async context
- Pydantic models at every input boundary (HTTP, MCP tool, file parser)
- ruff line-length 100, target py312, rules: E F W I N UP B SIM ASYNC
- Scope enforcement at network layer (tap0 egress), never prompt-layer
- "No verification, no submission" — findings without evidence artifact tagged `unverified` and filtered by default
- Context7 for live docs lookup during planning/research phases
- Oracle field-validation suites must hit TPR=1.0 / FPR=0.0 before wiring to agents

### Business Constraints
- HackerOne structured_scopes status must be confirmed against changelog before writing migration code
- SOC 2 Type II observation window must start at Phase 3 launch (Week 19) — not at enterprise launch
- Confirmed-rate SLO >70% required before community edition ships
- Cost target: <$0.20/solo-scan (re-validate after DeepSeek pricing correction)
- Benchmark publication gated by Phase 0 cost-model correction

## Key Decisions

| Decision | Rationale | Date | Status |
|----------|-----------|------|--------|
| AGPLv3 for Community Edition | Elastic's resolved 2024 model — OSI-approved, protects against unattributed SaaS-cloning | 2026-05-21 | Active |
| pnpm workspaces + Turborepo monorepo | Three-root split: core (Apache 2.0), community (AGPLv3), enterprise (proprietary) | 2026-05-21 | Active |
| OpenFeature SDK + Unleash for OSS flags / LaunchDarkly for SaaS tenant flags | Enterprise capabilities behind single `tier=enterprise` check — never forked code paths | 2026-05-21 | Active |
| Deterministic verifier as moat (not raw AI output) | curl shut HackerOne program; HackerOne logged 210% spike in AI vuln reports; raw AI too noisy | 2026-05-21 | Active |
| Temporal Cloud replaces Hatchet for multi-tenant SaaS | Hatchet fine for solo; Temporal required for durable multi-tenant workflows | 2026-05-21 | Planned (Phase 3) |
| Position as AEV inside Gartner CTEM (not "bug bounty tool") | Competes with Pentera/NodeZero/Picus/Cymulate; undercuts NodeZero entry pricing | 2026-05-21 | Active |

## Success Metrics

| Metric | Target | Current | Status |
|--------|--------|---------|--------|
| Oracle TPR | 1.0 | 1.0 (8 oracles) | Achieved |
| Oracle FPR | 0.0 | 0.0 (8 oracles) | Achieved |
| Confirmed-rate SLO | >70% | TBD | Not started |
| Dedup recall | >95% | TBD | Not started |
| Cost per solo scan | <$0.20 | TBD (pending DeepSeek correction) | Not started |
| XSS oracle TP on known-vulnerable targets | >90% on 20 targets | TBD | Not started |
| XBOW benchmark (black-box) | ~85% (XBOW reference) | TBD | Not started |
| Beta hunters at confirmed-rate | 20+ at >65% confirmed | TBD | Not started |

## Tech Stack / Tools

| Layer | Technology | Notes |
|-------|------------|-------|
| Language | Python 3.12 | uv package manager, ruff linter |
| API Framework | FastAPI + DDD | control-plane/ with 6 domains |
| Database | Postgres 17 + pgvector | 13 schema tables; pgvectorscale + ParadeDB Phase 1 |
| Cache / Kill-switch | Redis 7 | flag store + approval cache |
| Workflow (solo) | Hatchet | single-binary, Postgres-backed |
| Workflow (SaaS) | Temporal Cloud | Phase 3+ multi-tenant |
| Agent framework | Claude Code sub-agents | 9 specs in .claude/agents/ |
| MCP servers | 15 (14 FastMCP Python + 1 TypeScript) | stdio transport |
| LLM routing | LiteLLM proxy | cost metering + DeepSeek/Venice/Hermes fallback |
| Evidence store | Cloudflare R2 | SHA-256 content-addressable + hash-chain audit log |
| OAST callbacks | Interactsh | own collaborator subdomain |
| Exploit isolation | Firecracker microVMs | per-job isolation with egress allowlists |
| Frontend (Phase 3) | Next.js 16 + shadcn/ui | SSE agent-reasoning stream; Cmd+K palette |
| Auth (Phase 3+) | WorkOS AuthKit | SSO/SCIM foundation |
| Billing (Phase 3) | Stripe | usage-based metering; BYOK option |
| Infra (solo) | Hetzner CCX22 + Coolify | one-line installer target |
| Secrets | SOPS/age (solo) / HashiCorp Vault (enterprise) | |
| CI/CD | Sigstore + SLSA L3 + cosign + Syft SBOM | SLSA L3 provenance |
| Observability | Langfuse | trace-level hunt visibility |
| Feature flags | OpenFeature + Unleash (OSS) / LaunchDarkly (SaaS) | |

## Specialized Flows

See: .paul/SPECIAL-FLOWS.md

Quick Reference:
- /llm-recon → AI endpoint fingerprinting (always first)
- /llm-audit → AI red-team findings compilation
- /ai-jailbreak → Structural jailbreak probes
- /obfuscation-bypass → Content-filter evasion encoding
- /openrouter → Multi-model attack orchestration
- /e2e → Pipeline end-to-end testing

## Links

| Resource | URL |
|----------|-----|
| Repository | bountystrike-ai7 (local) |
| Architecture | docs/system-architecture.md |
| v6 Build Plan | docs/bountystrike_v6_phased_build_plan.md |
| v6 Research Report | docs/BountyStrike v6 Research Report... .md |

---
*PROJECT.md — Updated when requirements or context change*
*Last updated: 2026-05-29 after Phase 0 (Truth-in-Claims & Foundation — 4/4 plans complete)*
