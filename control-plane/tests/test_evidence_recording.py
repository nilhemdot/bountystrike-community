# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for the evidence write path (plan 01-03).

Layers:

* AC-1 (unit) — ``R2BlobStore`` carries the boto3>=1.36 checksum-safe Config by
  INTROSPECTION (the real trap-#5 gate), plus a moto byte-fidelity round-trip.
  moto runs as a ThreadedMotoServer (a real local S3 endpoint) because moto's
  in-process ``mock_aws`` does not reliably intercept aiobotocore.
* AC-2 / AC-1c (integration) — ``EvidenceRecordingService.record`` inserts
  exactly one artifact + one audit entry, and a byte-identical re-record returns
  the same artifact_id while adding NO duplicate row and NO second audit entry.
* AC-3 chain (integration) — the audit chain verifies link-by-link
  (chain_hash == sha256(prev_hash || canonical_json(payload))) with a genesis
  prev_hash of b"" (0-byte) per migration 03.

Integration tests are gated on ``BS5_PG_TEST_DSN`` (skipped when unset) so CI
without a live Postgres stays green::

    BS5_PG_TEST_DSN=postgresql://bs:<pw>@127.0.0.1:5432/bountystrike \\
        uv run pytest control-plane/tests/test_evidence_recording.py -v
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import sys
import uuid
from collections.abc import AsyncIterator, Iterator

import asyncpg
import boto3
import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "control-plane", "src"))

from control_plane.domains.evidence_management.repositories.blob_store import (  # noqa: E402
    R2BlobStore,
)
from control_plane.domains.evidence_management.services import (  # noqa: E402
    EvidenceRecordingService,
    HashChainService,
)
from control_plane.domains.evidence_management.value_objects import (  # noqa: E402
    ContentHash,
    R2Key,
)

_BUCKET = "bs-evidence-test"
_PLATFORM = "hackerone"
_PROGRAM = "acme-corp"

_DSN = os.environ.get("BS5_PG_TEST_DSN", "").replace("+asyncpg", "")
_skip_if_no_dsn = pytest.mark.skipif(
    not _DSN, reason="BS5_PG_TEST_DSN not set; skipping live-Postgres tests"
)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def moto_store() -> Iterator[R2BlobStore]:
    """A ThreadedMotoServer-backed R2BlobStore. Real HTTP — aiobotocore-safe."""
    from moto.server import ThreadedMotoServer

    port = _free_port()
    server = ThreadedMotoServer(ip_address="127.0.0.1", port=port, verbose=False)
    server.start()
    endpoint = f"http://127.0.0.1:{port}"
    try:
        # Create the bucket with a sync client (region us-east-1 needs no
        # LocationConstraint), then hand an R2BlobStore pointed at the same
        # endpoint to the test.
        boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id="test",
            aws_secret_access_key="test",
            region_name="us-east-1",
        ).create_bucket(Bucket=_BUCKET)
        store = R2BlobStore(
            bucket=_BUCKET,
            endpoint_url=endpoint,
            access_key_id="test",
            secret_access_key="test",
            region="us-east-1",
        )
        yield store
    finally:
        server.stop()


@pytest.fixture
async def pg() -> AsyncIterator[tuple[asyncpg.Pool, uuid.UUID]]:
    """Asyncpg pool + a seeded findings row (FK target). Cleans up on teardown."""
    if not _DSN:
        pytest.skip("BS5_PG_TEST_DSN not set")

    async def _init(conn: asyncpg.Connection) -> None:
        # Decode jsonb back to dict on read so the chain-verify test can
        # re-serialize the payload canonically.
        await conn.set_type_codec(
            "jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
        )

    pool = await asyncpg.create_pool(_DSN, min_size=1, max_size=4, init=_init)
    finding_id = uuid.uuid4()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO findings (id, status) VALUES ($1, 'hypothesis')",
            finding_id,
        )
    try:
        yield pool, finding_id
    finally:
        async with pool.acquire() as conn:
            # FK ON DELETE CASCADE drops audit_log + evidence_artifacts rows.
            await conn.execute("DELETE FROM findings WHERE id = $1", finding_id)
        await pool.close()


# --------------------------------------------------------------------------
# AC-1 — checksum config (the real trap-#5 gate) + moto byte fidelity
# --------------------------------------------------------------------------


def test_checksum_config_is_when_required() -> None:
    """AC-1 gate: the Config literally carries when_required for both knobs."""
    cfg = R2BlobStore._CHECKSUM_CONFIG
    assert cfg.request_checksum_calculation == "when_required"
    assert cfg.response_checksum_validation == "when_required"


