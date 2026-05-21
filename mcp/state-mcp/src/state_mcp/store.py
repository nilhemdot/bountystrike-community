"""StateStore — read/write API over the findings + evidence_artifacts schema.

Why an MCP wrapper exists at all when ``findings`` is a simple Postgres
table: subagents are written in markdown and have no DB driver. Exposing
typed read/write tools through MCP keeps every state mutation behind an
audit-loggable boundary, and lets the orchestrator inject a different
backend (e.g. test in-memory store) without touching agent code.

This module is the persistence layer; ``server.py`` wraps each method as
a FastMCP tool.
"""

from __future__ import annotations

from collections.abc import Sequence

import asyncpg

# Subset of `finding_status` ENUM values we actively transition between.
# Loaded from infra/sql/01_schema.sql:16. Kept here for runtime validation;
# Postgres rejects unknown values regardless, but failing in-process gives
# a clearer error.
FINDING_STATUSES: frozenset[str] = frozenset({
    "hypothesis",
    "exploit_attempt",
    "exploit_candidate",
    "validation_pending",
    "validated",
    "dedup_check",
    "approval_pending_t1",
    "approval_pending_t2",
    "approval_pending_t3",
    "approved",
    "submitted",
    "confirmed",
    "rejected",
    "duplicate",
    "wont_fix",
    "archived",
})


def _strip_asyncpg_driver(dsn: str) -> str:
    """Strip the SQLAlchemy ``+asyncpg`` driver suffix from the scheme.

    asyncpg's ``create_pool`` accepts ``postgresql://`` but not the
    SQLAlchemy-style ``postgresql+asyncpg://``. Naive substring replace
    on the full DSN would also corrupt a password literal containing
    the ``+asyncpg`` substring (hypothetical, but defensive). Parse the
    scheme portion explicitly so only the driver suffix is touched.
    """
    if "://" not in dsn:
        return dsn
    scheme, rest = dsn.split("://", 1)
    if "+" in scheme:
        base, suffix = scheme.split("+", 1)
        if suffix.lower() == "asyncpg":
            scheme = base
    return f"{scheme}://{rest}"


