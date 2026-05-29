# SPDX-License-Identifier: AGPL-3.0-or-later

"""Roundtrip tests for ev/writer.py against an in-memory SQLite (aiosqlite)."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from control_plane.domains.program_ranking import (
    ScoreBreakdown,
    ev_score_history,
    get_latest_ev,
    metadata,
    write_ev_score,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all)
    sm = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with sm() as s:
        yield s
    await engine.dispose()


def _sample_breakdown(ev: float = 0.6789) -> ScoreBreakdown:
    return ScoreBreakdown(
        ev_score=ev,
        f_payout=0.5000,
        f_saturation=0.4500,
        f_ops=0.9000,
        f_fit=0.7200,
        f_cve=0.0,
        weights_version="v2.0",
    )


@pytest.mark.asyncio
async def test_write_returns_pk(session: AsyncSession) -> None:
    breakdown = _sample_breakdown()
    pk = await write_ev_score(session, "acme-web", breakdown, "alice")
    await session.commit()
    assert isinstance(pk, int)
    assert pk >= 1


@pytest.mark.asyncio
async def test_roundtrip_insert_then_read(session: AsyncSession) -> None:
    written = _sample_breakdown(ev=0.7531)
    await write_ev_score(session, "defi-protocol", written, "alice")
    await session.commit()

    read_back = await get_latest_ev(session, "defi-protocol", "alice")
    assert read_back is not None
    assert read_back.ev_score == pytest.approx(written.ev_score, abs=0.0001)
    assert read_back.f_payout == pytest.approx(written.f_payout, abs=0.0001)
    assert read_back.f_saturation == pytest.approx(written.f_saturation, abs=0.0001)
    assert read_back.f_ops == pytest.approx(written.f_ops, abs=0.0001)
    assert read_back.f_fit == pytest.approx(written.f_fit, abs=0.0001)
    assert read_back.f_cve == pytest.approx(written.f_cve, abs=0.0001)
    assert read_back.weights_version == "v2.0"


@pytest.mark.asyncio
async def test_get_latest_returns_most_recent(session: AsyncSession) -> None:
    """When multiple rows exist for the same (handle, operator), get_latest_ev picks the newest."""
    earlier = _sample_breakdown(ev=0.50)
    later = _sample_breakdown(ev=0.90)

    await write_ev_score(session, "globex-api", earlier, "alice")
    await write_ev_score(session, "globex-api", later, "alice")
    await session.commit()

    result = await get_latest_ev(session, "globex-api", "alice")
    assert result is not None
    assert result.ev_score == pytest.approx(0.90, abs=0.0001)


@pytest.mark.asyncio
async def test_get_latest_none_when_missing(session: AsyncSession) -> None:
    result = await get_latest_ev(session, "nonexistent-program", "alice")
    assert result is None


@pytest.mark.asyncio
async def test_get_latest_filters_by_operator(session: AsyncSession) -> None:
    alice_breakdown = _sample_breakdown(ev=0.60)
    bob_breakdown = _sample_breakdown(ev=0.80)
    await write_ev_score(session, "skyhigh-cloud", alice_breakdown, "alice")
    await write_ev_score(session, "skyhigh-cloud", bob_breakdown, "bob")
    await session.commit()

    a = await get_latest_ev(session, "skyhigh-cloud", "alice")
    b = await get_latest_ev(session, "skyhigh-cloud", "bob")
    assert a is not None and a.ev_score == pytest.approx(0.60, abs=0.0001)
    assert b is not None and b.ev_score == pytest.approx(0.80, abs=0.0001)


@pytest.mark.asyncio
async def test_persists_weights_version_and_all_factors(session: AsyncSession) -> None:
    """Verify the row contains weights_version, computed_at, and every f_* column."""
    from sqlalchemy import select

    breakdown = _sample_breakdown()
    await write_ev_score(session, "acme-web", breakdown, "alice")
    await session.commit()

    rows = (await session.execute(select(ev_score_history))).all()
    assert len(rows) == 1
    row = rows[0]

    assert row.program_handle == "acme-web"
    assert row.computed_at is not None
    assert float(row.ev_score) == pytest.approx(breakdown.ev_score, abs=0.0001)
    assert float(row.f_payout) == pytest.approx(breakdown.f_payout, abs=0.0001)
    assert float(row.f_saturation) == pytest.approx(breakdown.f_saturation, abs=0.0001)
    assert float(row.f_ops) == pytest.approx(breakdown.f_ops, abs=0.0001)
    assert float(row.f_fit) == pytest.approx(breakdown.f_fit, abs=0.0001)
    assert float(row.f_cve) == pytest.approx(breakdown.f_cve, abs=0.0001)
    assert row.weights_version == "v2.0"
    assert row.computed_for_operator == "alice"


@pytest.mark.asyncio
async def test_write_supports_null_operator(session: AsyncSession) -> None:
    """operator_id may be None (system-wide score)."""
    breakdown = _sample_breakdown()
    pk = await write_ev_score(session, "acme-web", breakdown, None)
    await session.commit()
    assert pk >= 1
    result = await get_latest_ev(session, "acme-web", None)
    assert result is not None
    assert result.ev_score == pytest.approx(breakdown.ev_score, abs=0.0001)
