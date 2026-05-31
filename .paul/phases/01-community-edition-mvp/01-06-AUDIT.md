# Enterprise Plan Audit Report

**Plan:** .paul/phases/01-community-edition-mvp/01-06-PLAN.md
**Audited:** 2026-05-31
**Verdict:** Conditionally acceptable (was *not acceptable* as written — would strand findings and wrongly reject real bugs)

---

## 1. Executive Verdict

The plan's architecture is correct and its core invariant (no `validated` without an
`evidence_artifacts` row, enforced by ordering) is sound. But **as written it would not
ship**: it had two release-blocking failure modes and three strongly-recommended gaps,
all in the verdict-handling path — the single most important code path in Phase 1.

Every external contract the plan asserts was verified against live source and **holds**:
oracle signatures `(url, param[, target])`, `EvidenceRecordingService.record()` kwargs and
its `{...content_hash_hex...}` return, the `finding_status` enum
(`hypothesis`/`validation_pending`/`validated`/`rejected` all present), `scan_jobs.scope_jwt_jti`,
the `Verdict` literal set, and all `findings` columns. The plan does not invent anything.

The defects were **state-machine and error-handling omissions**, not contract errors:
a claimed-then-crashed finding stranded forever; a real bug terminally rejected over a
missing provenance token. Both are now fixed in-plan. With the applied upgrades I would
approve this for APPLY.

## 2. What Is Solid (Do Not Change)

- **Moat-by-ordering.** `status='validated'` set only on the path that already obtained a
  `content_hash_hex` from `record()`. Correct, and the strongest part of the plan.
- **Optimistic single-statement CLAIM** (`UPDATE ... WHERE status='hypothesis' RETURNING`).
  Atomic; correctly serializes two concurrent workers (loser sees 0 rows → noop). AC-5.
