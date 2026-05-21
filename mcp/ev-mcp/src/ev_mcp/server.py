"""FastMCP server for ev-mcp.

Exposes the two tools named in build-plan §4.x for ev-mcp:

* ``rank_programs(operator_profile, ...)``
* ``get_program_details(program_handle, operator_profile=None)``

The scoring math itself is imported from
:mod:`control_plane.domains.program_ranking` so any tweak to the EV
formula propagates without touching this server.
"""

from __future__ import annotations

import os
from typing import Any, cast

import asyncpg
import structlog
from control_plane.domains.program_ranking.services.scoring_service import (
    rank_programs as _rank_programs_internal,
    score_program,
)
from control_plane.domains.program_ranking.value_objects import (
    OperatorProfile,
    ProgramFeatures,
)
from mcp.server.fastmcp import FastMCP

from .db import ProgramFeatureLoader, _ConnLike

log = structlog.get_logger("ev_mcp.server")


# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------

DEFAULT_DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://bs:bs@127.0.0.1:5432/bountystrike"
)

loader = ProgramFeatureLoader()
_pool: asyncpg.Pool | None = None


async def _get_pool() -> asyncpg.Pool:
    """Lazy-build the asyncpg pool, swappable in tests via attribute set."""
    global _pool
    if _pool is None:
        dsn = DEFAULT_DATABASE_URL.replace("+asyncpg", "")
        _pool = await asyncpg.create_pool(dsn, min_size=1, max_size=5)
    return _pool


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _operator_profile_from_dict(raw: dict[str, Any] | None) -> OperatorProfile:
    raw = raw or {}
    return OperatorProfile(
        skill_vector=dict(raw.get("skill_vector") or {}),
        time_budget_hours=float(raw.get("time_budget_hours") or 40.0),
        cost_budget_usd=float(raw.get("cost_budget_usd") or 50.0),
        asset_type_pref=dict(raw.get("asset_type_pref") or {}),
    )


def _features_to_summary(features: ProgramFeatures) -> dict[str, Any]:
    return {
        "handle": features.handle,
        "platform": features.platform,
        "payout_min": features.payout_min,
        "payout_max": features.payout_max,
        "bounty_paid_ratio": features.bounty_paid_ratio,
        "triage_acceptance_rate": features.triage_acceptance_rate,
        "dup_rate": features.dup_rate,
        "last_modified_at": (
            features.last_modified_at.isoformat()
            if features.last_modified_at is not None
            else None
        ),
        "asset_distribution": dict(features.asset_distribution),
    }


# ---------------------------------------------------------------------------
# FastMCP server
# ---------------------------------------------------------------------------

mcp = FastMCP("ev-mcp")


@mcp.tool()
async def rank_programs(
    operator_profile: dict[str, Any] | None = None,
    min_ev_score: float = 0.0,
    platforms: list[str] | None = None,
    require_bounty: bool = False,
    limit: int = 25,
) -> dict[str, Any]:
    """Return the top *limit* programs by EV score for the given operator.

    Args:
        operator_profile: Operator skill + budget profile. Shape::

            {
              "skill_vector": {str: float},
              "time_budget_hours": float,         # default 40
              "cost_budget_usd":   float,         # default 50
              "asset_type_pref":  {str: float}
            }

        min_ev_score: Drop programs whose computed EV is below this.
        platforms: Restrict to specific bug-bounty platforms.
        require_bounty: Drop programs without a positive ``payout_max``.
        limit: Cap the result set; clamped to ``[1, 200]``.

    Returns:
        ``{"count": int, "limit": int, "results": [...]}`` where each
        result is::

            {
              "rank":        int,
              "program":     <_features_to_summary>,
              "score":       <ScoreBreakdown.dict>
            }

        Sorted by ``score.ev_score`` descending.
    """
    if limit < 1:
        return {"error": "limit must be >= 1", "count": 0, "results": []}
    limit = min(limit, 200)

    operator = _operator_profile_from_dict(operator_profile)

    pool = await _get_pool()
    async with pool.acquire() as conn:
        features_list = await loader.list_features(
            cast(_ConnLike, conn),
            platforms=platforms,
            require_bounty=require_bounty,
        )

    ranked = _rank_programs_internal(
        features_list, operator, top_n=limit
    )

    by_handle = {f.handle: f for f in features_list}
    results: list[dict[str, Any]] = []
    for rank, (handle, breakdown) in enumerate(ranked, start=1):
        if breakdown.ev_score < min_ev_score:
            continue
        feat = by_handle.get(handle)
        if feat is None:
            continue
        results.append({
            "rank": rank,
            "program": _features_to_summary(feat),
            "score": breakdown.model_dump(),
        })

    log.info(
        "ev.rank_programs",
        candidates=len(features_list),
        returned=len(results),
        platforms=platforms,
        min_ev_score=min_ev_score,
    )
    return {
        "count": len(results),
        "limit": limit,
        "results": results,
    }


@mcp.tool()
async def get_program_details(
    program_handle: str,
    operator_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return one program's signals + EV score for the given operator.

    Args:
        program_handle: Platform program handle (e.g. ``"acme-corp"``).
        operator_profile: Operator profile (see :func:`rank_programs`).
            When omitted, scoring uses an empty profile so callers can
            still see the program signals + a zero-fit baseline EV.

    Returns:
        ``{"program": ..., "score": ...}`` or ``{"error": "not_found"}``.
    """
    if not program_handle or not program_handle.strip():
        return {"error": "program_handle is required"}

    pool = await _get_pool()
    async with pool.acquire() as conn:
        features = await loader.get_features(cast(_ConnLike, conn), program_handle)

    if features is None:
        return {"error": "not_found", "program_handle": program_handle}

    operator = _operator_profile_from_dict(operator_profile)
    breakdown = score_program(features, operator)

    return {
        "program": _features_to_summary(features),
        "score": breakdown.model_dump(),
    }


def main() -> None:
    """Run the ev-mcp FastMCP server (stdio transport)."""
    mcp.run()


if __name__ == "__main__":
    main()
