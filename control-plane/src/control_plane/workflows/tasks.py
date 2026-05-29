# SPDX-License-Identifier: AGPL-3.0-or-later
"""First BountyStrike Hatchet v1 task — heartbeat (plan 01-02).

Proves the durable-execution runtime end to end (trigger -> worker -> status)
with no business logic. v1 function-based API: ``@hatchet.task`` with a Pydantic
``input_validator`` and an async handler taking ``(input, ctx)``; triggered via
``aio_run``. The legacy class-based decorator API (hatchet . workflow) is NOT
used. Real agent tasks (recon -> scan -> exploit -> validate) land in later plans.
"""

from __future__ import annotations

import base64
import os
from datetime import UTC, datetime

import asyncpg
from hatchet_sdk import Context
from pydantic import BaseModel

from control_plane.domains.evidence_management.repositories.factory import make_blob_store
from control_plane.domains.evidence_management.services import (
    EvidenceRecordingService,
    HashChainService,
)
from control_plane.workflows.client import hatchet


class HeartbeatInput(BaseModel):
    """Input schema for the heartbeat task."""

    message: str


@hatchet.task(name="bs-heartbeat", input_validator=HeartbeatInput)
async def heartbeat(input: HeartbeatInput, ctx: Context) -> dict[str, str]:
    """Echo the message back with a server timestamp — a durable no-op."""
    return {
        "echo": input.message,
        "completed_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }


class RecordEvidenceInput(BaseModel):
    """Input schema for the record-evidence task.

    PoC bytes ride the gRPC payload base64-encoded (``raw_bytes_b64``); the
    handler decodes and hands raw bytes to
    :meth:`EvidenceRecordingService.record`, which enforces the size cap. Field
    validity (non-empty jti, uuid finding_id, etc.) is enforced there too, at
    the service boundary, so a single source of truth governs both call paths.
    """

    finding_id: str
    platform: str
    program_handle: str
    raw_bytes_b64: str
    oracle_verdict: str
    oracle_method: str
    scope_token_jti: str


@hatchet.task(name="record-evidence", input_validator=RecordEvidenceInput)
async def record_evidence(input: RecordEvidenceInput, ctx: Context) -> dict[str, str]:
    """Durably record one finding's evidence: blob → artifact row → audit chain.

    Resource setup (asyncpg pool, blob store) lives inside the handler — at
    Phase 1 volume (one PUT per validated finding) a shared pool is a later
    optimization. Reads ``DATABASE_URL`` and the ``EVIDENCE_BACKEND`` / R2 env
    consumed by ``make_blob_store``.
    """
    raw_bytes = base64.b64decode(input.raw_bytes_b64)
    dsn = os.environ["DATABASE_URL"].replace("+asyncpg", "")
    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=2)
    try:
        service = EvidenceRecordingService(
            blob_store=make_blob_store(),
            pool=pool,
            hash_chain_service=HashChainService(),
        )
        return await service.record(
            finding_id=input.finding_id,
            platform=input.platform,
            program_handle=input.program_handle,
            raw_bytes=raw_bytes,
            oracle_verdict=input.oracle_verdict,
            oracle_method=input.oracle_method,
            scope_token_jti=input.scope_token_jti,
        )
    finally:
        await pool.close()
