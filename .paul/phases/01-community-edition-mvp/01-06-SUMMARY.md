---
phase: 01-community-edition-mvp
plan: 06
subsystem: validation
tags: [oracles, hatchet, evidence, finding-fsm, deterministic-verifier, asyncpg]

requires:
  - phase: 01-02
    provides: Hatchet v1 runtime (@hatchet.task, worker, aio_run trigger)
  - phase: 01-03
    provides: EvidenceRecordingService.record (SHA-256 content-addressed + hash-chain)
  - phase: 01-01
    provides: findings / scan_jobs / evidence_artifacts schema + finding_status enum
provides:
  - control-plane validation domain (cwe→oracle dispatch + VerifyFindingService)
  - verify-finding Hatchet task + worker registration + orchestrator trigger seam
  - the deterministic-verifier moat in code (no validated without evidence)
affects: [02-01 exploit/validator/dedup, 01-08 installer (chromium + worker token), benchmark]

tech-stack:
  added: [oracle-mcp as control-plane workspace dep (in-process oracle calls)]
  patterns: [optimistic-claim FSM, moat-by-ordering, parked validation_pending state]

key-files:
  created:
    - control-plane/src/control_plane/domains/validation/dispatch.py
    - control-plane/src/control_plane/domains/validation/services/verify_service.py
    - control-plane/tests/test_verify_finding.py
  modified:
    - control-plane/src/control_plane/workflows/tasks.py
    - control-plane/src/control_plane/workflows/worker.py
    - scripts/orchestrator.py
    - control-plane/pyproject.toml

key-decisions:
  - "In-process oracle import (no MCP stdio) — oracles are stateless coroutines"
  - "rejected = ONLY a real non-validated oracle verdict; provenance/input/crash never reject"
  - "CWE-94/CWE-74 → None (parked), not SSTI — preserved for Phase-2 RCE"

patterns-established:
  - "Optimistic CLAIM (single-statement UPDATE…WHERE status='hypothesis' RETURNING) as the lock"
  - "CLAIM-before-side-effect must release the claim on transient failure or it poisons retry"
  - "Moat by ordering: status='validated' set ONLY after record() returns a content_hash_hex"

duration: ~75min
started: 2026-05-31T00:00:00Z
completed: 2026-05-31T01:15:00Z
---

# Phase 1 Plan 06: Deterministic Verifier Summary

**Wired the five field-validated oracles into a durable `verify-finding` Hatchet task: a hypothesis finding is claimed, dispatched by CWE to its oracle, and on a `validated` verdict gets a SHA-256-linked evidence artifact + `status='validated'`; every other path parks or rejects with no evidence — the moat, enforced by ordering.**

## Performance

| Metric | Value |
|--------|-------|
| Tasks | 3 of 3 completed (all qualified PASS) |
| Unit tests | 29 passed |
| Files | 4 created, 3 modified |
| ruff (touched files) | clean |

## Acceptance Criteria Results

| Criterion | Status | Notes |
|-----------|--------|-------|
| AC-1: validated → evidence + status flip | Pass | `test_validated_records_evidence_and_flips_status`; evidence_hash=content_hash_hex |
| AC-2: non-validated → rejected, NO evidence (moat) | Pass | parametrized over unreproducible/flaky/inconclusive; zero record() calls |
| AC-3: cwe → oracle dispatch (5 oracles + aliases) | Pass | smoke + parametrized; CWE-94/74→None (S3) |
| AC-4: unsupported cwe → safe no-op | Pass | parks validation_pending, no oracle, no evidence |
| AC-5: already-claimed → benign no-op | Pass | CLAIM 0 rows → noop_unclaimed |
| AC-6: Hatchet verify-finding registers + triggerable | Pass | AST wiring check + `trigger-verify-finding --help` |
| AC-7: control-plane invokes oracles in-process | Pass | `uv sync --all-packages`; `from oracle_mcp.oracles import …` works |
| AC-8: oracles remain field-valid post-wiring | Deferred | deploy gate (needs docker+chromium); oracle source unmodified |
| AC-9: transient oracle error releases claim (M1) | Pass | `test_oracle_error_releases_claim` — re-raise + status→hypothesis |
| AC-10: validated + missing jti parks, not rejects (M2) | Pass | two cases (job_id NULL; scope_jwt_jti NULL) → blocked_missing_scope_jti |
| AC-11: null url/parameter → safe no-op (S1) | Pass | parametrized parameter/url None/"" → missing_input |

