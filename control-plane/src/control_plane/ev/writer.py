"""Persistence layer for ev_score_history (only file in this package with DB calls).

Mirrors infra/sql/01_schema.sql:ev_score_history columns exactly:
    id (autoincrement) | program_handle | computed_at | ev_score
    f_payout | f_saturation | f_ops | f_fit | f_cve
    weights_version | computed_for_operator
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    desc,
    insert,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession

from .scoring import ScoreBreakdown

metadata = MetaData()

ev_score_history = Table(
    "ev_score_history",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("program_handle", String, nullable=False),
    Column(
        "computed_at",
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    ),
    Column("ev_score", Numeric(6, 4), nullable=False),
    Column("f_payout", Numeric(6, 4)),
    Column("f_saturation", Numeric(6, 4)),
    Column("f_ops", Numeric(6, 4)),
    Column("f_fit", Numeric(6, 4)),
    Column("f_cve", Numeric(6, 4)),
    Column("weights_version", String),
    Column("computed_for_operator", String),
)


async def write_ev_score(
    session: AsyncSession,
    program_handle: str,
    breakdown: ScoreBreakdown,
    operator_id: str | None,
) -> int:
    """Insert a new row in ev_score_history; return the PK.

    The session is *not* committed here — the caller owns the transaction
    boundary so multi-program writes can batch into one txn.
    """
    stmt = (
        insert(ev_score_history)
        .values(
            program_handle=program_handle,
            computed_at=datetime.now(UTC),
            ev_score=breakdown.ev_score,
            f_payout=breakdown.f_payout,
            f_saturation=breakdown.f_saturation,
            f_ops=breakdown.f_ops,
            f_fit=breakdown.f_fit,
            f_cve=breakdown.f_cve,
            weights_version=breakdown.weights_version,
            computed_for_operator=operator_id,
        )
        .returning(ev_score_history.c.id)
    )
    result = await session.execute(stmt)
    inserted_id = result.scalar_one()
    return int(inserted_id)


async def get_latest_ev(
    session: AsyncSession,
    program_handle: str,
    operator_id: str | None,
) -> ScoreBreakdown | None:
    """Return the most recent ScoreBreakdown for (program_handle, operator_id)."""
    operator_clause = (
        ev_score_history.c.computed_for_operator.is_(None)
        if operator_id is None
        else ev_score_history.c.computed_for_operator == operator_id
    )
    stmt = (
        select(
            ev_score_history.c.ev_score,
            ev_score_history.c.f_payout,
            ev_score_history.c.f_saturation,
            ev_score_history.c.f_ops,
            ev_score_history.c.f_fit,
            ev_score_history.c.f_cve,
            ev_score_history.c.weights_version,
        )
        .where(ev_score_history.c.program_handle == program_handle)
        .where(operator_clause)
        .order_by(desc(ev_score_history.c.computed_at))
        .limit(1)
    )
    row = (await session.execute(stmt)).first()
    if row is None:
        return None
    return ScoreBreakdown(
        ev_score=float(row.ev_score),
        f_payout=float(row.f_payout) if row.f_payout is not None else 0.0,
        f_saturation=float(row.f_saturation) if row.f_saturation is not None else 0.0,
        f_ops=float(row.f_ops) if row.f_ops is not None else 0.0,
        f_fit=float(row.f_fit) if row.f_fit is not None else 0.0,
        f_cve=float(row.f_cve) if row.f_cve is not None else 0.0,
        weights_version=row.weights_version or "",
    )
