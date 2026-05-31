# SPDX-License-Identifier: AGPL-3.0-or-later
"""VerifyFindingService — the deterministic-verifier bridge (plan 01-06).

Claims a ``status='hypothesis'`` finding, dispatches it to the matching oracle,
and on a ``validated`` verdict records a SHA-256-linked evidence artifact
(reusing the 01-03 :class:`EvidenceRecordingService`) before flipping the
finding to ``validated``.

MOAT INVARIANT (enforced by ORDERING): ``status`` becomes ``validated`` only on
the code path that already holds a ``content_hash_hex`` from ``record()``. If
``record()`` raises, the finding is never set ``validated`` — no evidence, no
``validated``.

Finding-state semantics (audit 01-06):
  * ``hypothesis``         — fresh, OR released after a transient oracle error
                             (re-claimable on Hatchet retry).
  * ``validation_pending`` — parked: claimed but cannot complete now and NOT a
                             failure (unsupported cwe, missing oracle input,
                             missing evidence provenance). Recoverable later.
  * ``validated``          — an oracle returned ``validated`` AND evidence was
                             recorded.
  * ``rejected``           — an oracle RAN and returned a non-validated verdict.
                             NEVER set for a provenance gap, a missing input, or
                             a transient crash — keeps the FSM honest for
                             post-incident reconstruction.

All DB statements run in asyncpg autocommit mode (one statement per ``execute``/
``fetch*``), so the optimistic CLAIM is durable immediately — a concurrent
worker's CLAIM matches zero rows and no-ops. The connection is NOT held across
the (potentially slow) oracle call; each write re-acquires briefly.
"""

from __future__ import annotations

import asyncpg
import structlog

from control_plane.domains.evidence_management.services import EvidenceRecordingService
from control_plane.domains.validation.dispatch import resolve_oracle

logger = structlog.get_logger("control_plane.domains.validation.verify")

# Optimistic claim: hypothesis -> validation_pending, atomically. 0 rows => the
# finding was not in 'hypothesis' (already claimed / terminal) => benign no-op.
_CLAIM_SQL = """
UPDATE findings SET status='validation_pending', updated_at=now()
WHERE id=$1::uuid AND status='hypothesis'
RETURNING id, job_id, program_handle, platform, cwe, url, parameter
"""

# Release the claim back to 'hypothesis' so a Hatchet retry can re-claim after a
# transient oracle error (audit M1). Guarded on validation_pending so it cannot
# clobber a row another path already advanced.
_RELEASE_SQL = """
UPDATE findings SET status='hypothesis', updated_at=now()
WHERE id=$1::uuid AND status='validation_pending'
"""

_VALIDATED_SQL = """
UPDATE findings SET status='validated', evidence_hash=$2, oracle_method=$3, updated_at=now()
WHERE id=$1::uuid
"""

_REJECTED_SQL = """
UPDATE findings SET status='rejected', oracle_method=$2, updated_at=now()
WHERE id=$1::uuid
"""

_JTI_SQL = "SELECT scope_jwt_jti FROM scan_jobs WHERE id=$1"


class VerifyFindingService:
    """Runs the hypothesis → validated/rejected/parked transition for one finding."""

    def __init__(self, pool: asyncpg.Pool, evidence_service: EvidenceRecordingService) -> None:
        self._pool = pool
        self._evidence = evidence_service

    async def verify(self, finding_id: str) -> dict[str, str]:
        fid = str(finding_id)

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(_CLAIM_SQL, fid)
        if row is None:
            return {"finding_id": fid, "result": "noop_unclaimed"}

        cwe = row["cwe"]
        url = row["url"]
        parameter = row["parameter"]

        spec = resolve_oracle(cwe)
        if spec is None:
            # Parked in validation_pending (set by CLAIM); awaits an out-of-scope
            # path (e.g. Phase-2 RCE). NOT a failure, NOT rejected (AC-4 / S3).
            logger.warning("verify.unsupported_cwe", finding_id=fid, cwe=cwe)
            return {"finding_id": fid, "result": "unsupported_cwe", "cwe": cwe or ""}

        if not url or not parameter:
            # Oracles require a non-empty param (and a url); never call with None/""
            # (audit S1). Parked, recoverable once recon supplies the input.
            logger.warning("verify.missing_oracle_input", finding_id=fid, cwe=cwe)
            return {"finding_id": fid, "result": "missing_input", "cwe": cwe or ""}

        # Transient oracle errors must release the claim, else a Hatchet retry's
        # CLAIM matches 0 rows and the finding strands in validation_pending
        # forever (audit M1).
        try:
            result = await spec.coro(**spec.kwargs(url, parameter))
        except Exception:
            async with self._pool.acquire() as conn:
                await conn.execute(_RELEASE_SQL, fid)
            logger.warning("verify.oracle_error", finding_id=fid, cwe=cwe, exc_info=True)
            raise

        if result.verdict != "validated":
            async with self._pool.acquire() as conn:
                await conn.execute(_REJECTED_SQL, fid, result.oracle_method)
            return {"finding_id": fid, "result": "rejected", "verdict": result.verdict}

        # Validated. Resolve evidence provenance. A missing scope JTI is a
        # PROVENANCE gap, not a false vuln: park (never reject, never call
        # record() with "" — it would raise ValidationError) (audit M2).
        async with self._pool.acquire() as conn:
            jti = await conn.fetchval(_JTI_SQL, row["job_id"]) if row["job_id"] else None
        if not jti:
            logger.warning("verify.missing_scope_jti", finding_id=fid)
            return {"finding_id": fid, "result": "blocked_missing_scope_jti"}

        # record() also requires non-empty platform + program_handle; a missing
        # one is the same provenance-gap class — park rather than crash-strand.
        if not row["platform"] or not row["program_handle"]:
            logger.warning("verify.missing_evidence_metadata", finding_id=fid)
            return {"finding_id": fid, "result": "blocked_missing_metadata"}

        raw_bytes = result.model_dump_json().encode()
        ev = await self._evidence.record(
            finding_id=fid,
            platform=row["platform"],
            program_handle=row["program_handle"],
            raw_bytes=raw_bytes,
            oracle_verdict="validated",
            oracle_method=result.oracle_method,
            scope_token_jti=jti,
        )
        # MOAT: status -> validated ONLY now, with a content_hash_hex in hand.
        async with self._pool.acquire() as conn:
            await conn.execute(_VALIDATED_SQL, fid, ev["content_hash_hex"], result.oracle_method)
        return {"finding_id": fid, "result": "validated", "evidence_hash": ev["content_hash_hex"]}
