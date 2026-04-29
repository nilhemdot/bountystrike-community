"""Storage backends for evidence artifacts and hash-chained audit logs.

BlobStore  — content-addressed blob storage on disk.
AuditStore — SQLite-backed hash-chained audit log via aiosqlite.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import aiosqlite


class BlobStore:
    """Stores raw artifact bytes on disk using a hierarchical key layout."""

    def __init__(self, evidence_root: Path) -> None:
        self.evidence_root = evidence_root.resolve()
        self.evidence_root.mkdir(parents=True, exist_ok=True)

    def _secure_path(self, r2_key: str) -> Path:
        """Resolve a key to an absolute path, rejecting directory traversal.

        Splits *r2_key* on '/' and joins parts one-by-one so the OS never
        interprets raw path separators in a single component.  Raises
        ``ValueError`` if the resolved path escapes *evidence_root*.
        """
        parts = r2_key.split("/")
        # Reject empty segments or any component that is a traversal marker.
        for part in parts:
            if not part or part == "..":
                raise ValueError(f"Unsafe r2_key component: {part!r}")
        candidate = self.evidence_root.joinpath(*parts).resolve()
        if not candidate.is_relative_to(self.evidence_root):
            raise ValueError(f"r2_key escapes evidence root: {r2_key!r}")
        return candidate

    async def put(self, r2_key: str, data: bytes) -> None:
        """Write *data* to the path derived from *r2_key*."""
        path = self._secure_path(r2_key)
        await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, data)

    async def get(self, r2_key: str) -> bytes | None:
        """Return the bytes stored at *r2_key*, or ``None`` if not found."""
        try:
            path = self._secure_path(r2_key)
        except ValueError:
            return None
        if not await asyncio.to_thread(path.exists):
            return None
        return await asyncio.to_thread(path.read_bytes)

    async def exists(self, r2_key: str) -> bool:
        """Return ``True`` if *r2_key* is present in the store."""
        try:
            path = self._secure_path(r2_key)
        except ValueError:
            return False
        return await asyncio.to_thread(path.exists)


class AuditStore:
    """SQLite-backed audit log with SHA-256 hash chaining per finding."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)

    async def initialize(self) -> None:
        """Create the audit_log table if it does not already exist."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_log (
                    id          TEXT NOT NULL,
                    finding_id  TEXT NOT NULL,
                    entry_type  TEXT NOT NULL,
                    payload     TEXT NOT NULL,
                    prev_hash   BLOB NOT NULL,
                    chain_hash  BLOB NOT NULL,
                    created_at  TEXT NOT NULL
                )
                """
            )
            await db.commit()

    async def get_latest_chain_hash(self, finding_id: str) -> bytes:
        """Return the most recent chain_hash for *finding_id*, or ``b''`` for genesis."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT chain_hash FROM audit_log "
                "WHERE finding_id = ? "
                "ORDER BY created_at DESC, id DESC "
                "LIMIT 1",
                (finding_id,),
            ) as cursor:
                row = await cursor.fetchone()
        return row[0] if row else b""

    async def append(
        self,
        id: str,
        finding_id: str,
        entry_type: str,
        payload: str,
        prev_hash: bytes,
        chain_hash: bytes,
        created_at: str,
    ) -> None:
        """Insert a new audit log entry."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO audit_log "
                "(id, finding_id, entry_type, payload, prev_hash, chain_hash, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (id, finding_id, entry_type, payload, prev_hash, chain_hash, created_at),
            )
            await db.commit()

    async def get_chain(self, finding_id: str) -> list[dict]:
        """Return all audit entries for *finding_id* ordered by creation time."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT id, entry_type, payload, chain_hash, created_at "
                "FROM audit_log "
                "WHERE finding_id = ? "
                "ORDER BY created_at ASC, id ASC",
                (finding_id,),
            ) as cursor:
                rows = await cursor.fetchall()
        return [
            {
                "id": row[0],
                "entry_type": row[1],
                "payload_json": row[2],
                "chain_hash_hex": row[3].hex(),
                "created_at": row[4],
            }
            for row in rows
        ]
