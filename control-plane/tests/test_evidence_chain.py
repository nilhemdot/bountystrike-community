"""Tests for evidence_management bounded context."""

from __future__ import annotations

import hashlib
import uuid
from unittest.mock import AsyncMock, MagicMock

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
from control_plane.domains.evidence_management.repositories import (
    BlobStore,
    LocalFsBlobStore,
    R2BlobStore,
)
from control_plane.domains.evidence_management.services import HashChainService
from control_plane.domains.evidence_management.value_objects import (
    ContentHash,
    OracleData,
    R2Key,
)

_PLATFORM = "hackerone"
_HANDLE = "acme-corp"


def _txn_mock() -> MagicMock:
    """Return a MagicMock whose call result is an async context manager."""
    txn = MagicMock()
    txn.__aenter__ = AsyncMock(return_value=None)
    txn.__aexit__ = AsyncMock(return_value=False)
    transaction_factory = MagicMock(return_value=txn)
    return transaction_factory


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
    conn.transaction = _txn_mock()
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
    # Two execute calls: advisory lock + INSERT.
    assert conn.execute.await_count == 2


async def test_hash_chain_service_advisory_lock_taken_first(tmp_path):
    """append_entry must acquire pg_advisory_xact_lock BEFORE reading chain head."""
    finding_id = uuid.uuid4()
    conn = AsyncMock()
    conn.transaction = _txn_mock()
    conn.fetchval.return_value = None

    call_order: list[str] = []

    async def record_execute(sql, *args, **kwargs):
        call_order.append("execute:lock" if "advisory" in sql else "execute:insert")

    async def record_fetchval(sql, *args, **kwargs):
        call_order.append("fetchval:head")
        return None

    conn.execute.side_effect = record_execute
    conn.fetchval.side_effect = record_fetchval

    service = HashChainService()
    await service.append_entry(
        finding_id=finding_id,
        entry_type="submission",
        payload={"k": "v"},
        conn=conn,
    )

    # Lock must come first, then chain-head read, then insert.
    assert call_order == ["execute:lock", "fetchval:head", "execute:insert"]
    conn.transaction.assert_called_once()


# ---------------------------------------------------------------------------
# 7. BlobStore Protocol + R2 stub
# ---------------------------------------------------------------------------


def test_local_fs_blob_store_satisfies_protocol(tmp_path):
    """LocalFsBlobStore must structurally satisfy the BlobStore Protocol."""
    store = LocalFsBlobStore(tmp_path)
    assert isinstance(store, BlobStore)


def test_r2_blob_store_rejects_empty_bucket():
    """Defence: empty bucket name is silently broken in S3 — fail loud."""
    with pytest.raises(ValueError, match="bucket"):
        R2BlobStore(
            bucket="",
            endpoint_url=None,
            access_key_id="x",
            secret_access_key="y",
        )


def test_r2_blob_store_satisfies_protocol():
    """R2BlobStore must structurally satisfy the BlobStore Protocol."""
    store = R2BlobStore(
        bucket="evidence",
        endpoint_url="https://example.invalid",
        access_key_id="x",
        secret_access_key="y",
    )
    assert isinstance(store, BlobStore)


def test_r2_blob_store_from_env_derives_endpoint(monkeypatch: pytest.MonkeyPatch):
    """from_env must derive the R2 endpoint from R2_ACCOUNT_ID."""
    monkeypatch.setenv("R2_BUCKET", "evidence")
    monkeypatch.setenv("R2_ACCOUNT_ID", "abc123")
    monkeypatch.setenv("R2_ACCESS_KEY_ID", "k")
    monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "s")
    monkeypatch.delenv("R2_ENDPOINT_URL", raising=False)

    store = R2BlobStore.from_env()
    assert store._bucket == "evidence"
    assert store._endpoint_url == "https://abc123.r2.cloudflarestorage.com"


def test_r2_blob_store_from_env_endpoint_override(monkeypatch: pytest.MonkeyPatch):
    """R2_ENDPOINT_URL must take precedence over derived endpoint."""
    monkeypatch.setenv("R2_BUCKET", "evidence")
    monkeypatch.setenv("R2_ACCOUNT_ID", "abc123")
    monkeypatch.setenv("R2_ACCESS_KEY_ID", "k")
    monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "s")
    monkeypatch.setenv("R2_ENDPOINT_URL", "https://localhost:9000")

    store = R2BlobStore.from_env()
    assert store._endpoint_url == "https://localhost:9000"


# ---------------------------------------------------------------------------
# 8. R2BlobStore — round-trip against in-memory fake S3 client
# ---------------------------------------------------------------------------
#
# moto + aioboto3 are incompatible at the time of writing: moto returns
# response bodies as ``bytes`` while aiobotocore awaits them, raising
# ``TypeError: 'bytes' object can't be awaited``. We instead inject a tiny
# in-memory S3 client that satisfies the subset of the API our store uses
# (put_object / get_object / head_object). This tests both the call shape
# and the round-trip semantics without external infrastructure.


