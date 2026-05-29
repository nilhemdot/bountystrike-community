---
phase: 01-community-edition-mvp
plan: 03
subsystem: evidence_management
tags: [r2, boto3, aioboto3, checksum, asyncpg, hatchet, hash-chain, audit-log, moto]

requires:
  - phase: 01-01
    provides: evidence_artifacts + audit_log (realigned, migration 03) tables; pg17 image
  - phase: 01-02
    provides: Hatchet v1 runtime; @hatchet.task pattern; worker.py + orchestrator trigger seam
provides:
  - R2BlobStore checksum-safe under boto3>=1.36 (trap #5 fixed via botocore Config)
  - EvidenceRecordingService.record() — atomic, idempotent blob->row->hash-chained audit
  - Hatchet record-evidence task + orchestrator trigger-record-evidence subcommand
affects: [01-04 validator wiring, reporter submission, any evidence-producing agent]

tech-stack:
  added: ["moto[server]>=5.0 (dev/test)"]
  patterns:
    - "Idempotency via per-finding pg_advisory_xact_lock SELECT-guard (no UNIQUE constraint needed)"
    - "Blob PUT before DB commit; orphan blob acceptable (content-addressed)"
    - "Service self-registers jsonb codec on acquired conn"

key-files:
  created:
    - control-plane/src/control_plane/domains/evidence_management/services/evidence_recording_service.py
    - control-plane/tests/test_evidence_recording.py
  modified:
    - control-plane/src/control_plane/domains/evidence_management/repositories/blob_store.py
    - control-plane/src/control_plane/domains/evidence_management/services/__init__.py
    - control-plane/src/control_plane/workflows/tasks.py
    - control-plane/src/control_plane/workflows/worker.py
    - scripts/orchestrator.py
    - control-plane/pyproject.toml

key-decisions:
  - "ON CONFLICT impossible (no UNIQUE on content_hash, schema locked) -> advisory-lock SELECT-guard keyed (finding_id, content_hash)"
  - "moto mock_aws unreliable with aiobotocore -> ThreadedMotoServer (real HTTP)"
  - "Live trigger ran EVIDENCE_BACKEND=local (no R2 creds); R2 path covered by moto"

patterns-established:
  - "Per-finding advisory lock serializes SELECT-guard + INSERT + audit append in one txn"
  - "Audit append only on NEW artifact insert — re-record never extends the chain"

duration: ~75min
started: 2026-05-29T04:45:00Z
completed: 2026-05-29T05:05:00Z
---

# Phase 1 Plan 03: Evidence store / R2 write path Summary

**Evidence write path is now R2-checksum-safe, atomic+idempotent, and durably Hatchet-driven: one `record()` call PUTs the blob, inserts the `evidence_artifacts` row, and appends a hash-chained `audit_log` entry — verified live end-to-end.**

## Acceptance Criteria Results

| Criterion | Status | Notes |
|-----------|--------|-------|
| AC-1: R2 client survives boto3>=1.36 checksum break | Pass | `_CHECKSUM_CONFIG` introspection asserts `when_required` ×2; moto byte-fidelity round-trip via ThreadedMotoServer |
| AC-1b: genesis prev_hash = b"" (not 32 zero bytes) | Pass | Live audit row: `prev_hash == b''` |
| AC-1c: re-record idempotent across blob AND audit | Pass | 2nd byte-identical record → same artifact_id, artifact_rows=1, audit_rows=1 |
| AC-1d: provenance + ordering + size cap | Pass | jti non-empty / bad-uuid / >4MiB rejected at boundary; PUT before commit |
| AC-2: atomic + idempotent record | Pass | integration test green on live PG |
| AC-3: durable Hatchet task triggerable via orchestrator | Pass | live trigger SUCCEEDED, payload {artifact_id,r2_key,content_hash_hex,chain_hash_hex}; blob on disk; chain canonical-verifies |

## Verification Results

- `uv run pytest control-plane/tests/test_evidence_recording.py` → 4 passed (2 unit + 2 integration vs live bs-postgres).
- `ruff check` clean on all 7 plan files.
- Live: worker registered bs-heartbeat + record-evidence; `orchestrator.py trigger-record-evidence` returned full payload; blob present under EVIDENCE_ROOT; chain `chain_hash == sha256(prev_hash || json.dumps(payload,sort_keys=True,default=str))` = True, genesis empty.

## Deviations from Plan

| Type | Count | Impact |
|------|-------|--------|
| Spec-correction (auto) | 1 | Idempotency mechanism (no scope creep) |
| Scope additions | 1 | pyproject (moto dep + marker) — outside files_modified |
| Test-infra | 1 | ThreadedMotoServer vs mock_aws |
| Backend choice | 1 | local backend for live trigger |

1. **ON CONFLICT (content_hash) not executable** — `evidence_artifacts` has no UNIQUE constraint on `content_hash` and the schema is boundary-locked. Replaced with a per-finding `pg_advisory_xact_lock` SELECT-guard (the same lock HashChainService already uses), idempotency keyed `(finding_id, content_hash)` — the correct content-addressed semantic. Atomicity + chain-append-only-on-new preserved.
2. **pyproject.toml edited** (not in plan files_modified) — added `moto[server]>=5.0` to control-plane dev extra (plan assumed moto present; it was undeclared) and registered the `integration` pytest marker (control-plane config lacked it → `PytestUnknownMarkWarning`).
3. **moto `mock_aws` → `ThreadedMotoServer`** — `mock_aws` does not reliably intercept aiobotocore (bypasses botocore's HTTP layer); the threaded server is a real local S3 endpoint aioboto3 reaches over HTTP.
4. **Live trigger used `EVIDENCE_BACKEND=local`** — no real R2 creds present; R2BlobStore S3 path is covered by the moto unit test. Real-bucket smoke remains a deployment concern (`scripts/r2_smoke.py`).

## Deferred Items

- evidence-mcp (standalone local-FS+SQLite stdio) vs control-plane (R2+Postgres) divergence — OUT OF SCOPE, defer to later plan.
- oracle_verdict gating (recording attempts = legit audit trail) — deferred per audit.
- aioboto3 client pooling — Phase 2 optimization.
- in-container worker token wiring (carried from 01-02).

## Next Phase Readiness

**Ready:** Validated findings can now be durably recorded with tamper-evident evidence. 01-04 (validator wiring) can call `trigger-record-evidence` after a `validated` verdict.

**Concerns:** Hatchet client token is session-ephemeral (regen runbook below). Pre-existing ruff debt (~40 errors in non-01-03 files) still untriaged.

**Blockers:** None.

## Runbook — regenerate Hatchet client token

```bash
TENANT=707d0855-80ab-4e1f-a156-f1c4546cbf52   # Default tenant
docker exec bs-hatchet /hatchet-admin token create --config /config \
  --tenant-id "$TENANT" --name bs-worker
# export HATCHET_CLIENT_TOKEN=<token>; HATCHET_CLIENT_TLS_STRATEGY=none
```

---
*Phase: 01-community-edition-mvp, Plan: 03*
*Completed: 2026-05-29*
