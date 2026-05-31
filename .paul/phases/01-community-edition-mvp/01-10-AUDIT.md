# Enterprise Plan Audit Report

**Plan:** .paul/phases/01-community-edition-mvp/01-10-PLAN.md
**Audited:** 2026-05-31
**Verdict:** Conditionally acceptable → upgraded to enterprise-ready after applied fixes

---

## 1. Executive Verdict

Conditionally acceptable as originally written; **enterprise-ready** after the must-have
fixes below were applied. The plan correctly treats public exposure as the irreversible,
outward-facing act it is and gates it behind a human checkpoint — that instinct is right.
But the original secret gate relied on a **human reading a string** ("SECRET-SCAN: CLEAN")
rather than a machine exit code, and the release mechanics had **no tag-collision preflight
and no partial-push recovery** — both of which can silently half-publish or force-overwrite
a published tag. With those closed, I would sign my name to this release.

## 2. What Is Solid (Do Not Change)

- **Human-action checkpoint on the public push (T3, blocking).** Correct — the agent must
  not pick the target repo or flip visibility. Authorization boundary is in the right place.
- **No-push-to-origin / no-auto-history-rewrite boundaries.** Explicit, correct, and match
  the M1/M3 invariants. A leak halting for operator-approved scrub (not auto-filter-repo) is
  the right default — automatic history rewrite is itself a hazard.
- **Tree AND history scan (not just tree).** Many release checklists scan only the working
  tree; scanning history reachable from the release ref is the audit-grade choice.
- **SUMMARY-backed CHANGELOG ("do NOT invent features").** Prevents fabricated release notes.

## 3. Enterprise Gaps Identified

1. **Verdict was a human-read string, not a machine gate.** "prints SECRET-SCAN: CLEAN" is
   eyeball-verified; nothing mechanically blocked T3 on a leak. A tired operator can push past it.
2. **Ad-hoc grep needles only; no deterministic scanner.** AKIA-only AWS match, no generic
   high-entropy / GCP service-account / npmrc coverage. Method also unrecorded for audit.
3. **Tag-collision unhandled.** `git tag -a v0.1.0` with no preflight; a pre-existing tag
   invites a `-f` force-overwrite of an already-published ref.
4. **Partial-push not handled.** Commit+tag push succeeds, `gh release create` fails → silent
   half-published state with no recovery contract.
5. **License filename assumed.** verify hard-codes `LICENSE-AGPL`, but the context block names
   `LICENSE` + `LICENSES.md` and boundaries name `LICENSE-AGPL`/`LICENSE-APACHE`. An assumed
   name fails the gate on a naming mismatch, not a real problem.
6. **.env.example not scanned.** Tracked and modified this cycle; could carry a real webhook/token.
7. **No release audit evidence.** No recorded commit SHA / tag SHA / approver / scan method —
   post-incident reconstruction ("what exactly went public, approved by whom, scanned how?") fails.
8. **No final payload review at the checkpoint.** Operator confirms a *slug* but never sees the
   actual commit list / file manifest going public.

## 4. Upgrades Applied to Plan

### Must-Have (Release-Blocking)

| # | Finding | Plan Section Modified | Change Applied |
|---|---------|----------------------|----------------|
| 1 | Human-string verdict, not machine gate | AC-2, Task 2 action(5)/verify | Scan MUST exit non-zero on leak; T3 mechanically reads exit code |
| 2 | No tag-collision preflight | AC-4, Task 3 step 2 | `git tag -l` + `git ls-remote` preflight; never `-f`/`--force` a published tag |
| 3 | Partial-push silent half-state | AC-4, Task 3 | Retry release-only on `gh release` failure; record half-state + recovery |
| 4 | No operator payload review | Task 3 step 1b | Operator reviews `git log --oneline` + manifest count + gate exit before approve |

### Strongly Recommended

| # | Finding | Plan Section Modified | Change Applied |
|---|---------|----------------------|----------------|
| 5 | License filename assumed | AC-2, Task 2 action(3)/verify | Resolve real names via `git ls-files \| grep -i licen`; assert LICENSES.md |
| 6 | .env.example unscanned | AC-2, Task 2 action(4)/verify | Grep .env.example for real-secret needles; abort like a leak on hit |
| 7 | No release audit evidence | AC-4, Task 3, verification | SUMMARY records commit SHA, tag SHA, slug, scan method, approval timestamp |
| 8 | Scanner non-determinism | Task 2 action(5) | Prefer gitleaks if installed; else bounded git-grep recorded as "grep-needle fallback" |

### Deferred (Can Safely Defer)

| # | Finding | Rationale for Deferral |
|---|---------|----------------------|
| D1 | GPG-signed tag/commit provenance | Adds operator keyring setup; not blocking for a v0.1.0 OSS cut. Add when distributing release binaries. |
| D2 | CHANGELOG compare-URL backlinks | Need the public slug, unknown until checkpoint; fill post-push. |
| D3 | Full SBOM (CycloneDX/SPDX) | LICENSES.md presence asserted now; machine-readable SBOM is a Phase-2 supply-chain item. |

## 5. Audit & Compliance Readiness

After fixes: the release produces **defensible evidence** (commit/tag SHA, approver, timestamp,
scan method in SUMMARY), **prevents silent failure** (non-zero machine gate + partial-push
recovery note), and **supports reconstruction** (operator reviewed the exact manifest; method
recorded). Ownership is explicit — the human checkpoint names the accountable operator for the
irreversible push. Remaining audit weakness is provenance (unsigned tags, D1) — acceptable and
documented for v0.1.0.

## 6. Final Release Bar

Must be true before ship: AC-2 gate exits 0 (tree+history+`.env.example` clean), real license
files resolved, tag-collision preflight clean, operator reviewed the payload and confirmed a
public slug. Remaining risk if shipped as-is: no cryptographic tag provenance (D1) — a consumer
cannot verify the tag author. Acceptable for an AGPLv3 source cut. **Would sign.**

---

**Summary:** Applied 4 must-have + 4 strongly-recommended upgrades. Deferred 3 items.
**Plan status:** Updated and ready for APPLY.

---
*Audit performed by PAUL Enterprise Audit Workflow*
*Audit template version: 1.0*