## Accomplishments

- Deterministic-verifier moat is now executable code: the single durable transition that turns a hypothesis into either `validated`+evidence or `rejected`/parked, with the invariant enforced by ordering (status flips only after `record()` returns a hash).
- Honest finding FSM: `rejected` means an oracle ran and said not-real; provenance gaps, missing inputs, and transient crashes park or release instead — no stranded findings, no real bug buried.
- All five audit deltas (M1/M2/S1/S2/S3) implemented and unit-tested; 29 tests, no DB/network/docker required.

## Files Created/Modified

| File | Change | Purpose |
|------|--------|---------|
| `domains/validation/dispatch.py` | Created | `normalise_cwe`, `resolve_oracle`, `OracleSpec`, canary const |
| `domains/validation/services/verify_service.py` | Created | `VerifyFindingService.verify()` — the FSM transition |
| `domains/validation/__init__.py`, `services/__init__.py` | Created | domain exports |
| `workflows/tasks.py` | Modified | `+VerifyFindingInput` + `@hatchet.task("verify-finding")` (append-only) |
| `workflows/worker.py` | Modified | registers `verify_finding` |
| `scripts/orchestrator.py` | Modified | `trigger_verify_finding` + `trigger-verify-finding` subcommand |
| `control-plane/pyproject.toml` | Modified | `+oracle-mcp` dependency |
| `tests/test_verify_finding.py` | Created | 29 tests (FakePool/FakeConn/FakeEvidence + fake oracle) |

## Deviations from Plan

| Type | Count | Impact |
|------|-------|--------|
| Auto-fixed / scope additions | 4 | Essential robustness, no scope creep |
| Deferred (deploy gate) | 2 | Logged; same posture as 01-04/05 |

1. **Pool `max_size=4`** (plan said mirror record_evidence's 2). VerifyFindingService re-acquires per write and the evidence service acquires its own conn — headroom avoids any acquire contention. Benign.
2. **Added `blocked_missing_metadata` branch.** `record()` also requires non-empty `platform`/`program_handle` (same input-completeness class as the M2 jti guard). Guarding prevents a `ValidationError` crash-strand on a validated finding with NULL metadata. Faithful M2 extension.
3. **Tests use FakeConn, not sqlite** (plan Task 3 said "sqlite"). `VerifyFindingService` is asyncpg-specific (`$1::uuid`, `now()`); sqlite cannot run that SQL. Fakes test all logic branches dialect-free and deterministically — strictly better coverage than a sqlite shim would give.
4. **Connection NOT held across the oracle call** — each DB write re-acquires briefly. Avoids nested-acquire deadlock risk and frees the pool during a slow (≤15s) oracle. The CLAIM autocommits, so concurrency safety is unaffected.

### Deferred Items (deploy gate → 01-08 / live smoke)
- **AC-8 XSS field-validation harness** + **live worker-trigger of verify-finding** — need docker + `playwright install chromium` + `HATCHET_CLIENT_TOKEN`. Oracles are stateless probes untouched by the 01-01 DB rebuild, so no regression risk; verified-by-construction here, empirically gated at deploy (same as 01-04 bbscope / 01-05 webhook POST).

## Issues Encountered

| Issue | Resolution |
|-------|------------|
| asyncpg won't coerce `str`→`uuid` for the PK param | `$1::uuid` cast in all finding-id statements; `record()` coerces via pydantic |
| ruff I001 import grouping on new service | `ruff --fix` (import-sort only) |

## Next Phase Readiness

**Ready:**
- The `validate` node of recon→scan→**validate**→report is live and callable (`orchestrator.py trigger-verify-finding` / `verify_finding.aio_run`).
- Evidence + hash-chain reused unchanged; findings FSM advances honestly.

**Concerns:**
- Live worker trigger + XSS field-validation unproven this session (deploy gate, 01-08).
- A hard process crash between CLAIM and oracle leaves `validation_pending` (D1: terminal/timeout error state deferred to Phase 2 observability).

**Blockers:** None. Working tree NOT committed — phase transition (after 01-08) will commit.

---
*Phase: 01-community-edition-mvp, Plan: 06*
*Completed: 2026-05-31*
