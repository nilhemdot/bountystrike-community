"""Tests for evidence-mcp — blob store, audit chain, and MCP tool layer.

All tests use real temporary directories (no mocks for I/O).
"""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helpers shared by tests
# ---------------------------------------------------------------------------


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _chain_hash(prev_hash: bytes, payload: dict) -> bytes:
    payload_bytes = json.dumps(payload, sort_keys=True, default=str).encode()
    return hashlib.sha256(prev_hash + payload_bytes).digest()


def _r2_key(platform: str, program_handle: str, finding_id: str, sha256_hex: str) -> str:
    return f"{platform}/{program_handle}/{finding_id}/{sha256_hex}"


# ---------------------------------------------------------------------------
# Fixtures — isolated per test
# ---------------------------------------------------------------------------


@pytest.fixture()
def blob_store(tmp_path: Path):
    from evidence_mcp.store import BlobStore

    return BlobStore(tmp_path / "blobs")


@pytest.fixture()
async def audit_store(tmp_path: Path):
    from evidence_mcp.store import AuditStore

    store = AuditStore(tmp_path / "audit.db")
    await store.initialize()
    return store


@pytest.fixture(autouse=True)
def patch_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Point server module to per-test temp dirs and reset init state."""
    import evidence_mcp.server as srv

    blob_root = tmp_path / "blobs"
    db_path = tmp_path / "audit.db"
    monkeypatch.setenv("EVIDENCE_ROOT", str(blob_root))
    monkeypatch.setenv("EVIDENCE_DB", str(db_path))

    # Re-create store instances pointing at the new paths.
    from evidence_mcp.store import AuditStore, BlobStore

    srv.blob_store = BlobStore(blob_root)
    srv.audit_store = AuditStore(db_path)
    srv._initialized = False
    # Per-finding locks are bound to the running event loop; pytest-asyncio
    # creates a fresh loop per test, so stale locks must not leak across tests.
    srv._finding_locks.clear()


# ---------------------------------------------------------------------------
# 1. put and get round-trip
# ---------------------------------------------------------------------------


async def test_put_and_get_artifact():
    from evidence_mcp.server import get_artifact, put_artifact

    raw = b"hello evidence"
    result = await put_artifact(
        finding_id="11111111-0000-0000-0000-000000000001",
        platform="hackerone",
        program_handle="acme",
        raw_bytes_b64=_b64(raw),
        oracle_verdict="validated",
        oracle_method="sqli_timing_welch",
    )

    assert result.get("error") is None
    assert result["content_hash_hex"] == _sha256_hex(raw)
    assert "r2_key" in result
    assert "artifact_id" in result

    fetched = await get_artifact(result["r2_key"])
    assert fetched.get("error") is None
    assert base64.b64decode(fetched["raw_bytes_b64"]) == raw


# ---------------------------------------------------------------------------
# 2. Idempotency — same bytes → same content_hash
# ---------------------------------------------------------------------------


async def test_put_idempotent():
    from evidence_mcp.server import put_artifact

    raw = b"idempotent bytes"
    kwargs = dict(
        finding_id="22222222-0000-0000-0000-000000000002",
        platform="hackerone",
        program_handle="acme",
        raw_bytes_b64=_b64(raw),
        oracle_verdict="validated",
        oracle_method="sqli_timing_welch",
    )
    r1 = await put_artifact(**kwargs)
    r2 = await put_artifact(**kwargs)

    assert r1["content_hash_hex"] == r2["content_hash_hex"]
    assert r1["r2_key"] == r2["r2_key"]


# ---------------------------------------------------------------------------
# 3. Missing artifact → {"error": "not_found"}
# ---------------------------------------------------------------------------


async def test_get_missing_artifact_returns_error():
    from evidence_mcp.server import get_artifact

    result = await get_artifact("hackerone/acme/nonexistent-finding/deadbeef" * 1)
    assert result == {"error": "not_found"}


# ---------------------------------------------------------------------------
# 4. Audit genesis — prev_hash is b''
# ---------------------------------------------------------------------------


async def test_audit_genesis_entry():
    from evidence_mcp.server import append_audit_entry

    payload = {"verdict": "validated", "method": "sqli"}
    result = await append_audit_entry(
        finding_id="33333333-0000-0000-0000-000000000003",
        entry_type="oracle_result",
        payload=payload,
    )

    expected_chain_hash = _chain_hash(b"", payload)
    assert result["chain_hash_hex"] == expected_chain_hash.hex()
    assert "entry_id" in result
    assert result["entry_type"] == "oracle_result"


# ---------------------------------------------------------------------------
# 5. Chain integrity — each hash links correctly to its predecessor
# ---------------------------------------------------------------------------


async def test_audit_chain_is_hash_chained():
    from evidence_mcp.server import append_audit_entry, get_audit_chain

    fid = "44444444-0000-0000-0000-000000000004"
    payloads = [
        {"step": 1, "note": "first"},
        {"step": 2, "note": "second"},
        {"step": 3, "note": "third"},
    ]

    for p in payloads:
        await append_audit_entry(finding_id=fid, entry_type="oracle_result", payload=p)

    chain_result = await get_audit_chain(fid)
    entries = chain_result["entries"]
    assert len(entries) == 3

    # Verify the chain from genesis.
    prev_hash = b""
    for i, (entry, payload) in enumerate(zip(entries, payloads, strict=True)):
        expected = _chain_hash(prev_hash, payload)
        assert entry["chain_hash_hex"] == expected.hex(), (
            f"Entry {i}: chain_hash mismatch. "
            f"Expected {expected.hex()!r}, got {entry['chain_hash_hex']!r}"
        )
        prev_hash = bytes.fromhex(entry["chain_hash_hex"])


# ---------------------------------------------------------------------------
# 6. Audit chain order — entries returned in creation order
# ---------------------------------------------------------------------------


async def test_audit_chain_order():
    from evidence_mcp.server import append_audit_entry, get_audit_chain

    fid = "55555555-0000-0000-0000-000000000005"
    for i in range(5):
        await append_audit_entry(
            finding_id=fid,
            entry_type="status_change",
            payload={"seq": i},
        )

    result = await get_audit_chain(fid)
    entries = result["entries"]
    assert len(entries) == 5

    # Payload seq values must be in ascending order.
    seqs = [json.loads(e["payload"])["seq"] for e in entries]
    assert seqs == sorted(seqs)


# ---------------------------------------------------------------------------
# 6b. Concurrent append must not fork the chain
# ---------------------------------------------------------------------------


async def test_audit_chain_concurrent_appends_do_not_fork():
    """N concurrent appends to the same finding_id must produce a single
    linear chain (no two entries sharing the same prev_hash)."""
    import asyncio

    from evidence_mcp.server import append_audit_entry, get_audit_chain

    fid = "77777777-0000-0000-0000-000000000007"
    n = 12

    await asyncio.gather(
        *[
            append_audit_entry(
                finding_id=fid,
                entry_type="oracle_result",
                payload={"seq": i},
            )
            for i in range(n)
        ]
    )

    result = await get_audit_chain(fid)
    entries = result["entries"]
    assert len(entries) == n

    # Each chain_hash must be unique — duplicates indicate a fork.
    chain_hashes = [e["chain_hash_hex"] for e in entries]
    assert len(set(chain_hashes)) == n, "duplicate chain_hash → fork detected"

    # The chain must be reconstructible from genesis: walking forward,
    # each entry's chain_hash equals sha256(prev_chain_hash || payload).
    prev = b""
    for entry in entries:
        payload_dict = json.loads(entry["payload"])
        expected = _chain_hash(prev, payload_dict)
        assert entry["chain_hash_hex"] == expected.hex(), (
            "chain integrity broken under concurrency"
        )
        prev = bytes.fromhex(entry["chain_hash_hex"])


# ---------------------------------------------------------------------------
# 7. put_artifact — path traversal in component rejected
# ---------------------------------------------------------------------------


async def test_put_artifact_traversal_rejected():
    from evidence_mcp.server import put_artifact

    result = await put_artifact(
        finding_id="66666666-0000-0000-0000-000000000006",
        platform="../evil",
        program_handle="acme",
        raw_bytes_b64=_b64(b"bad"),
        oracle_verdict="validated",
        oracle_method="sqli",
    )
    assert result == {"error": "invalid_r2_key"}

    result2 = await put_artifact(
        finding_id="66666666-0000-0000-0000-000000000006",
        platform="hackerone",
        program_handle="acme/../escape",
        raw_bytes_b64=_b64(b"bad"),
        oracle_verdict="validated",
        oracle_method="sqli",
    )
    assert result2 == {"error": "invalid_r2_key"}


# ---------------------------------------------------------------------------
# 8. BlobStore._secure_path blocks traversal
# ---------------------------------------------------------------------------


def test_blob_store_secure_path_blocks_traversal(tmp_path: Path):
    from evidence_mcp.store import BlobStore

    store = BlobStore(tmp_path / "blobs")

    with pytest.raises(ValueError):
        store._secure_path("../outside")

    with pytest.raises(ValueError):
        store._secure_path("a/../../etc/passwd")

    with pytest.raises(ValueError):
        store._secure_path("a/b/../../../etc/shadow")

    # Valid key should not raise.
    valid = store._secure_path("platform/handle/finding/sha256abc123")
    assert valid.is_relative_to(store.evidence_root)