class StateStore:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    @classmethod
    async def create(cls, dsn: str) -> StateStore:
        pool = await asyncpg.create_pool(_strip_asyncpg_driver(dsn))
        return cls(pool)

    async def close(self) -> None:
        await self._pool.close()

    # ---------------------------------------------------------------------
    # Read API
    # ---------------------------------------------------------------------

    async def get_finding(self, finding_id: str) -> dict | None:
        sql = """
            SELECT id, job_id, program_handle, platform, cwe, url, parameter,
                   status::text AS status, evidence_hash, oracle_method,
                   validator_model, deduplication_key, created_at, updated_at
            FROM findings
            WHERE id = $1::uuid
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(sql, finding_id)
        if row is None:
            return None
        return _row_to_dict(row)

    async def query_artifacts(self, finding_id: str) -> list[dict]:
        sql = """
            SELECT id, finding_id, content_hash, prev_audit_hash,
                   oracle_data, reproduction_command,
                   scope_token_jti, sandbox_vm_id, r2_key, created_at
            FROM evidence_artifacts
            WHERE finding_id = $1::uuid
            ORDER BY created_at ASC
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(sql, finding_id)
        return [_row_to_dict(r) for r in rows]

    async def query_experience_kb(
        self,
        cwe: str,
        product: str | None = None,
        version: str | None = None,
        limit: int = 10,
    ) -> list[dict]:
        """Find prior validated exploits matching a tech triple.

        Used by exploit-agent (build-plan §2.3.6 chain detection) to
        reuse a known-good chain template instead of regenerating from
        scratch.

        Match semantics:
          - Always filter ``cwe`` exact match.
          - ``product`` / ``version`` filter the URL field via ILIKE
            with LIKE-metacharacters in caller input ESCAPED so a
            caller cannot inject ``%`` / ``_`` to broaden the match.
          - Status restricted to ``validated`` / ``confirmed`` /
            ``submitted`` so we never recommend a chain that the
            validator later rejected.

        **Known limitation** (audit reviewer 3, MEDIUM): the matcher
        is a URL substring proxy because the schema does not yet have
        dedicated tech-stack columns. ``product=wordpress version=6.4``
        will match any URL containing both substrings in order, e.g.
        ``https://wordpress.com/blog/2024/06/04/foo`` (false-match).
        Tracked for a follow-up that adds a tech-stack JSONB column
        to ``findings`` and switches this query to a precise-key match.
        """
        statuses: tuple[str, ...] = ("validated", "confirmed", "submitted")
        if product and version:
            # ESCAPE clause + escape caller input so callers can't
            # inject LIKE metacharacters to widen the match.
            sql = """
                SELECT id, cwe, oracle_method, evidence_hash, url, parameter,
                       status::text AS status, program_handle
                FROM findings
                WHERE cwe = $1
                  AND status::text = ANY($2::text[])
                  AND url ILIKE $3 ESCAPE '\\'
                ORDER BY updated_at DESC
                LIMIT $4
            """
            pattern = f"%{_escape_like(product)}%{_escape_like(version)}%"
            args: tuple = (cwe, list(statuses), pattern, int(limit))
        elif product:
            sql = """
                SELECT id, cwe, oracle_method, evidence_hash, url, parameter,
                       status::text AS status, program_handle
                FROM findings
                WHERE cwe = $1
                  AND status::text = ANY($2::text[])
                  AND url ILIKE $3 ESCAPE '\\'
                ORDER BY updated_at DESC
                LIMIT $4
            """
            args = (cwe, list(statuses), f"%{_escape_like(product)}%", int(limit))
        else:
            sql = """
                SELECT id, cwe, oracle_method, evidence_hash, url, parameter,
                       status::text AS status, program_handle
                FROM findings
                WHERE cwe = $1
                  AND status::text = ANY($2::text[])
                ORDER BY updated_at DESC
                LIMIT $3
            """
            args = (cwe, list(statuses), int(limit))
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(sql, *args)
        return [_row_to_dict(r) for r in rows]

    # ---------------------------------------------------------------------
    # Write API
    # ---------------------------------------------------------------------

    async def update_finding_status(
        self,
        finding_id: str,
        new_status: str,
        expected_current_status: str | None = None,
    ) -> dict:
        """Transition a finding's status, optionally with optimistic lock.

        ``expected_current_status`` is the optimistic-lock guard pattern
        used by validator-agent (claim-then-process). When provided, the
        UPDATE only fires if the current status equals it; ``updated``
        comes back False on mismatch and the caller defers.

        Returns ``{updated, finding_id, status, prior_status?}``.
        """
        if new_status not in FINDING_STATUSES:
            raise ValueError(f"unknown finding_status {new_status!r}")
        if (
            expected_current_status is not None
            and expected_current_status not in FINDING_STATUSES
        ):
            raise ValueError(
                f"unknown expected_current_status {expected_current_status!r}"
            )
        if expected_current_status is None:
            sql = """
                UPDATE findings
                SET status = $1::finding_status, updated_at = now()
                WHERE id = $2::uuid
                RETURNING status::text AS status
            """
            args: Sequence = (new_status, finding_id)
        else:
            sql = """
                UPDATE findings
                SET status = $1::finding_status, updated_at = now()
                WHERE id = $2::uuid
                  AND status::text = $3
                RETURNING status::text AS status
            """
            args = (new_status, finding_id, expected_current_status)
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(sql, *args)
            if row is None:
                # Optimistic-lock UPDATE returned 0 rows. Distinguish
                # "row does not exist" from "row exists but status
                # mismatched the expectation" — both used to surface
                # as the same ``updated=False`` shape, leaving the
                # caller unable to tell whether it raced another
                # worker or was handed a bad finding_id.
                #
                # The follow-up SELECT runs on the same connection so
                # there is no extra acquire / round-trip cost beyond
                # a single query.
                exists_row = await conn.fetchrow(
                    "SELECT status::text AS status FROM findings WHERE id = $1::uuid",
                    finding_id,
                )
        if row is None:
            current_status = (
                exists_row["status"] if exists_row is not None else None
            )
            return {
                "updated": False,
                "finding_id": finding_id,
                "status": current_status,
                "finding_exists": exists_row is not None,
                "reason": (
                    "row_missing"
                    if exists_row is None
                    else "expected_status_mismatch"
                ),
            }
        return {
            "updated": True,
            "finding_id": finding_id,
            "status": row["status"],
            "finding_exists": True,
            "reason": "ok",
        }


def _escape_like(s: str) -> str:
    """Escape Postgres ILIKE metacharacters in caller-supplied input.

    Without this, a caller passing ``product='_'`` matches every
    single-character substring in the URL (every URL); ``%`` matches
    any substring. Both are widening attacks against the
    experience-KB query: not SQL injection (asyncpg binds the
    parameter), but they expand the match scope past the caller's
    intent. Used together with ``ESCAPE '\\'`` clause in the SQL.
    """
    return (
        s.replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )


def _row_to_dict(row: asyncpg.Record) -> dict:
    """Convert asyncpg.Record to a plain dict with stringified UUID/datetime."""
    out: dict = {}
    for k, v in dict(row).items():
        if hasattr(v, "isoformat"):  # datetime
            out[k] = v.isoformat()
        elif isinstance(v, bytes):
            out[k] = v.hex()
        else:
            try:
                # uuid.UUID is not isinstance-checkable cheaply; str() is safe.
                if hasattr(v, "hex") and not isinstance(v, (bytes, bytearray, str, int, float)):
                    out[k] = str(v)
                else:
                    out[k] = v
            except Exception:
                out[k] = str(v)
    return out


__all__ = ["FINDING_STATUSES", "StateStore"]
