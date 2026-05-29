# Enterprise Plan Audit Report

**Plan:** `.paul/phases/00-truth-in-claims-foundation/00-04-PLAN.md`
**Audited:** 2026-05-29
**Verdict:** conditionally acceptable (now enterprise-ready after auto-applied fixes)

---

## 1. Executive Verdict

As submitted, the plan was **not acceptable for production** — it carried two release-blocking
license-compliance defects and one unsound enforcement test that would have given false CI
assurance. The architecture (allow-list-by-root SPDX sweep + import-linter forbidden contract +
blocking CI) is correct; the *specification* leaked in ways that would mis-license foreign code and
ship a green-but-meaningless import ban.

With the must-have and strongly-recommended findings auto-applied, I would **conditionally sign off**:
the plan now closes the foreign/generated-code stamping holes, proves idempotency by byte-equality,
preserves shebangs, relocates the canary into a scanned module with guaranteed cleanup, pins the tool,
and asserts the contract is non-vacuous. The remaining residual is execution-time discipline, not
design (see §6).

This is licensing + supply-chain work; "looks done" is not "is correct." The original draft would have
passed its own `--check` while AGPL-stamping `.venv/` site-packages.

## 2. What Is Solid

- **Per-root SPDX map is correct and matches LICENSES.md exactly.** Apache-2.0 for `packages/core`,
  `AGPL-3.0-or-later` (NOT `AGPL-3.0-only`) for community/control-plane/mcp/scripts, and a valid
  `LicenseRef-BountyStrike-Proprietary` for enterprise. The `-or-later` choice is consistent with the
  verbatim AGPL §13 text shipped in 00-02. No collision between the Apache core path and the AGPL
  community paths in the routing table. This is the single most important thing to get right and it is right.
- **Idempotency guard by SPDX-presence check** is the correct mechanism (not a marker comment).
- **Forbidden-contract type** (`forbidden` + `source_modules`/`forbidden_modules`) is the right
  import-linter primitive for a one-directional ban; `include_external_packages` is appropriate since
  `bountystrike_enterprise` is not a first-party importable module yet.
- **Blocking CI on push + PR** with two independent fail-fast gates is the right enforcement shape.
- **Correctly scoped down:** no physical relocation, no logic changes, no STATE write (UNIFY's job —
  correctly excised). The plan resists scope creep.

## 3. Enterprise Gaps Identified

1. **[BLOCKER] Foreign + generated code would be stamped.** Skip-list omitted `.venv/`/`site-packages/`
   (3rd-party Apache/MIT/BSD code) and `dist/`/`*.d.ts` (compiled output in `mcp/scope-mcp/dist/`).
   Default `--root` = git root → the walk descends into `.venv/`, `infra/`, `.claude/hooks/*.sh`,
   `.gemini/`. AGPL-stamping foreign code is illegal relicensing — a legal defect, not a lint nit.
   (Ground truth confirmed: `.venv/.../structlog/*.py`, `mcp/scope-mcp/dist/*.d.ts`, `infra/sql/*.sql`,
   16 `.claude/hooks/*.sh` all exist and were in scope.)
2. **[BLOCKER] Unsound negative test.** Canary was placed in `packages/community/`, but the contract's
   `source_modules = ["control_plane"]` only analyzes the `control_plane` import graph. A canary outside
   every source_module means the contract **passes with the forbidden import present** — the negative
   test proves nothing and AC-5 is a false green.
3. **[BLOCKER] Shebang destruction.** Task-1 step 6 said "prepend ... as the very first line." 20+ files
   (`scripts/*.py`, `scripts/*.sh`) have `#!` on line 1. Inserting SPDX as line 1 breaks every executable.
   No coding-cookie handling either.
4. **Vacuous-pass risk.** Plan's own note accepted "passes vacuously if not installed." `control_plane`
   lives at `control-plane/src/control_plane`; if `uv sync` doesn't install the workspace member,
   import-linter analyzes 0 modules and AC-6 passes for the wrong reason — no enforcement, but green CI.
5. **Idempotency asserted, not proven.** AC-2 verify relied on `--check` exit 0, which proves header
   *presence*, not duplicate-prevention on a second *apply*. No byte-equality check.
