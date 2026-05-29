# Enterprise Plan Audit Report

**Plan:** .paul/phases/01-community-edition-mvp/01-03-PLAN.md
**Audited:** 2026-05-29
**Verdict:** Conditionally acceptable (was not-acceptable as written — AC-1c/M1 would have failed the plan's own verification)

---

## 1. Executive Verdict

Conditionally acceptable after applied fixes. As originally written the plan contained a
release-blocking factual error (genesis chain link) and an unsound verification strategy
(moto cannot reproduce the very R2 behavior trap #5 guards against). With the 3 must-have +
3 strongly-recommended upgrades applied, I would approve for APPLY. The underlying
architecture is sound because most of `evidence_management` already exists and verified.

## 2. What Is Solid

- **Reuse over rebuild.** Plan correctly consumes existing R2BlobStore, make_blob_store,
  HashChainService, and the realigned audit_log table rather than reimplementing — and locks
  schema + chain algorithm as DO-NOT-CHANGE. Correct boundary.
- **Single-transaction atomicity** for artifact-row + advisory-locked audit append. Right call.
- **evidence-mcp ↔ control-plane divergence explicitly deferred**, not silently ignored.
- **Trap #5 named** (boto3≥1.36 checksum) — the right risk was identified up front.

## 3. Enterprise Gaps Identified

1. **Genesis chain link wrong (release-blocking).** AC claimed genesis prev_hash = 32 zero
   bytes; migration 03 + HashChainService use empty/0-byte (b""). Plan would fail its own
   chain-verify AC and a SQL-only auditor export would mismatch.
2. **Verification unsound for trap #5 (release-blocking).** moto does not reproduce R2's CRC
   header rejection, so a passing moto round-trip is NOT proof the checksum config is correct.
3. **Idempotency incomplete (release-blocking).** Re-record skipped duplicate artifact rows
   but would still append a second audit entry — a crashed/replayed Hatchet task could pad or
   fork the tamper-evident chain. Idempotency must cover the audit append.
4. **Provenance unbound.** scope_token_jti passed but not required/validated — weakens
   post-incident reconstruction ("which scope authorized this evidence?").
5. **Failure ordering unstated.** Blob-vs-DB-commit ordering and orphan-blob semantics undefined.
6. **No payload size bound.** Oversized raw_bytes fails mid-PUT / exceeds Hatchet gRPC limit.

## 4. Upgrades Applied to Plan

### Must-Have (Release-Blocking)

| # | Finding | Plan Section Modified | Change Applied |
|---|---------|----------------------|----------------|
| M1 | Genesis prev_hash = b"" not 32 zero bytes | AC-1b, Task 1 action, Task 3 action, Verification | Corrected to 0-byte genesis per migration 03 |
| M2 | moto can't prove trap-#5 fix | AC-1, Task 1, Verification | AC now asserts Config values by introspection; moto = byte-fidelity only |
| M3 | Idempotent re-record must not extend audit chain | AC-1c, Task 1 action, Task 3 action | Audit append only on NEW row insert; re-record returns existing chain_hash |

### Strongly Recommended

| # | Finding | Plan Section Modified | Change Applied |
|---|---------|----------------------|----------------|
| S1 | scope_token_jti provenance | AC-1d, Task 1 action | Required non-empty at input boundary |
| S2 | Blob-before-commit + orphan semantics | AC-1d, Task 1 action | PUT before txn commit; raise on txn fail; orphan blob acceptable (content-addressed) |
| S3 | Payload size cap | AC-1d, Task 1 action | Reject raw_bytes over documented cap (Hatchet gRPC ~4 MiB) at boundary |

### Deferred (Can Safely Defer)

| # | Finding | Rationale for Deferral |
|---|---------|----------------------|
| D1 | Gate recording on oracle_verdict="validated" | Recording attempts (incl. non-validated) is a legitimate audit trail; submission gating lives in reporter/approval tiers, not the store |
| D2 | Pooled aioboto3 client | Phase 2 optimization; existing code comment already notes one-PUT-per-finding is fine for Phase 1 |

## 5. Audit & Compliance Readiness

After fixes: chain is genuinely tamper-evident (correct genesis + no replay padding), evidence
is bound to its authorizing scope JWT (jti), and failures raise rather than silently report
success. Defensible for SOC 2 evidence-integrity controls. Residual: real-R2 checksum behavior
is asserted by config, not by a live R2 bucket — flagged as a deployment-time smoke (r2_smoke.py).

## 6. Final Release Bar

Before ship: AC-1 config-introspection test green; chain verify with b"" genesis green; idempotent
re-record proves no second audit entry; live Hatchet trigger SUCCEEDED. Remaining risk if shipped
as-is: real Cloudflare R2 CRC behavior unverified without a live bucket (mitigated by config
assertion + deployment smoke). I would sign off on APPLY with these conditions encoded.

---

**Summary:** Applied 3 must-have + 3 strongly-recommended upgrades. Deferred 2.
**Plan status:** Updated and ready for APPLY.

---
*Audit performed by PAUL Enterprise Audit Workflow*
*Audit template version: 1.0*
