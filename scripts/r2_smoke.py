#!/usr/bin/env python3
"""1.1f-deploy live R2 round-trip smoke.

Asserts that the credentials in the current environment can put → exists
→ get → delete a small payload through ``R2BlobStore``. Used by the
``r2-smoke`` GitHub Actions workflow and runnable locally after sourcing
``.env``::

    set -a && source .env && set +a
    uv run --frozen python scripts/r2_smoke.py

Exit codes:
    0 — round-trip succeeded; cleanup ran.
    1 — required env vars missing.
    2 — round-trip failed; cleanup attempted.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from datetime import UTC, datetime

sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "..", "control-plane", "src"),
)

from control_plane.domains.evidence_management.repositories.blob_store import (  # noqa: E402
    R2BlobStore,
)
from control_plane.domains.evidence_management.value_objects import R2Key  # noqa: E402
from control_plane.domains.evidence_management.value_objects.content_hash import (  # noqa: E402
    ContentHash,
)

_REQUIRED_ENV = (
    "R2_BUCKET",
    "R2_ACCESS_KEY_ID",
    "R2_SECRET_ACCESS_KEY",
)


def _missing_env() -> list[str]:
    return [name for name in _REQUIRED_ENV if not os.environ.get(name)]


def _emit(event: str, **fields: object) -> None:
    payload = {"event": event, "ts": datetime.now(UTC).isoformat(), **fields}
    print(json.dumps(payload, default=str), flush=True)


async def _round_trip() -> int:
    store = R2BlobStore.from_env()
    payload = b"bs5-r2-smoke-" + os.urandom(16)
    key = R2Key.compute(
        platform="hackerone",
        program_handle="smoke-test",
        finding_id=uuid.uuid4(),
        content_hash=ContentHash.from_bytes(payload),
    )

    _emit("smoke.start", bucket=os.environ["R2_BUCKET"], key=key.key, bytes=len(payload))
    try:
        await store.put(key, payload)
        _emit("smoke.put.ok", key=key.key)

        if not await store.exists(key):
            raise AssertionError(f"exists() returned False after put for {key.key}")
        _emit("smoke.exists.ok", key=key.key)

        got = await store.get(key)
        if got != payload:
            raise AssertionError(
                f"get() returned {len(got)} bytes; expected {len(payload)}"
            )
        _emit("smoke.get.ok", key=key.key, bytes=len(got))
        return 0
    finally:
        # Always attempt cleanup, even if the round-trip raised — leaving
        # smoke artifacts in a real bucket is the worst failure mode.
        try:
            await store.delete(key)
            _emit("smoke.delete.ok", key=key.key)
        except Exception as cleanup_err:  # noqa: BLE001
            _emit("smoke.delete.fail", key=key.key, error=repr(cleanup_err))


def main() -> int:
    missing = _missing_env()
    if missing:
        _emit("smoke.env.missing", missing=missing)
        return 1
    try:
        return asyncio.run(_round_trip())
    except Exception as err:  # noqa: BLE001
        _emit("smoke.fail", error=repr(err))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