6. **Floating tool version.** `import-linter = ">=2.1"` is non-deterministic CI (violates CLAUDE.md
   supply-chain trap #6). Also targeted `[tool.uv.dev-dependencies]`, but the root uses PEP 735
   `[dependency-groups] dev`.
7. **Canary cleanup not guaranteed.** `rm` ran as a plain post-step; an abort between create and rm
   would commit the canary (with an AGPL header, since it'd survive the sweep).
8. **No `continue-on-error` / PR-trigger assertion** in CI verify — a non-blocking gate would look green.

## 4. Upgrades Applied to Plan

### Must-Have (Release-Blocking)

| # | Finding | Plan Section Modified | Change Applied |
|---|---------|----------------------|----------------|
| 1 | Foreign/generated code stamping (`.venv`, `dist`, `infra`, `.claude`, `.gemini`) | AC-1/AC-1a, AC-3 skip-list, AC-3a, Task-1 step 5, boundaries | Added explicit six-root ALLOW-LIST as primary gate; added `.venv`/`site-packages`/`dist`/`build`/`*.d.ts`/`*.min.`/`infra`/`.claude`/`.gemini` to deny skip-list; new AC-1a + AC-3a; hard boundaries forbidding foreign-root stamping |
| 2 | Unsound negative test (canary in wrong module) | AC-5b, Task-4 (file + action) | Relocated canary to `control-plane/src/control_plane/_import_ban_canary_DELETE_ME.py` (a scanned source_module); new AC-5b |
| 3 | Shebang/coding-cookie destruction | AC-2a, Task-1 step 6, verify | Insertion-index rule: SPDX after `#!` and after PEP 263 cookie, never line 1; per-file shebang-survival assertions in Task-1/Task-2 verify |
| 4 | Vacuous import-ban pass | AC-5a, Task-3 action+verify, CI step | Added `import control_plane` resolution assertion + analyzed-module-count grep; new CI step `Verify import-linter root package resolves` |
| 5 | Canary cleanup not guaranteed | Task-4 action | Wrapped negative test in EXIT `trap cleanup`; post-test `git status --porcelain` assertion proving no committed canary |

### Strongly Recommended

| # | Finding | Plan Section Modified | Change Applied |
|---|---------|----------------------|----------------|
| 1 | Idempotency proven by byte-equality | AC-2, Task-2 verify | Second-apply run asserting "0 files updated" AND zero additional `git diff` |
| 2 | Pin import-linter; correct dep-group | Task-3 toml block, frontmatter | `import-linter~=2.3` in `[dependency-groups] dev` (PEP 735), not floating `>=`, not `[tool.uv.dev-dependencies]` |
| 3 | Pin CI uv; assert blocking gates + PR trigger | Task-5 workflow + verify | `setup-uv` version pin; verify greps for absence of `continue-on-error` and presence of `pull_request` |
| 4 | scope-mcp src vs dist handling | AC-3a | New AC: `src/`+`test/` `.ts` stamped `//`, `dist/` untouched |
| 5 | Doc coverage for new failure modes | Task-6 action + verify | Added shebang-ordering, allow-list-vs-deny, non-vacuous, canary-location/trap topics; doc content-check now requires `shebang`, `allow-list`, `control_plane` |
| 6 | Verification + boundaries hardening | verification checklist, boundaries | New checklist items for foreign-code exclusion, shebang survival, non-vacuous, canary residue, pinning, blocking gates |

### Deferred (Can Safely Defer)

| # | Finding | Rationale for Deferral |
|---|---------|----------------------|
| 1 | Cross-server import ban (mcp/* → enterprise) | Each mcp server is a separate pyproject; the plan explicitly scopes the contract to `control_plane` and defers cross-server bans to Phase 1 physical relocation. Correct boundary; not a Phase-0 defect. |
| 2 | REUSE/license-header tool (e.g. `reuse lint`) instead of a hand-rolled script | REUSE is not installed (per task brief); the bespoke idempotent script is acceptable for this scope. Adopting REUSE is a Phase-1+ tooling upgrade, not release-blocking. |
| 3 | SPDX file-level `Copyright` line in addition to the identifier | SPDX-License-Identifier alone is sufficient for machine-verifiable license routing; copyright attribution is a polish item, deferrable. |
| 4 | Pre-commit hook mirroring the CI check (local fast-fail) | CI is the authoritative gate; a local pre-commit mirror is a developer-experience nicety, deferrable. |

## 5. Audit & Compliance Readiness

- **Defensible evidence:** After fixes, CI produces a per-PR pass/fail artifact for both license-header
  presence and the import boundary. The `--check` mode is the same code path as apply, so the gate
  cannot drift from the sweep. An auditor can reconstruct that every shipped source file carried the
  correct tier identifier at merge time.
- **Silent-failure prevention:** The pre-fix plan had two silent-failure surfaces (vacuous import pass,
  unsound canary). Both are now closed by explicit non-vacuous assertions and canary relocation, so a
  green CI now *means* the boundary is enforced.
- **Post-incident reconstruction:** SPDX identifiers are in-file and machine-grepable; the import graph
  is contract-checked. A future relicensing dispute can be reconstructed from git history + headers.
- **Ownership:** The plan correctly delegates STATE/transition to UNIFY. No accountability gap there.
- **Would have failed a real audit pre-fix:** stamping `.venv/` Apache code as AGPL is exactly the kind
  of finding a legal/OSS-compliance review (e.g. ScanCode/FOSSA) flags as a P1. Now excluded.

## 6. Final Release Bar

**Must be true before this ships (now encoded in the plan):**
- Sweep touches ONLY the six licensed roots; `.venv/`, `dist/`, `infra/`, `.claude/`, `.gemini/` provably
  untouched.
- Idempotent by byte-equality on a second apply (not just `--check`).
- Shebangs/cookies preserved on every executable script.
- `control_plane` resolves so the import ban is non-vacuous; canary lives in a scanned module and is
  trap-removed (no committed canary).
- `import-linter` pinned; CI gates blocking and PR-triggered.

**Residual risk if shipped as-is (single biggest):** the sweep's correctness now hinges entirely on the
**implementer faithfully encoding the six-root allow-list** rather than reverting to a convenient
git-root walk during APPLY. If the script regresses to "walk everything + skip-list," the deny-list is a
weaker second line and any path the implementer forgets (a future `vendor/` dir, a new infra subtree)
silently gets AGPL-stamped. The plan now mandates the allow-list as the primary gate and adds a
foreign-path scan to the verify, but this is a discipline guarantee, not a structural one — APPLY must run
the `git diff --name-only | grep -E '\.venv/|/infra/|dist/'` assertion and treat a hit as release-blocking.

**Sign-off:** I would sign my name to this plan *after* the auto-applied fixes, contingent on the APPLY
phase running the new foreign-path, shebang-survival, byte-equality, and non-vacuous verification gates
and treating any failure as red. Do not skip the verify steps to save time — they are the only thing
standing between this and a license-compliance defect.

---

**Summary:** Applied 5 must-have + 6 strongly-recommended upgrades. Deferred 4 items.
**Plan status:** Updated and ready for APPLY (autonomous; no new checkpoints required).

---
*Audit performed by PAUL Enterprise Audit Workflow*
*Audit template version: 1.0*
