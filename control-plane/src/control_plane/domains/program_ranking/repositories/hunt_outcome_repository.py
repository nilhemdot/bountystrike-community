"""Persistence layer for hunt_outcomes (Phase 3 calibration scaffolding).

Mirrors infra/sql/07_phase3_calibration.sql:hunt_outcomes columns exactly:
    id (autoincrement) | program_handle | operator_id | scan_job_id
    ev_rank | submitted_count | confirmed_count
    period_start | period_end | created_at

Style mirrors ev_history_repository.py: SQLAlchemy core async + Pydantic
value objects. The session is *not* committed here — the caller owns the
transaction boundary.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    insert,
    select,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncSession

from ..value_objects.hunt_outcome import HuntOutcome

metadata = MetaData()

hunt_outcomes = Table(
    "hunt_outcomes",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("program_handle", String, nullable=False),
    Column("operator_id", String, nullable=False),
    Column("scan_job_id", PG_UUID(as_uuid=True)),
    Column("ev_rank", Integer),
    Column("submitted_count", Integer, nullable=False, default=0),
    Column("confirmed_count", Integer, nullable=False, default=0),
    Column("period_start", DateTime(timezone=True)),
    Column("period_end", DateTime(timezone=True)),
    Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    ),
    UniqueConstraint("program_handle", "operator_id", "scan_job_id"),
)


async def write_hunt_outcome(
    session: AsyncSession,
    outcome: HuntOutcome,
) -> int:
    """Insert one hunt_outcomes row; return the PK.

    Caller owns the transaction. Raises IntegrityError on duplicate
    (program_handle, operator_id, scan_job_id) — let it bubble up so
    reconciliation scripts can detect already-recorded outcomes.
    """
    stmt = (
        insert(hunt_outcomes)
        .values(
            program_handle=outcome.program_handle,
            operator_id=outcome.operator_id,
            scan_job_id=outcome.scan_job_id,
            ev_rank=outcome.ev_rank,
            submitted_count=outcome.submitted_count,
            confirmed_count=outcome.confirmed_count,
            period_start=outcome.period_start,
            period_end=outcome.period_end,
            created_at=datetime.now(UTC),
        )
        .returning(hunt_outcomes.c.id)
    )
    result = await session.execute(stmt)
    return int(result.scalar_one())


async def get_outcomes_for_calibration(
    session: AsyncSession,
    operator_id: str | None = None,
    limit: int = 200,
) -> list[HuntOutcome]:
    """Fetch outcomes for Spearman ρ calculation.

    Filters out rows with NULL ev_rank (can't correlate without a rank)
    and rows with submitted_count = 0 (no signal). When operator_id is
    None, returns outcomes across all operators (global calibration).
    """
    stmt = (
        select(
            hunt_outcomes.c.program_handle,
            hunt_outcomes.c.operator_id,
            hunt_outcomes.c.scan_job_id,
            hunt_outcomes.c.ev_rank,
            hunt_outcomes.c.submitted_count,
            hunt_outcomes.c.confirmed_count,
            hunt_outcomes.c.period_start,
            hunt_outcomes.c.period_end,
        )
        .where(hunt_outcomes.c.ev_rank.is_not(None))
        .where(hunt_outcomes.c.submitted_count > 0)
        .limit(limit)
    )
    if operator_id is not None:
        stmt = stmt.where(hunt_outcomes.c.operator_id == operator_id)

    rows = (await session.execute(stmt)).all()
    return [
        HuntOutcome(
            program_handle=row.program_handle,
            operator_id=row.operator_id,
            scan_job_id=str(row.scan_job_id) if row.scan_job_id is not None else None,
            ev_rank=row.ev_rank,
            submitted_count=row.submitted_count,
            confirmed_count=row.confirmed_count,
            period_start=row.period_start,
            period_end=row.period_end,
        )
        for row in rows
    ]
