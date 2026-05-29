# SPDX-License-Identifier: AGPL-3.0-or-later

"""Atomic evidence-recording service — the heart of the "no verification, no
submission" moat (PROJECT.md).

``EvidenceRecordingService.record`` performs ONE idempotent write of a validated
finding's PoC bytes:

1. content-address the bytes (SHA-256) and PUT the blob (content-addressed, so
   the PUT itself is idempotent);
2. in a SINGLE asyncpg transaction, under a per-finding advisory lock:
   - insert the ``evidence_artifacts`` row (only if one does not already exist
     for this ``(finding_id, content_hash)``), and
   - append ONE hash-chained ``audit_log`` entry via
     :class:`HashChainService` — but ONLY when a new artifact row was inserted,
     so replaying a crashed task can neither duplicate the artifact row nor
     fork/pad the tamper-evident chain.

Schema note: ``evidence_artifacts`` carries no UNIQUE constraint on
``content_hash`` (see infra/sql/01_schema.sql — boundary-locked for this plan),
so idempotency cannot use ``ON CONFLICT``. Instead the per-finding
``pg_advisory_xact_lock`` that :class:`HashChainService` already uses for chain
extension is taken FIRST, serializing the SELECT-guard + INSERT against
concurrent identical records for the same finding. Idempotency is keyed on
``(finding_id, content_hash)`` — the correct content-addressed semantic: the
same bytes for the same finding are one artifact; the same bytes for a different
finding get their own row pointing at the shared blob.
"""

from __future__ import annotations

import json
import uuid

import asyncpg
from control_plane.domains.evidence_management.repositories.blob_store import BlobStore
from control_plane.domains.evidence_management.services.hash_chain_service import (
    HashChainService,
)
from control_plane.domains.evidence_management.value_objects import ContentHash, R2Key
from pydantic import BaseModel, ConfigDict, Field

# Hatchet's gRPC message ceiling is ~4 MiB; a raw_bytes payload larger than this
# would fail mid-transport after a successful R2 PUT (orphan blob + crashed
# task). Reject it at the input boundary instead. Raise the cap here only in
# lockstep with the engine's grpc max-message-size if larger PoCs are needed.
MAX_RAW_BYTES = 4 * 1024 * 1024

# entry_type for the audit-chain link this service appends.
ENTRY_TYPE = "evidence_recorded"


class _RecordInputs(BaseModel):
    """Validated inputs for :meth:`EvidenceRecordingService.record`.

    Validation runs at the method boundary (PROJECT.md: Pydantic at every input
    boundary). ``scope_token_jti`` is required non-empty so every artifact ties
    back to the scope JWT that authorized the work (audit reconstruction).
    """

    model_config = ConfigDict(frozen=True)

    finding_id: uuid.UUID
    platform: str = Field(min_length=1)
    program_handle: str = Field(min_length=1)
    raw_bytes: bytes = Field(min_length=1, max_length=MAX_RAW_BYTES)
    oracle_verdict: str = Field(min_length=1)
    oracle_method: str = Field(min_length=1)
    scope_token_jti: str = Field(min_length=1)


