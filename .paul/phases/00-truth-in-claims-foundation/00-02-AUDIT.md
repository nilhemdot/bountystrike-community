# Enterprise Plan Audit Report

**Plan:** .paul/phases/00-truth-in-claims-foundation/00-02-PLAN.md
**Audited:** 2026-05-27
**Verdict:** Conditionally acceptable → ready after auto-applied fixes

---

## 1. Executive Verdict

Conditionally acceptable. Scope discipline is good and the hybrid (keep uv, layer Turborepo) is the right architectural call. But this is a license/compliance plan for an AGPLv3 OSS release — license correctness is legally load-bearing — and it had three gaps that would fail a real compliance audit. All three auto-applied. Now ready.

## 2. What Is Solid

- **pyproject.toml fenced in boundaries** — uv workspace stays authoritative; layering not replacing.
- **Turborepo 2.x `tasks:` trap encoded** in AC-1 + verification.
- **Physical reorg + header injection deferred** — keeps blast radius small.
- **AC-5 env-gap fallback** — doesn't fail the plan on a missing node runtime.

## 3. Enterprise Gaps Identified

- **G1 — License-text integrity:** "fetch/write full text" risked an LLM paraphrasing the GPL/Apache from memory → legally invalid LICENSE. No fidelity check.
- **G2 — SSOT contradiction:** root manifest asserts control-plane/+mcp/ are AGPL community-tier, but packages/community/ is an empty marker dir and the actual AGPL code lives elsewhere with no LICENSE. License↔code binding was prose-only.
- **G3 — AGPL §13:** the network-use/source-offer clause — the whole basis of "AGPL community + proprietary SaaS" — was unstated. Getting the §13 boundary wrong is the existential dual-product license risk.
- **G4 — CLA enforceability:** "CLA.md present" implied governance that an unsigned doc doesn't provide.

## 4. Upgrades Applied to Plan

### Must-Have (Release-Blocking)

| # | Finding | Plan Section Modified | Change Applied |
|---|---------|----------------------|----------------|
| 1 | G1 text integrity | AC-6 + Task 2 action/verify | Fetch VERBATIM canonical text from spdx.org/gnu.org; verify AGPL contains "13. Remote Network Interaction" (proves full text, not paraphrase) |
| 2 | G2 license↔code bind | AC-7 + Task 3 + LICENSES.md | New LICENSES.md maps control-plane/ + mcp/* + scripts/ to AGPL-3.0 — explicit, machine-checkable |
| 3 | G3 AGPL §13 | AC-8 + Task 3 + LICENSE/CONTRIBUTING | Both state §13 network-use obligation + core→community→enterprise relicensing boundary |

### Strongly Recommended

| # | Finding | Plan Section Modified | Change Applied |
|---|---------|----------------------|----------------|
| 4 | G4 CLA | Task 3 action/verify | CLA.md notes it's aspirational until DCO/sign-off wired |

### Deferred

| # | Finding | Rationale |
|---|---------|-----------|
| - | None | All gaps must-have or strongly-recommended; all applied |

## 5. Audit & Compliance Readiness

As-submitted would fail a license audit on G1 (unverified text) + G2 (unbound mapping). With fixes: texts verifiable, mapping explicit via LICENSES.md, §13 stated. G3 is the commercially critical one — the dual-product moat rests on the AGPL boundary being correct.

## 6. Final Release Bar

Ship-ready now that canonical texts are verified (not paraphrased), every code dir is bound to a tier+license in LICENSES.md, and AGPL §13 + the relicensing boundary are stated. Signed.

---

**Summary:** Applied 3 must-have + 1 strongly-recommended. Deferred 0.
**Plan status:** Updated and ready for APPLY

---
*Audit performed by PAUL Enterprise Audit Workflow*
*Audit template version: 1.0*
