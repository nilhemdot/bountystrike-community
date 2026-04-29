"""DedupStore — asyncpg-backed Postgres deduplication state."""

from __future__ import annotations

import asyncpg

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS dedup_fingerprints (
    fingerprint_hex  TEXT        PRIMARY KEY,
    platform         TEXT        NOT NULL,
    program_handle   TEXT        NOT NULL,
    vuln_type        TEXT        NOT NULL,
    finding_id       TEXT        NOT NULL,
    first_seen_at    TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""

_INSERT = """
INSERT INTO dedup_fingerprints
    (fingerprint_hex, platform, program_handle, vuln_type, finding_id)
VALUES ($1, $2, $3, $4, $5)
ON CONFLICT (fingerprint_hex) DO NOTHING
RETURNING finding_id, first_seen_at
"""

_LOOKUP = """
SELECT finding_id, first_seen_at
FROM dedup_fingerprints
WHERE fingerprint_hex = $1
"""


class DedupStore:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    @classmethod
    async def create(cls, dsn: str) -> DedupStore:
        pool = await asyncpg.create_pool(dsn.replace("+asyncpg", ""))
        store = cls(pool)
        await store._initialize()
        return store

    async def _initialize(self) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(_CREATE_TABLE)

    async def lookup(self, fingerprint_hex: str) -> dict | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(_LOOKUP, fingerprint_hex)
        if row is None:
            return None
        return {
            "finding_id": row["finding_id"],
            "first_seen_at": row["first_seen_at"].isoformat(),
        }

    async def register(
        self,
        fingerprint_hex: str,
        platform: str,
        program_handle: str,
        vuln_type: str,
        finding_id: str,
    ) -> dict:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(_INSERT, fingerprint_hex, platform, program_handle, vuln_type, finding_id)
        if row is not None:
            return {
                "registered": True,
                "finding_id": row["finding_id"],
                "first_seen_at": row["first_seen_at"].isoformat(),
            }
        # ON CONFLICT DO NOTHING — fetch existing winner
        existing = await self.lookup(fingerprint_hex)
        return {"registered": False, **existing}  # type: ignore[arg-type]

    async def close(self) -> None:
        await self._pool.close()


__all__ = ["DedupStore"]
