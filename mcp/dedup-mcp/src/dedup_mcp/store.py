# SPDX-License-Identifier: AGPL-3.0-or-later

"""DedupStore — asyncpg-backed Postgres deduplication state."""

from __future__ import annotations

from collections.abc import Sequence

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
            row = await conn.fetchrow(
                _INSERT, fingerprint_hex, platform, program_handle, vuln_type, finding_id
            )
        if row is not None:
            return {
                "registered": True,
                "finding_id": row["finding_id"],
                "first_seen_at": row["first_seen_at"].isoformat(),
            }
        # ON CONFLICT DO NOTHING — fetch existing winner
        existing = await self.lookup(fingerprint_hex)
        return {"registered": False, **existing}  # type: ignore[arg-type]

    async def semantic_search(
        self,
        embedding: Sequence[float],
        program_handle: str,
        threshold: float = 0.75,
        limit: int = 10,
        exclude_statuses: Sequence[str] = ("archived", "rejected", "duplicate"),
    ) -> list[dict]:
        """Return the top-N findings whose cosine similarity ≥ ``threshold``.

        Uses pgvector ``<=>`` (cosine distance). Similarity = 1 - distance.

        Args:
            embedding: 1536-dim float list for the new finding.
            program_handle: scope semantic match to a single program.
            threshold: minimum cosine similarity (default 0.75 = display set).
            limit: cap result rows.
            exclude_statuses: skip findings already archived / rejected /
                marked duplicate so we never recommend a non-canonical row
                as the parent of a new dup chain.

        Returns:
            List of ``{finding_id, cwe, similarity}`` dicts ordered by
            similarity DESC. Empty list if no matches above threshold.
        """
        # asyncpg expects a string of the form '[0.1,0.2,...]' for vector
        # binding when no codec is registered; pgvector's text format is
        # bracketed comma-separated.
        vec_text = "[" + ",".join(repr(float(v)) for v in embedding) + "]"
        sql = """
            SELECT id, cwe, 1 - (embedding <=> $1::vector) AS similarity
            FROM findings
            WHERE program_handle = $2
              AND embedding IS NOT NULL
              AND status::text <> ALL($3::text[])
              AND 1 - (embedding <=> $1::vector) >= $4
            ORDER BY embedding <=> $1::vector ASC
            LIMIT $5
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                sql,
                vec_text,
                program_handle,
                list(exclude_statuses),
                float(threshold),
                int(limit),
            )
        return [
            {
                "finding_id": str(r["id"]),
                "cwe": r["cwe"],
                "similarity": float(r["similarity"]),
            }
            for r in rows
        ]

    async def store_embedding(self, finding_id: str, embedding: Sequence[float]) -> None:
        """Persist the embedding column for a finding row.

        Called by ``register_finding_semantic`` after the row exists. Idempotent:
        overwrites prior embedding (re-embedding after edits is a valid flow).
        """
        vec_text = "[" + ",".join(repr(float(v)) for v in embedding) + "]"
        sql = "UPDATE findings SET embedding = $1::vector, updated_at = now() WHERE id = $2::uuid"
        async with self._pool.acquire() as conn:
            await conn.execute(sql, vec_text, finding_id)

    async def close(self) -> None:
        await self._pool.close()


__all__ = ["DedupStore"]