class EvidenceRecordingService:
    """Records evidence atomically: blob → artifact row → hash-chained audit."""

    def __init__(
        self,
        blob_store: BlobStore,
        pool: asyncpg.Pool,
        hash_chain_service: HashChainService,
    ) -> None:
        self._blob_store = blob_store
        self._pool = pool
        self._hash_chain = hash_chain_service

    async def record(
        self,
        finding_id: uuid.UUID | str,
        platform: str,
        program_handle: str,
        raw_bytes: bytes,
        oracle_verdict: str,
        oracle_method: str,
        scope_token_jti: str,
    ) -> dict[str, str]:
        """Idempotently record evidence for ``finding_id``.

        Returns ``{artifact_id, r2_key, content_hash_hex, chain_hash_hex}``.
        Raises ``pydantic.ValidationError`` on bad/oversized input (before any
        PUT), or propagates the DB error if the transaction fails after the PUT
        (the orphan blob is acceptable — content-addressed, reused on re-run).
        """
        inputs = _RecordInputs(
            finding_id=finding_id,  # type: ignore[arg-type]
            platform=platform,
            program_handle=program_handle,
            raw_bytes=raw_bytes,
            oracle_verdict=oracle_verdict,
            oracle_method=oracle_method,
            scope_token_jti=scope_token_jti,
        )

        content_hash = ContentHash.from_bytes(inputs.raw_bytes)
        r2_key = R2Key.compute(
            platform=inputs.platform,
            program_handle=inputs.program_handle,
            finding_id=inputs.finding_id,
            content_hash=content_hash,
        )
        oracle_data = {
            "verdict": inputs.oracle_verdict,
            "oracle_method": inputs.oracle_method,
        }

        # PUT the blob BEFORE the DB transaction commits (AC-1d ordering). The
        # PUT is idempotent (content-addressed); if the txn below fails, the
        # orphan blob is acceptable and record(...) raises rather than lying.
        await self._blob_store.put(r2_key, inputs.raw_bytes)

        async with self._pool.acquire() as conn:
            # HashChainService.append_entry passes a dict into a JSONB column, so
            # the connection must encode dict→jsonb. Register defensively here so
            # callers need not configure the pool.
            await conn.set_type_codec(
                "jsonb",
                encoder=json.dumps,
                decoder=json.loads,
                schema="pg_catalog",
            )
            async with conn.transaction():
                # Take the per-finding advisory lock FIRST (same keyspace as
                # HashChainService) so the SELECT-guard + INSERT + audit append
                # are serialized against a concurrent identical record() for the
                # same finding. Re-entrant: append_entry takes it again; xact
                # locks release together on commit.
                await conn.execute(
                    "SELECT pg_advisory_xact_lock(hashtext($1::text)::bigint)",
                    str(inputs.finding_id),
                )

                existing_id = await conn.fetchval(
                    "SELECT id FROM evidence_artifacts WHERE finding_id = $1 AND content_hash = $2",
                    inputs.finding_id,
                    content_hash.hex,
                )
                if existing_id is not None:
                    # Idempotent re-record: do NOT insert a duplicate row and do
                    # NOT extend the chain (AC-1c). Return the existing artifact
                    # and the chain_hash of its recording entry.
                    chain_hash = await conn.fetchval(
                        "SELECT chain_hash FROM audit_log"
                        " WHERE finding_id = $1 AND entry_type = $2"
                        " ORDER BY created_at DESC LIMIT 1",
                        inputs.finding_id,
                        ENTRY_TYPE,
                    )
                    return {
                        "artifact_id": str(existing_id),
                        "r2_key": r2_key.key,
                        "content_hash_hex": content_hash.hex,
                        "chain_hash_hex": chain_hash.hex() if chain_hash else "",
                    }

                artifact_id = uuid.uuid4()
                await conn.execute(
                    "INSERT INTO evidence_artifacts"
                    " (id, finding_id, content_hash, oracle_data, scope_token_jti, r2_key)"
                    " VALUES ($1, $2, $3, $4, $5, $6)",
                    artifact_id,
                    inputs.finding_id,
                    content_hash.hex,
                    oracle_data,
                    inputs.scope_token_jti,
                    r2_key.key,
                )
                entry = await self._hash_chain.append_entry(
                    finding_id=inputs.finding_id,
                    entry_type=ENTRY_TYPE,
                    payload={
                        "artifact_id": str(artifact_id),
                        "content_hash": content_hash.hex,
                        "r2_key": r2_key.key,
                        "scope_token_jti": inputs.scope_token_jti,
                        "oracle_verdict": inputs.oracle_verdict,
                        "oracle_method": inputs.oracle_method,
                    },
                    conn=conn,
                )
                return {
                    "artifact_id": str(artifact_id),
                    "r2_key": r2_key.key,
                    "content_hash_hex": content_hash.hex,
                    "chain_hash_hex": entry.chain_hash.hex(),
                }


__all__ = ["EvidenceRecordingService", "MAX_RAW_BYTES"]
