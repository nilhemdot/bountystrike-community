"""Tests for evidence_management bounded context."""

from __future__ import annotations

import hashlib
import uuid
from unittest.mock import AsyncMock

import pytest

from control_plane.core.security import PathTraversalError
from control_plane.domains.evidence_management.aggregates import (
    AuditLogEntry,
    EvidenceArtifact,
)
from control_plane.domains.evidence_management.events import (
    AuditEntryRecorded,
    EvidenceArtifactCreated,
)
from control_plane.domains.evidence_management.repositories import LocalFsBlobStore
from control_plane.domains.evidence_management.services import HashChainService
from control_plane.domains.evidence_management.value_objects import (
    ContentHash,
    OracleData,
    R2Key,
)

_PLATFORM = "hackerone"
_HANDLE = "acme-corp"


def _oracle() -> OracleData:
    return OracleData(
        verdict="validated",
        oracle_method="ssrf-oast",
        attempts=2,
        cleanup_confirmed=True,
        validator_model="claude-sonnet-4-6",
    )


# ---------------------------------------------------------------------------
# 1. ContentHash roundtrip
# ---------------------------------------------------------------------------


def test_content_hash_roundtrip():
    data = b"hello"
    expected_hex = hashlib.sha256(data).hexdigest()
    ch = ContentHash.from_bytes(data)
    assert ch.hex == expected_hex
    assert ch.storage_ref == f"sha256:{expected_hex}"


# ---------------------------------------------------------------------------
# 2. EvidenceArtifact.create
# ---------------------------------------------------------------------------


def test_evidence_artifact_create():
    finding_id = uuid.uuid4()
    raw_bytes = b"poc-evidence"

    artifact = EvidenceArtifact.create(
        finding_id=finding_id,
        platform=_PLATFORM,
        program_handle=_HANDLE,
        raw_bytes=raw_bytes,
        oracle_data=_oracle(),
    )

    expected_hex = hashlib.sha256(raw_bytes).hexdigest()
    assert artifact.content_hash.hex == expected_hex

    # R2 key format: {platform}/{program}/{uuid}/{hex}
    key = artifact.r2_key.key
    parts = key.split("/")
    assert len(parts) == 4
    assert parts[0] == _PLATFORM
    assert parts[1] == _HANDLE
    assert parts[2] == str(finding_id)
    assert parts[3] == expected_hex

    events = artifact.pull_events()
    assert len(events) == 1
    event = events[0]
    assert isinstance(event, EvidenceArtifactCreated)
    assert event.finding_id == str(finding_id)
    assert event.platform == _PLATFORM
    assert event.content_hash_hex == expected_hex
    assert event.r2_key == key


# ---------------------------------------------------------------------------
# 3. AuditLogEntry hash chain
# ---------------------------------------------------------------------------


def test_audit_log_chain():
    finding_id = uuid.uuid4()

    first = AuditLogEntry.create(
        finding_id=finding_id,
        entry_type="submission",
        payload={"note": "initial"},
        prev_hash=b"",
    )

    second = AuditLogEntry.create(
        finding_id=finding_id,
        entry_type="oracle_verdict",
        payload={"verdict": "validated"},
        prev_hash=first.chain_hash,
    )

    assert second.prev_hash == first.chain_hash
    assert second.chain_hash != second.prev_hash

    events = second.pull_events()
    assert len(events) == 1
    assert isinstance(events[0], AuditEntryRecorded)


# ---------------------------------------------------------------------------
# 4. LocalFsBlobStore put/get/exists
# ---------------------------------------------------------------------------


async def test_blob_store_put_get(tmp_path):
    store = LocalFsBlobStore(tmp_path)
    finding_id = uuid.uuid4()
    raw = b"binary-payload"
    ch = ContentHash.from_bytes(raw)
    key = R2Key.compute(_PLATFORM, _HANDLE, finding_id, ch)

    assert not await store.exists(key)
    await store.put(key, raw)
    assert await store.exists(key)
    assert await store.get(key) == raw


# ---------------------------------------------------------------------------
# 5. Directory traversal blocked
# ---------------------------------------------------------------------------


def test_blob_store_traversal_blocked():
    # Construct an R2Key with a traversal sequence in finding_id.
    # R2Key.finding_id has no regex constraint so we can set it directly.
    # The key becomes: hackerone/acme-corp/../../../evil/{sha256}
    # Under /some/root this resolves to /evil/{sha256} — outside the root.
    malicious_key = R2Key(
        platform=_PLATFORM,
        program=_HANDLE,
        finding_id="../../../evil",
        sha256_hex="a" * 64,
    )
    with pytest.raises(PathTraversalError):
        malicious_key.under("/some/root")


# ---------------------------------------------------------------------------
# 6. HashChainService with mocked asyncpg conn
# ---------------------------------------------------------------------------


async def test_hash_chain_service_genesis():
    """First entry gets b'' as prev_hash (genesis)."""
    finding_id = uuid.uuid4()
    conn = AsyncMock()
    conn.fetchval.return_value = None  # no prior entries

    service = HashChainService()
    prev = await service.get_latest_chain_hash(finding_id, conn)
    assert prev == b""


async def test_hash_chain_service_append(tmp_path):
    finding_id = uuid.uuid4()
    conn = AsyncMock()
    conn.fetchval.return_value = None  # genesis

    service = HashChainService()
    entry = await service.append_entry(
        finding_id=finding_id,
        entry_type="submission",
        payload={"key": "value"},
        conn=conn,
    )

    assert entry.prev_hash == b""
    assert len(entry.chain_hash) == 32  # SHA-256 → 32 bytes
    conn.execute.assert_called_once()
