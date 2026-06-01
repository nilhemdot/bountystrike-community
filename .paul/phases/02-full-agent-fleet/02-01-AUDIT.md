# Enterprise Plan Audit Report

**Plan:** .paul/phases/02-full-agent-fleet/02-01-PLAN.md
**Audited:** 2026-05-31
**Verdict:** Conditionally acceptable (was NOT-acceptable as written)

---

## 1. Executive Verdict
Conditionally acceptable after applied fixes. As originally written it was NOT
acceptable: the pre-oracle dedup gate used a **parameter-blind** fingerprint that would
silently bury distinct real bugs (moat inversion), and the dedup adapter would open a
**second asyncpg pool per finding** (connection exhaustion). Both are release-blocking
and now fixed. Would sign off for APPLY with the 3 must-haves applied.

## 2. What Is Solid (do not change)
- Register-on-validated-only semantics: dedup_fingerprints holds only validated
  canonicals, so a 'duplicate' park provably means "matches a prior VALIDATED finding."
  Defensible, correct — keep.
- Reuse of CLAIM optimistic lock for idempotency: a re-trigger on a duplicate/validated
  row matches 0 rows → noop. No double-processing. Keep.
- Meeting the gate by tuning the FIXTURE, never the production thresholds. Keep.
- Honoring 01-06 ordering (only ADD hooks) + transient-release retry contract. Keep.

## 3. Enterprise Gaps Identified
- A: exact fingerprint keys on platform/program/vuln_type/host/path — **parameter-blind**.
  Two bugs, same endpoint, different vulnerable params → 2nd parked duplicate → real bug
  buried, never validated/submitted. Inverts the core moat.
- G: `DedupStore.create(dsn)` opens its own pool; called per finding = pool-per-call
  resource leak. Must reuse verify_service's existing pool via `DedupStore(pool)`.
- D: embedding text source left "raw_finding OR compose" = non-deterministic; two runs
  could embed different text → incomparable vectors, silent semantic-dedup drift.
- E: no audit trail for a duplicate decision — which canonical finding did it match?
  Fails post-incident reconstruction.
- F: precision-empty-predicted=1.0 convention lets a trivial predict-none/predict-all
  predictor pass half the gate; needs a non-degenerate guard.
- I: register does two writes (fpr + embedding); order + partial-success semantics
  unspecified.

## 4. Upgrades Applied to Plan

### Must-Have (release-blocking)
| # | Finding | Section | Change |
|---|---------|---------|--------|
| A | Parameter-blind fingerprint buries distinct bugs | AC-6 (new) + T2 | dedup identity MUST include `parameter`; check+register use identical key (fold param into `path`); only full-identity match parks duplicate |
| G | Per-finding second asyncpg pool | T2 | dedup_gate reuses verify_service pool via `DedupStore(pool)`; never `DedupStore.create` |
| D | Non-deterministic embedding text source | AC-7 (new) + T2 | pin a FIXED source (raw_finding w/ defined order, else fixed `cwe\nurl\nparameter`); same builder at register + query |

### Strongly Recommended
| # | Finding | Section | Change |
|---|---------|---------|--------|
| E | No reconstructable dup decision | AC-7 + T2 pre-oracle hook | emit structured `verify.duplicate {finding_id, canonical_finding_id, fingerprint}`; check returns canonical id |
| I | Two-write register ordering | T2 | register exact fpr FIRST (moat layer), embedding SECOND; partial-success logged, never raised |
| F | Gate gameable by degenerate predictor | T1 | assert predicted_pairs non-empty AND not-all-pairs in the gate test |

### Deferred (can safely defer)
| # | Finding | Rationale |
|---|---------|-----------|
| H | Live worker verify+dedup smoke | Already a documented deploy gate (posture as 01-06/01-09); unit-verified now |
| — | L2 semantic auto-park / L3 pre-submission cross-check | Explicitly scoped to 02-04 / 02-03 |

## 5. Audit & Compliance Readiness
With E applied, every duplicate park is reconstructable (finding_id + canonical +
fingerprint). Register-on-validated-only keeps the dedup ledger trustworthy. Failures
are loud (transient → release+reraise; post-validate register → WARNING, no silent
revert). Remaining audit gap is live-path proof, accepted as a deploy gate. No
schema/audit-log change needed (status ENUM already has 'duplicate'; log-only trail).

## 6. Final Release Bar
Must be true before ship: (A) param in dedup identity, (G) shared pool, (D) deterministic
embedding source — all applied. Residual risk if shipped as-is: live worker path
unproven (deploy-gate, mirrors Phase 1). Signable for APPLY.

---

**Summary:** Applied 3 must-have + 3 strongly-recommended upgrades. Deferred 1 (+2 scoped-out).
**Plan status:** Updated and ready for APPLY.

---
*Audit performed by PAUL Enterprise Audit Workflow — template v1.0*
