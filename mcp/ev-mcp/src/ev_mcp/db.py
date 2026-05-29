# SPDX-License-Identifier: AGPL-3.0-or-later

"""Postgres loader for :class:`ProgramFeatures`.

Queries the canonical ``programs`` + ``scopes`` tables (per
``infra/sql/01_schema.sql``) and materializes the typed value objects
``score_program`` consumes.

We deliberately keep this module decoupled from any specific connection
pool — the loader takes either a single ``asyncpg.Connection`` or a
``Pool``, and the server owns the lifecycle. That keeps tests cheap
(no pool needed) and lets the orchestrator inject its own pool when
co-located with the control-plane app.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Protocol

from control_plane.domains.program_ranking.value_objects import ProgramFeatures


class _ConnLike(Protocol):
    """Minimal asyncpg surface — anything with these methods is fine."""

    async def fetch(self, query: str, *args, **kwargs) -> list: ...
    async def fetchrow(self, query: str, *args, **kwargs): ...


_PROGRAM_COLUMNS = (
    "handle, platform, "
    "COALESCE(payout_min, 0) AS payout_min, "
    "COALESCE(payout_max, 0) AS payout_max, "
    "COALESCE(bounty_paid_ratio, 0) AS bounty_paid_ratio, "
    "COALESCE(triage_acceptance_rate, 0) AS triage_acceptance_rate, "
    "COALESCE(dup_rate, 0) AS dup_rate, "
    "last_modified_at"
)


class ProgramFeatureLoader:
    """Materialize :class:`ProgramFeatures` from the canonical tables."""

    async def list_features(
        self,
        conn: _ConnLike,
        platforms: Iterable[str] | None = None,
        require_bounty: bool = False,
    ) -> list[ProgramFeatures]:
        """Load ``ProgramFeatures`` for every matching program.

        Args:
            conn: An asyncpg ``Connection`` (or compatible mock).
            platforms: Restrict to specific platform handles
                (e.g. ``["hackerone", "immunefi"]``). ``None`` = all.
            require_bounty: When ``True``, drop programs whose
                ``payout_max`` is zero — useful for ranker callers
                that only want paying programs.
        """
        platform_list = list(platforms) if platforms is not None else None

        where_clauses: list[str] = []
        params: list = []
        if platform_list:
            where_clauses.append(f"platform = ANY(${len(params) + 1})")
            params.append(platform_list)
        if require_bounty:
            where_clauses.append("COALESCE(payout_max, 0) > 0")
        where = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        program_rows = await conn.fetch(
            f"SELECT {_PROGRAM_COLUMNS} FROM programs {where}",
            *params,
        )
        if not program_rows:
            return []

        handles = [r["handle"] for r in program_rows]
        scope_rows = await conn.fetch(
            """
            SELECT program_handle, asset_type, COUNT(*) AS n
            FROM scopes
            WHERE program_handle = ANY($1)
              AND in_scope = TRUE
            GROUP BY program_handle, asset_type
            """,
            handles,
        )
        distribution: dict[str, dict[str, int]] = {}
        for row in scope_rows:
            distribution.setdefault(row["program_handle"], {})[
                row["asset_type"]
            ] = int(row["n"])

        return [_row_to_features(row, distribution.get(row["handle"], {}))
                for row in program_rows]

    async def get_features(
        self,
        conn: _ConnLike,
        handle: str,
    ) -> ProgramFeatures | None:
        """Load one program's features. Returns ``None`` for unknown handles."""
        if not handle:
            return None
        program_row = await conn.fetchrow(
            f"SELECT {_PROGRAM_COLUMNS} FROM programs WHERE handle = $1",
            handle,
        )
        if program_row is None:
            return None
        scope_rows = await conn.fetch(
            """
            SELECT asset_type, COUNT(*) AS n
            FROM scopes
            WHERE program_handle = $1 AND in_scope = TRUE
            GROUP BY asset_type
            """,
            handle,
        )
        distribution = {row["asset_type"]: int(row["n"]) for row in scope_rows}
        return _row_to_features(program_row, distribution)


def _row_to_features(
    row, distribution: dict[str, int]
) -> ProgramFeatures:
    last_mod = row["last_modified_at"]
    if last_mod is not None and not isinstance(last_mod, datetime):
        last_mod = datetime.fromisoformat(str(last_mod))
    return ProgramFeatures(
        handle=row["handle"],
        platform=row["platform"],
        payout_min=float(row["payout_min"] or 0.0),
        payout_max=float(row["payout_max"] or 0.0),
        bounty_paid_ratio=float(row["bounty_paid_ratio"] or 0.0),
        triage_acceptance_rate=float(row["triage_acceptance_rate"] or 0.0),
        dup_rate=float(row["dup_rate"] or 0.0),
        last_modified_at=last_mod,
        asset_distribution=distribution,
    )


__all__ = ["ProgramFeatureLoader"]
