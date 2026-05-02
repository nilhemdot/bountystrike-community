"""Live Cloudflare R2 round-trip tests for ``R2BlobStore``.

Mocked unit tests (``control-plane/tests/test_evidence_chain.py``) prove
the call shape and the round-trip semantics against an in-memory fake
S3 client. They cannot prove that the user-provided credentials work,
that the endpoint URL derivation matches what Cloudflare actually
serves, or that the ``head_object`` 404 / ``NoSuchKey`` branch fires
against R2's real error envelope.

These tests close that gap. Skipped when ``R2_BUCKET`` is unset so CI
without R2 secrets stays green. To run locally::

    set -a && source .env && set +a
    cd control-plane && uv run pytest ../tests/integration/test_r2_blob_store_live.py -v
"""

from __future__ import annotations

import os
import sys
import uuid

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "control-plane", "src"))

from control_plane.domains.evidence_management.repositories.blob_store import (  # noqa: E402
    R2BlobStore,
)
from control_plane.domains.evidence_management.value_objects import R2Key  # noqa: E402
from control_plane.domains.evidence_management.value_objects.content_hash import (  # noqa: E402
    ContentHash,
)

_R2_BUCKET = os.environ.get("R2_BUCKET", "")
_skip_if_no_r2 = pytest.mark.skipif(
    not _R2_BUCKET,
    reason="R2_BUCKET not set; skipping live-R2 tests",
)


def _smoke_key(payload: bytes) -> R2Key:
    """Build a unique R2Key under the smoke-test program for this run."""
    return R2Key.compute(
        platform="hackerone",
        program_handle="smoke-test",
        finding_id=uuid.uuid4(),
        content_hash=ContentHash.from_bytes(payload),
    )


@pytest.fixture
def store() -> R2BlobStore:
    if not _R2_BUCKET:
        pytest.skip("R2_BUCKET not set")
    return R2BlobStore.from_env()


@pytest.fixture
async def cleanup_keys(store: R2BlobStore):
    """Track keys written during the test and delete them afterwards.

    Tests append the keys they put to the yielded list; teardown deletes
    each one regardless of test outcome so the bucket stays clean even
    when an assertion fails mid-test.
    """
    written: list[R2Key] = []
    try:
        yield written
    finally:
        for key in written:
            try:
                await store.delete(key)
            except Exception:  # noqa: BLE001
                # Cleanup is best-effort; any error here would mask the
                # real test failure if we re-raised.
                pass


@_skip_if_no_r2
async def test_put_get_round_trip_returns_identical_bytes(
    store: R2BlobStore, cleanup_keys: list[R2Key]
) -> None:
    payload = b"bs5-r2-live-" + os.urandom(32)
    key = _smoke_key(payload)
    cleanup_keys.append(key)

    await store.put(key, payload)
    assert await store.exists(key) is True

    got = await store.get(key)
    assert got == payload, (
        f"R2 returned {len(got)} bytes; expected {len(payload)}"
    )


@_skip_if_no_r2
async def test_exists_returns_false_for_missing_key(store: R2BlobStore) -> None:
    """exists() must surface R2's 404 / NoSuchKey envelope as False."""
    key = _smoke_key(b"never-uploaded-" + os.urandom(8))
    assert await store.exists(key) is False


@_skip_if_no_r2
async def test_get_raises_on_missing_key(store: R2BlobStore) -> None:
    """get() must NOT silently return empty bytes when the key is absent."""
    from botocore.exceptions import ClientError

    key = _smoke_key(b"never-uploaded-" + os.urandom(8))
    with pytest.raises(ClientError):
        await store.get(key)


@_skip_if_no_r2
async def test_delete_then_exists_returns_false(
    store: R2BlobStore, cleanup_keys: list[R2Key]
) -> None:
    """delete() must actually remove the key from the live bucket."""
    payload = b"bs5-r2-delete-" + os.urandom(16)
    key = _smoke_key(payload)
    cleanup_keys.append(key)  # belt-and-braces; test also deletes inline

    await store.put(key, payload)
    assert await store.exists(key) is True

    await store.delete(key)
    assert await store.exists(key) is False