async def test_checksum_round_trip_byte_fidelity(moto_store: R2BlobStore) -> None:
    """AC-1: a put -> get through the (checksum-configured) client preserves bytes."""
    payload = b"bs5-evidence-" + os.urandom(64)
    key = R2Key.compute(
        platform=_PLATFORM,
        program_handle=_PROGRAM,
        finding_id=uuid.uuid4(),
        content_hash=ContentHash.from_bytes(payload),
    )
    await moto_store.put(key, payload)
    assert await moto_store.exists(key) is True
    assert await moto_store.get(key) == payload


# --------------------------------------------------------------------------
# AC-2 / AC-1c — atomic + idempotent record (live Postgres)
# --------------------------------------------------------------------------


@_skip_if_no_dsn
@pytest.mark.integration
async def test_record_atomic_and_idempotent(
    pg: tuple[asyncpg.Pool, uuid.UUID], moto_store: R2BlobStore
) -> None:
    pool, finding_id = pg
    svc = EvidenceRecordingService(moto_store, pool, HashChainService())
    poc = b"poc-payload-" + os.urandom(32)

    r1 = await svc.record(
        finding_id=finding_id,
        platform=_PLATFORM,
        program_handle=_PROGRAM,
        raw_bytes=poc,
        oracle_verdict="validated",
        oracle_method="sqli-timing",
        scope_token_jti="jti-test-001",
    )
    assert set(r1) == {"artifact_id", "r2_key", "content_hash_hex", "chain_hash_hex"}

    async with pool.acquire() as conn:
        n_art = await conn.fetchval(
            "SELECT count(*) FROM evidence_artifacts WHERE finding_id = $1", finding_id
        )
        n_aud = await conn.fetchval(
            "SELECT count(*) FROM audit_log WHERE finding_id = $1", finding_id
        )
    assert n_art == 1
    assert n_aud == 1

    # Idempotent re-record: byte-identical input.
    r2 = await svc.record(
        finding_id=finding_id,
        platform=_PLATFORM,
        program_handle=_PROGRAM,
        raw_bytes=poc,
        oracle_verdict="validated",
        oracle_method="sqli-timing",
        scope_token_jti="jti-test-001",
    )
    assert r2["artifact_id"] == r1["artifact_id"]
    assert r2["content_hash_hex"] == r1["content_hash_hex"]

    async with pool.acquire() as conn:
        n_art2 = await conn.fetchval(
            "SELECT count(*) FROM evidence_artifacts WHERE finding_id = $1", finding_id
        )
        n_aud2 = await conn.fetchval(
            "SELECT count(*) FROM audit_log WHERE finding_id = $1", finding_id
        )
    # AC-1c: re-record adds neither a duplicate artifact nor a second chain link.
    assert n_art2 == 1
    assert n_aud2 == 1

    # Blob is retrievable from the store.
    key = R2Key.compute(
        platform=_PLATFORM,
        program_handle=_PROGRAM,
        finding_id=finding_id,
        content_hash=ContentHash.from_bytes(poc),
    )
    assert await moto_store.get(key) == poc


@_skip_if_no_dsn
@pytest.mark.integration
async def test_audit_chain_verifies(
    pg: tuple[asyncpg.Pool, uuid.UUID], moto_store: R2BlobStore
) -> None:
    pool, finding_id = pg
    svc = EvidenceRecordingService(moto_store, pool, HashChainService())
    poc = b"chain-poc-" + os.urandom(32)

    await svc.record(
        finding_id=finding_id,
        platform=_PLATFORM,
        program_handle=_PROGRAM,
        raw_bytes=poc,
        oracle_verdict="validated",
        oracle_method="xss-playwright",
        scope_token_jti="jti-test-002",
    )

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT entry_type, payload, prev_hash, chain_hash FROM audit_log"
            " WHERE finding_id = $1 ORDER BY created_at",
            finding_id,
        )
    assert len(rows) == 1
    entry = rows[0]
    # Genesis link: prev_hash is the empty byte string, NOT 32 zero bytes.
    assert entry["prev_hash"] == b""
    expected = hashlib.sha256(
        entry["prev_hash"] + json.dumps(entry["payload"], sort_keys=True, default=str).encode()
    ).digest()
    assert entry["chain_hash"] == expected
    assert len(entry["chain_hash"]) == 32