class _FakeStreamingBody:
    """Mimics the ``Body`` field of an S3 GetObject response."""

    def __init__(self, data: bytes) -> None:
        self._data = data

    async def __aenter__(self) -> _FakeStreamingBody:
        return self

    async def __aexit__(self, *_: object) -> bool:
        return False

    async def read(self) -> bytes:
        return self._data


class _FakeClientError(Exception):
    """Mirror of botocore.exceptions.ClientError shape we touch."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.response = {"Error": {"Code": code}}


class _FakeS3Client:
    """In-memory dict-backed S3 client. Supports just what R2BlobStore calls."""

    def __init__(self, storage: dict[tuple[str, str], bytes]) -> None:
        self._storage = storage
        self.exceptions = type(
            "_Exceptions", (), {"ClientError": _FakeClientError}
        )()

    async def __aenter__(self) -> _FakeS3Client:
        return self

    async def __aexit__(self, *_: object) -> bool:
        return False

    # boto3-style PascalCase kwargs mirror the real S3 client surface.
    async def put_object(
        self,
        *,
        Bucket: str,  # noqa: N803 — mirrors boto3 API
        Key: str,  # noqa: N803
        Body: bytes,  # noqa: N803
    ) -> dict:
        self._storage[(Bucket, Key)] = Body
        return {}

    async def get_object(self, *, Bucket: str, Key: str) -> dict:  # noqa: N803
        if (Bucket, Key) not in self._storage:
            raise _FakeClientError("NoSuchKey")
        return {"Body": _FakeStreamingBody(self._storage[(Bucket, Key)])}

    async def head_object(self, *, Bucket: str, Key: str) -> dict:  # noqa: N803
        if (Bucket, Key) not in self._storage:
            raise _FakeClientError("404")
        return {}

    async def delete_object(self, *, Bucket: str, Key: str) -> dict:  # noqa: N803
        # S3 DeleteObject is idempotent — succeeds whether the key existed.
        self._storage.pop((Bucket, Key), None)
        return {}


@pytest.fixture
def fake_r2_store(monkeypatch: pytest.MonkeyPatch):
    """Replace aioboto3.Session.client with a fake returning _FakeS3Client."""
    storage: dict[tuple[str, str], bytes] = {}

    def fake_client(self, *_args, **_kwargs):
        return _FakeS3Client(storage)

    import aioboto3

    monkeypatch.setattr(aioboto3.Session, "client", fake_client)

    return R2BlobStore(
        bucket="evidence",
        endpoint_url="https://fake.invalid",
        access_key_id="k",
        secret_access_key="s",
    )


def _r2_key(finding_id: uuid.UUID, payload: bytes) -> R2Key:
    return R2Key.compute(_PLATFORM, _HANDLE, finding_id, ContentHash.from_bytes(payload))


async def test_r2_blob_store_put_get_roundtrip(fake_r2_store):
    raw = b"binary-payload-12345"
    key = _r2_key(uuid.uuid4(), raw)

    assert await fake_r2_store.exists(key) is False
    await fake_r2_store.put(key, raw)
    assert await fake_r2_store.exists(key) is True
    assert await fake_r2_store.get(key) == raw


async def test_r2_blob_store_put_idempotent(fake_r2_store):
    """Same bytes written twice → key resolves to last body (S3 semantics)."""
    raw = b"idempotent-bytes"
    key = _r2_key(uuid.uuid4(), raw)
    await fake_r2_store.put(key, raw)
    await fake_r2_store.put(key, raw)
    assert await fake_r2_store.get(key) == raw


async def test_r2_blob_store_exists_false_for_missing(fake_r2_store):
    key = _r2_key(uuid.uuid4(), b"not-uploaded")
    assert await fake_r2_store.exists(key) is False


async def test_r2_blob_store_get_missing_propagates_client_error(fake_r2_store):
    """get must NOT swallow missing-object errors — caller decides."""
    key = _r2_key(uuid.uuid4(), b"nope")
    with pytest.raises(_FakeClientError):
        await fake_r2_store.get(key)


async def test_r2_blob_store_delete_removes_key(fake_r2_store):
    raw = b"delete-me"
    key = _r2_key(uuid.uuid4(), raw)
    await fake_r2_store.put(key, raw)
    assert await fake_r2_store.exists(key) is True

    await fake_r2_store.delete(key)
    assert await fake_r2_store.exists(key) is False


async def test_r2_blob_store_delete_missing_is_idempotent(fake_r2_store):
    """S3 DeleteObject is idempotent; deleting a missing key must not raise."""
    key = _r2_key(uuid.uuid4(), b"never-uploaded")
    await fake_r2_store.delete(key)  # must not raise
