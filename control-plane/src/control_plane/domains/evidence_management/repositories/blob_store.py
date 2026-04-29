from __future__ import annotations

import asyncio
from pathlib import Path

from control_plane.domains.evidence_management.value_objects import R2Key


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


class LocalFsBlobStore:
    """Filesystem-backed blob store for dev/test."""

    def __init__(self, evidence_root: str | Path) -> None:
        self._root = Path(evidence_root)

    async def put(self, r2_key: R2Key, data: bytes) -> None:
        """Write ``data`` to the blob store under ``r2_key``."""
        path = r2_key.under(self._root)
        await asyncio.to_thread(_write, path, data)

    async def get(self, r2_key: R2Key) -> bytes:
        """Read and return bytes stored under ``r2_key``."""
        path = r2_key.under(self._root)
        return await asyncio.to_thread(path.read_bytes)

    async def exists(self, r2_key: R2Key) -> bool:
        """Return True if the blob exists."""
        path = r2_key.under(self._root)
        return await asyncio.to_thread(path.exists)


__all__ = ["LocalFsBlobStore"]
