# SPDX-License-Identifier: AGPL-3.0-or-later

"""Scope-change notification delivery tests (plan 01-05).

SQLite (`sqlite+aiosqlite:///:memory:`) backs these — same pattern as
test_scope_federation.py — so no Postgres is needed. The webhook HTTP is mocked
by monkeypatching ``httpx.AsyncClient.post``; nothing touches the network.

Coverage:
- AC-1  new undelivered rows POSTed; marked notified_at after 2xx
- AC-2  non-2xx (500) and transport error leave rows redeliverable, no raise
- AC-3  unset SCOPE_WEBHOOK_URL -> no POST, pending surfaced
- AC-4  already-delivered rows excluded from payload
- AC-6  backfill semantics: pre-existing NULL rows stamped delivered
- AC-7  bounded batches drain in one run; summary <= 2000 chars
- AC-9  failure logs WARNING with pending count; secret URL never in logs
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
import pytest_asyncio
import structlog
from control_plane.db import Base, ScopeChange, make_session_factory
from control_plane.domains.scope_management.services import notification_service as notif
from control_plane.domains.scope_management.services.notification_service import (
    BATCH_SIZE,
    SUMMARY_MAX_CHARS,
    deliver_pending,
)
from sqlalchemy import JSON, BigInteger, Integer, event, func, select, update
from sqlalchemy.dialects.postgresql import ARRAY as PG_ARRAY
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.types import ARRAY as GENERIC_ARRAY

# A realistic secret-bearing webhook URL: the token in the path must never leak.
_SECRET = "SECRET_TOKEN_abc123xyz"
_WEBHOOK_URL = f"https://hooks.example.com/services/T000/B000/{_SECRET}"


# ---------------------------------------------------------------------------
# SQLite fixtures (Postgres-only types coerced before create_all).
# ---------------------------------------------------------------------------


def _coerce_pg_types_for_sqlite() -> None:
    for table in Base.metadata.tables.values():
        for col in table.columns:
            if isinstance(col.type, JSONB | PG_ARRAY | GENERIC_ARRAY):
                col.type = JSON()
            if col.primary_key and isinstance(col.type, BigInteger):
                col.type = Integer()


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    _coerce_pg_types_for_sqlite()
    eng = create_async_engine("sqlite+aiosqlite:///:memory:")

    @event.listens_for(eng.sync_engine, "connect")
    def _set_sqlite_pragmas(dbapi_conn: Any, _: Any) -> None:  # noqa: ARG001
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield eng
    finally:
        await eng.dispose()


@pytest_asyncio.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    factory = make_session_factory(engine)
    async with factory() as s:
        yield s


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _seed(session: AsyncSession, n: int, *, delivered: bool = False) -> list[int]:
    """Insert ``n`` scope_changes rows; return their ids."""
    rows = [
        ScopeChange(
            event_type="scope_added",
            program_handle=f"prog-{i}",
            platform="hackerone",
            asset_identifier=f"asset-{i}.example.com",
            old_value=None,
            new_value={"in_scope": True},
            detected_at=datetime.now(UTC),
            source="projectdiscovery",
            notified_at=datetime.now(UTC) if delivered else None,
        )
        for i in range(n)
    ]
    session.add_all(rows)
    await session.commit()
    return [r.id for r in rows]


async def _null_count(session: AsyncSession) -> int:
    return int(
        await session.scalar(
            select(func.count()).select_from(ScopeChange).where(ScopeChange.notified_at.is_(None))
        )
        or 0
    )


def _capturing_post(posted: list[dict], status: int = 200):
    async def fake_post(self: Any, url: str, json: Any = None, **kwargs: Any) -> httpx.Response:
        posted.append({"url": url, "json": json})
        return httpx.Response(status)

    return fake_post


def _raising_post(calls: list[str]):
    async def fake_post(self: Any, url: str, json: Any = None, **kwargs: Any) -> httpx.Response:
        calls.append(url)
        raise httpx.ConnectError("boom")

    return fake_post


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ac1_delivers_and_marks(session: AsyncSession, monkeypatch: Any) -> None:
    """AC-1: undelivered rows POSTed once; both in events[]; marked after 2xx."""
    await _seed(session, 2)
    posted: list[dict] = []
    monkeypatch.setenv("SCOPE_WEBHOOK_URL", _WEBHOOK_URL)
    monkeypatch.setattr(httpx.AsyncClient, "post", _capturing_post(posted, 200))

    result = await deliver_pending(session)

    assert result == {"notified": 2, "pending": 0}
    assert len(posted) == 1
    body = posted[0]["json"]
    assert len(body["events"]) == 2
    assert {e["program_handle"] for e in body["events"]} == {"prog-0", "prog-1"}
    assert body["text"] == body["content"]  # Slack + Discord same summary
    assert await _null_count(session) == 0  # all rows marked delivered


@pytest.mark.asyncio
async def test_ac2_500_leaves_redeliverable(session: AsyncSession, monkeypatch: Any) -> None:
    """AC-2: a 500 marks nothing; rows stay NULL; no raise; pending reflects them."""
    await _seed(session, 3)
    posted: list[dict] = []
    monkeypatch.setenv("SCOPE_WEBHOOK_URL", _WEBHOOK_URL)
    monkeypatch.setattr(notif, "_RETRY_BACKOFF_SECONDS", 0)  # keep the test fast
    monkeypatch.setattr(httpx.AsyncClient, "post", _capturing_post(posted, 500))

    result = await deliver_pending(session)

    assert result == {"notified": 0, "pending": 3}
    assert await _null_count(session) == 3  # nothing marked
    assert len(posted) == 2  # original + one retry on 5xx


@pytest.mark.asyncio
async def test_ac2_transport_error_leaves_redeliverable(
    session: AsyncSession, monkeypatch: Any
) -> None:
    """AC-2 (transport variant): a connection error never raises; rows stay NULL."""
    await _seed(session, 2)
    calls: list[str] = []
    monkeypatch.setenv("SCOPE_WEBHOOK_URL", _WEBHOOK_URL)
    monkeypatch.setattr(notif, "_RETRY_BACKOFF_SECONDS", 0)
    monkeypatch.setattr(httpx.AsyncClient, "post", _raising_post(calls))

    result = await deliver_pending(session)

    assert result == {"notified": 0, "pending": 2}
    assert await _null_count(session) == 2
    assert len(calls) == 2  # original + one retry on transport error


@pytest.mark.asyncio
async def test_ac3_unconfigured_noop(session: AsyncSession, monkeypatch: Any) -> None:
    """AC-3: empty/unset SCOPE_WEBHOOK_URL -> no POST; pending = undelivered count."""
    await _seed(session, 4)
    posted: list[dict] = []
    monkeypatch.delenv("SCOPE_WEBHOOK_URL", raising=False)
    monkeypatch.setattr(httpx.AsyncClient, "post", _capturing_post(posted, 200))

    result = await deliver_pending(session)

    assert result == {"notified": 0, "pending": 4}
    assert posted == []  # POST never attempted


@pytest.mark.asyncio
async def test_ac3_invalid_scheme_noop(session: AsyncSession, monkeypatch: Any) -> None:
    """AC-3 / S4: a non-http(s) scheme is rejected as a no-op (no POST)."""
    await _seed(session, 1)
    posted: list[dict] = []
    monkeypatch.setenv("SCOPE_WEBHOOK_URL", "file:///etc/passwd")
    monkeypatch.setattr(httpx.AsyncClient, "post", _capturing_post(posted, 200))

    result = await deliver_pending(session)

    assert result == {"notified": 0, "pending": 1}
    assert posted == []


@pytest.mark.asyncio
async def test_ac4_excludes_already_delivered(session: AsyncSession, monkeypatch: Any) -> None:
    """AC-4: rows with notified_at set are never re-sent; only NULL rows POSTed."""
    await _seed(session, 1, delivered=True)  # already delivered
    await _seed(session, 1, delivered=False)  # the only candidate
    posted: list[dict] = []
    monkeypatch.setenv("SCOPE_WEBHOOK_URL", _WEBHOOK_URL)
    monkeypatch.setattr(httpx.AsyncClient, "post", _capturing_post(posted, 200))

    result = await deliver_pending(session)

    assert result == {"notified": 1, "pending": 0}
    assert len(posted) == 1
    assert len(posted[0]["json"]["events"]) == 1


@pytest.mark.asyncio
async def test_ac6_backfill_marks_preexisting(session: AsyncSession) -> None:
    """AC-6: migration backfill semantics — pre-existing NULL rows -> delivered.

    The live Postgres migration (infra/sql/12_phase1_scope_notified.sql) is
    verified against bs-postgres in the APPLY step; here we assert the SAME
    go-forward-only UPDATE against the SQLite test schema leaves zero NULLs.
    """
    await _seed(session, 5, delivered=False)
    assert await _null_count(session) == 5

    await session.execute(
        update(ScopeChange)
        .where(ScopeChange.notified_at.is_(None))
        .values(notified_at=datetime.now(UTC))
    )
    await session.commit()

    assert await _null_count(session) == 0


@pytest.mark.asyncio
async def test_ac7_batches_and_drains(session: AsyncSession, monkeypatch: Any) -> None:
    """AC-7: > BATCH_SIZE rows drain in one run via multiple bounded POSTs."""
    total = BATCH_SIZE + 5  # 30 -> two batches (25 + 5)
    await _seed(session, total)
    posted: list[dict] = []
    monkeypatch.setenv("SCOPE_WEBHOOK_URL", _WEBHOOK_URL)
    monkeypatch.setattr(httpx.AsyncClient, "post", _capturing_post(posted, 200))

    result = await deliver_pending(session)

    assert result == {"notified": total, "pending": 0}  # full backlog drained
    assert len(posted) == 2  # bounded into 2 batches
    assert [len(p["json"]["events"]) for p in posted] == [BATCH_SIZE, 5]
    for p in posted:
        assert len(p["json"]["content"]) <= SUMMARY_MAX_CHARS  # provider-safe
        assert len(p["json"]["events"]) <= BATCH_SIZE


@pytest.mark.asyncio
async def test_ac9_failure_is_observable_and_redacted(
    session: AsyncSession, monkeypatch: Any
) -> None:
    """AC-9 / M3: failure logs WARNING with pending count; secret URL never logged."""
    await _seed(session, 2)
    posted: list[dict] = []
    monkeypatch.setenv("SCOPE_WEBHOOK_URL", _WEBHOOK_URL)
    monkeypatch.setattr(notif, "_RETRY_BACKOFF_SECONDS", 0)
    monkeypatch.setattr(httpx.AsyncClient, "post", _capturing_post(posted, 500))

    with structlog.testing.capture_logs() as logs:
        result = await deliver_pending(session)

    assert result["notified"] == 0
    assert result["pending"] == 2  # backlog surfaced, not silent

    warnings = [e for e in logs if e.get("log_level") == "warning"]
    assert any(e["event"] == "scope_notify.delivery_failed" for e in warnings)
    failed = next(e for e in warnings if e["event"] == "scope_notify.delivery_failed")
    assert failed["pending"] == 2
    assert failed["webhook"] == "https://hooks.example.com"  # redacted to scheme+host
    # The secret token must not appear anywhere in any captured log event.
    assert _SECRET not in repr(logs)