- **In-process oracle import** over an MCP stdio client. Removes a JSON-RPC failure surface
  and the stdout-corruption trap (#13); oracles are stateless, no DB coupling.
- **No schema migration.** Verified: `findings` already has `status`/`evidence_hash`/
  `oracle_method`; `evidence_artifacts` exists. Adding a migration would have been wrong.
- **Reuse of the 01-03 evidence service** rather than reimplementing hashing/chaining.
- **Boundaries** correctly fence off oracle source, schema, and the evidence domain.

## 3. Enterprise Gaps Identified

1. **Silent stranding on oracle exception (release-blocking).** The CLAIM moves the row to
   `validation_pending` *before* the oracle runs. The oracle can raise for entirely transient
   reasons (Interactsh down, `chromium` not installed on the worker, target unreachable,
   scipy edge). A bare propagation → Hatchet retries → the retry's CLAIM matches 0 rows
   (already `validation_pending`) → `noop_unclaimed` → the finding is stuck **forever**, with
   no log, no rejection, no re-attempt. This is precisely the silent failure an audit exists
   to catch.
2. **`scope_token_jti` decision punted to apply + a wrong default (release-blocking).**
   `findings.job_id` is nullable (`ON DELETE SET NULL`) and `scan_jobs.scope_jwt_jti` is
   nullable; `EvidenceRecordingService` validates the jti **non-empty** (01-03 audit), so an
   empty jti raises `ValidationError` *before* the PUT. The plan said "DOCUMENT the chosen
   path at apply; prefer require non-empty, else `status='rejected'`." Rejecting here would
   **terminally bury a real, oracle-confirmed vulnerability** over a provenance gap and
   corrupt the confirmed-rate SLO. Provenance failure ≠ vulnerability-false. An
   underspecified, deferred decision on the centerpiece path is itself a risk.
3. **No null url/parameter guard.** Oracles require a non-empty `param: str`; both columns are
   nullable. `oracle_xss(url=None, param=None)` crashes → same crash-strand as (1).
4. **Unsafe evidence serialization.** `json.dumps(result.model_dump())` raises on non-JSON
   types in the free-form `OracleResult.evidence` dict → crash-strand.
5. **CWE-94/CWE-74 → SSTI wrongful reject.** Routing generic code/injection CWEs to the SSTI
   oracle yields `unreproducible` → `rejected`, terminally burying a real injection bug the
   SSTI probe structurally cannot validate (the RCE oracle that *could* is out of scope here).
6. **`validation_pending` semantic overload** (cosmetic once 1–5 land): used as both
   "claimed, in flight" and "claimed, parked." Disambiguated by an explicit state-semantics
   note in `<boundaries>`.

## 4. Upgrades Applied to Plan

### Must-Have (Release-Blocking)

| # | Finding | Plan Section Modified | Change Applied |
|---|---------|----------------------|----------------|
| M1 | Oracle exception strands finding in `validation_pending` (silent failure) | AC (new AC-9), Task 1 step c, Verification, Boundaries | Oracle call wrapped in try/except; on exception reset `status='hypothesis'` (release claim) + `verify.oracle_error` warning, then re-raise for clean Hatchet retry. New AC-9 + test `test_oracle_error_releases_claim`. |
| M2 | `scope_token_jti` punted to apply; "reject if empty" would bury a real bug + crash on empty | AC (new AC-10), Task 1 step d, Verification, Boundaries | Deterministic now: missing/empty jti → do NOT call `record()`, leave `validation_pending` (parked) + `verify.missing_scope_jti` warning, return `blocked_missing_scope_jti`. Never `rejected`. New AC-10 + test. |

### Strongly Recommended

| # | Finding | Plan Section Modified | Change Applied |
|---|---------|----------------------|----------------|
| S1 | Null url/parameter crashes the oracle (required `param: str`) | AC (new AC-11), Task 1 step c0, Task 3, Verification | Input guard before dispatch: missing url/parameter → parked `validation_pending` + `verify.missing_oracle_input`, return `missing_input`. New AC-11 + test. |
| S2 | `json.dumps(model_dump())` raises on non-JSON `evidence` values | Task 1 step d | Switched to `result.model_dump_json().encode()` (pydantic-native, deterministic, type-safe). |
| S3 | CWE-94/CWE-74 → SSTI oracle → `rejected` buries a real injection bug | AC-3, Task 3 dispatch test, Verification | Narrowed SSTI mapping to CWE-1336 + bare `ssti`/`ssti-candidate` token; CWE-94/CWE-74 resolve to None → `validation_pending` (preserved for the Phase-2 RCE path), never auto-rejected. Test asserts `None`. |

### Deferred (Can Safely Defer)

| # | Finding | Rationale for Deferral |
|---|---------|------------------------|
| D1 | Dedicated terminal error state after N exhausted Hatchet retries | M1 leaves the finding re-pollable in `hypothesis`; Hatchet's bounded retry policy + a parked state are acceptable for Phase 1. Distinct exhaustion state is an observability concern → Phase 2. |
| D2 | Metrics/Langfuse on verify outcomes (validated/rejected/parked counts) | Observability instrumentation is Phase 2/3 (same posture as 01-05 deferral). |
| D3 | Full `validation_pending` sub-state disambiguation (distinct enum values per parked reason) | Resolved sufficiently by the structured warning per cause + the boundaries state-semantics note; distinct enum values are a schema change, out of scope (no-migration plan). |

## 5. Audit & Compliance Readiness

- **Defensible evidence:** unchanged and strong — every `validated` finding is backed by a
  content-addressed `evidence_artifacts` row + hash-chain entry (01-03). Moat intact.
- **Silent-failure prevention:** the central gap before this audit. Now every non-completing
  path emits a structured warning (`verify.oracle_error` / `verify.missing_scope_jti` /
  `verify.missing_oracle_input` / `verify.unsupported_cwe`) and lands in a recoverable state.
  No path fails silently.
- **Post-incident reconstruction:** the FSM is now honest — `rejected` means "an oracle ran
  and said not-real," never "we couldn't check." An auditor reading a `rejected` row can trust
  it reflects a real verdict, not an infrastructure hiccup or a missing token.
- **Ownership/accountability:** the verify-finding task is the single, durable, triggerable
  owner of the hypothesis→validated/rejected transition. Clear.

A pre-audit version would have failed a real review on (1) stranded findings indistinguishable
from "still processing," and (2) real vulnerabilities recorded as `rejected`. Both are closed.

## 6. Final Release Bar

**Must be true before this ships (now encoded in the plan):**
- Oracle invocation is exception-wrapped; transient errors release the claim and retry cleanly (AC-9).
- A `validated` verdict with no scope JTI parks (never rejects, never crashes) (AC-10).
- Null url/parameter never reaches an oracle (AC-11).
- `rejected` is reserved exclusively for a real non-validated oracle verdict.
- Unit tests prove all five branches (validated, rejected, parked×3) + the moat invariant.

**Residual risk if shipped as-is (accepted):** a persistently-failing oracle (e.g. worker
missing `chromium`) will retry-loop within Hatchet's bounds then rest re-pollable in
`hypothesis` — visible via the warning log, no terminal alarm until D1/D2 land. Acceptable
for a self-hosted Community Edition; flag `playwright install chromium` for the 01-08 installer.

**Would I sign my name to this system?** With the applied upgrades — yes, for APPLY.

---

**Summary:** Applied 2 must-have + 3 strongly-recommended upgrades. Deferred 3 items.
**Plan status:** Updated and ready for APPLY.

---
*Audit performed by PAUL Enterprise Audit Workflow*
*Audit template version: 1.0*
