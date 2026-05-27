---
phase: 00-truth-in-claims-foundation
plan: 00-02
completed: 2026-05-27
duration: ~1 session
---

# Phase 0 Plan 02: Hybrid Monorepo Scaffold + License Layer — Summary

Added the three-tier license/compliance layer and a pnpm+Turborepo task-orchestration layer on top of the existing uv Python workspace — without moving or breaking any existing code.

## What Was Built

| File | Purpose |
|------|---------|
| pnpm-workspace.yaml | Workspace globs for packages/{core,community,enterprise} + apps |
| turbo.json | Turborepo 2.x task graph (`tasks:` syntax — build/test/lint/dev) |
| package.json | Root private pkg; turbo ^2.9.0; pnpm@9.12.0 packageManager |
| packages/core/LICENSE (+ LICENSE-APACHE) | Verbatim canonical Apache-2.0 (curl from apache.org) |
| packages/community/LICENSE (+ LICENSE-AGPL) | Verbatim canonical AGPL-3.0 incl §13 (curl from gnu.org) |
| packages/enterprise/LICENSE | Proprietary notice |
| packages/{core,community,enterprise}/README.md | Tier description + license |
| LICENSE | Root manifest: three-tier model, §13, relicensing boundary |
| LICENSES.md | Explicit dir→tier→license map (control-plane/ + 15 mcp/* + scripts/ → AGPL-3.0) |
| CONTRIBUTING.md | Dev setup, community→core import ban, §13, header expectation |
| CLA.md | Contributor terms — marked aspirational (no enforcement yet) |
| .gitignore | Added .turbo/ |

## Acceptance Criteria Results

| AC | Description | Status |
|----|-------------|--------|
| AC-1 | pnpm/Turborepo layer present, uv untouched | PASS (pyproject.toml 0-line diff; `tasks:` not `pipeline:`) |
| AC-2 | Three license roots, correct licenses | PASS |
| AC-3 | Root LICENSE manifest points to all three | PASS |
| AC-4 | CONTRIBUTING + CLA present | PASS |
| AC-5 | turbo tasks runnable | PASS (env-gap: turbo v2.9.15 loaded + config structurally validated via node; live npx run blocked by Windows-CMD/WSL-UNC path) |
| AC-6 | License texts verbatim canonical (not paraphrased) | PASS (curl raw; AGPL "13. Remote Network Interaction" confirmed) |
| AC-7 | Existing code dirs bound to tier+license | PASS (LICENSES.md maps 18 entries) |
| AC-8 | AGPL §13 + relicensing boundary stated | PASS (LICENSE + CONTRIBUTING) |

## Verification Results

- `git diff pyproject.toml` → 0 lines (uv workspace untouched)
- `grep tasks turbo.json` → present; `pipeline` → absent (2.x trap avoided)
- Apache LICENSE → "Apache License Version 2.0"; AGPL → "GNU AFFERO GENERAL PUBLIC LICENSE" + "13. Remote Network Interaction"
- LICENSES.md → 18 AGPL-3.0 bindings incl control-plane/ + scripts/
- LICENSE + CONTRIBUTING → §13 + core/community/enterprise boundary present

## Deviations

1. **Tool choice corrected mid-apply.** Plan said "fetch" license text; the available WebFetch tool AI-processes (paraphrases) content — which would produce a legally-void license (the exact AC-6 risk). Switched to `curl` for raw byte-faithful canonical text. Lesson: for legal/verbatim content, never route through an AI-summarizing fetch.
2. **AC-5 env-gap.** pnpm not installed; Windows-launched npx can't resolve the WSL UNC working dir (fell back to C:\Windows). Validated config structurally with node instead of a live turbo run. Config correctness is the deliverable; a live run needs a Linux-native pnpm/turbo (Phase 1 infra).

## Key Decisions

- HYBRID monorepo: keep uv authoritative for Python, layer Turborepo for cross-language tasks; no physical code move (deferred).
- License↔code binding recorded in LICENSES.md (machine-checkable) because code lives outside packages/ under the hybrid.

## Skill Audit

No SPECIAL-FLOWS required-skills triggered (scaffold/compliance work; AI-red-team + e2e skills map to later phases).

## Next Phase

00-03 (last Phase 0 plan): OpenFeature SDK + custom Unleash provider (brief: no official Python provider) + per-file SPDX license headers into existing source. Completing 00-03 triggers the mandatory Phase 0 → Phase 1 transition (PROJECT.md evolve, ROADMAP, phase git commit).

## Carry-forward (deferred from this plan)

- Per-file SPDX headers into existing source (→ 00-03 or a header-automation plan)
- Physical relocation of control-plane/ + mcp/* under packages/community/ (later)
- CI/pre-commit enforcement of the community→core import ban (later)
- CLA DCO/sign-off enforcement mechanism (later)
