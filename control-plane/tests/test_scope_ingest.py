# SPDX-License-Identifier: AGPL-3.0-or-later

"""Integration tests for the scope-ingest worker.

We use SQLite (`sqlite+aiosqlite:///:memory:`) so no Postgres is required at
test time. The H1 client is mocked via `respx` to serve canned org-asset
responses.

Coverage:
1. Initial ingest of 3 H1 assets → 1 program row, 3 scopes rows, 3
   `scope_added` events.
2. Re-ingest with one asset's `max_bounty` tag changed → 1 `payout_changed`
   event.
3. Re-ingest with one asset removed → 1 `scope_removed` event.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
import pytest_asyncio
import respx
from control_plane.db import Base, Program, Scope, ScopeChange, make_session_factory
from control_plane.domains.scope_management.integrations.hackerone import (
    DEFAULT_BASE_URL,
    HackerOneClient,
)
from control_plane.domains.scope_management.services.ingest_service import (
    ingest_h1_org_assets,
)
from sqlalchemy import JSON, BigInteger, Integer, event, select
from sqlalchemy.dialects.postgresql import ARRAY as PG_ARRAY
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.types import ARRAY as GENERIC_ARRAY

# ---------------------------------------------------------------------------
# Postgres-only types (JSONB, TEXT[]) are swapped for JSON before create_all.
# ---------------------------------------------------------------------------


def _coerce_pg_types_for_sqlite() -> None:
    """Swap JSONB/ARRAY for JSON and BigInteger PKs to Integer for SQLite."""
    for table in Base.metadata.tables.values():
        for col in table.columns:
            if isinstance(col.type, JSONB | PG_ARRAY | GENERIC_ARRAY):
                col.type = JSON()
            # SQLite only supports AUTOINCREMENT on INTEGER PRIMARY KEY.
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
# Canned H1 responses
# ---------------------------------------------------------------------------


def _h1_response(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "data": [{"id": str(i), "type": "asset", "attributes": a} for i, a in enumerate(items)],
        "links": {"self": "...", "next": None},
    }


INITIAL_ASSETS = [
    {
        "asset_type": "URL",
        "identifier": "*.acme.com",
        "last_modified_at": "2026-04-20T10:00:00Z",
        "program_handles": ["acme-corp"],
        "tags": ["max_bounty:5000"],
    },
    {
        "asset_type": "API",
        "identifier": "api.acme.com",
        "last_modified_at": "2026-04-20T10:00:00Z",
        "program_handles": ["acme-corp"],
        "tags": ["max_bounty:8000"],
    },
    {
        "asset_type": "GOOGLE_PLAY_APP_ID",
        "identifier": "com.acme.app",
        "last_modified_at": "2026-04-20T10:00:00Z",
        "program_handles": ["acme-corp"],
        "tags": [],
    },
]

# 2nd ingest: identifier *.acme.com gets a new max_bounty tag (5000 → 7500).
PAYOUT_CHANGED_ASSETS = [
    {**INITIAL_ASSETS[0], "tags": ["max_bounty:7500"]},
    INITIAL_ASSETS[1],
    INITIAL_ASSETS[2],
]

# 3rd ingest: drops the API asset entirely.
ASSET_REMOVED = [PAYOUT_CHANGED_ASSETS[0], PAYOUT_CHANGED_ASSETS[2]]


async def _count(session: AsyncSession, model: type) -> int:
    result = await session.execute(select(model))
    return len(list(result.scalars().all()))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_ingest_flow(session: AsyncSession) -> None:
    """Stage 1 -> 2 -> 3: add, payout change, remove."""
    org_id = "77"

    with respx.mock(base_url=DEFAULT_BASE_URL, assert_all_called=False) as router:
        route = router.get(f"/v1/organizations/{org_id}/assets")

        # ---- Stage 1: initial ingest -------------------------------------
        route.mock(return_value=httpx.Response(200, json=_h1_response(INITIAL_ASSETS)))
        async with HackerOneClient(username="u", api_token="t", retries=0) as h1:
            result = await ingest_h1_org_assets(session, org_id, h1=h1)

        assert result == {"assets": 3, "programs": 1, "events": 3}

        prog_count = await _count(session, Program)
        scope_count = await _count(session, Scope)
        assert prog_count == 1
        assert scope_count == 3

        events = (await session.execute(select(ScopeChange))).scalars().all()
        added = [e for e in events if e.event_type == "scope_added"]
        assert len(added) == 3
        assert {e.asset_identifier for e in added} == {
            "*.acme.com",
            "api.acme.com",
            "com.acme.app",
        }
        assert all(e.source == "h1_org_assets" for e in added)
        assert all(e.platform == "hackerone" for e in added)
        assert all(e.program_handle == "acme-corp" for e in added)

        # ---- Stage 2: re-ingest with payout change -----------------------
        route.mock(
            return_value=httpx.Response(200, json=_h1_response(PAYOUT_CHANGED_ASSETS))
        )
        async with HackerOneClient(username="u", api_token="t", retries=0) as h1:
            result = await ingest_h1_org_assets(session, org_id, h1=h1)

        # 3 scopes, 1 payout change event recorded this round.
        assert result["events"] == 1

        payout_stmt = select(ScopeChange).where(ScopeChange.event_type == "payout_changed")
        events_after = (await session.execute(payout_stmt)).scalars().all()
        assert len(events_after) == 1
        assert events_after[0].asset_identifier == "*.acme.com"
        assert events_after[0].old_value is not None
        assert events_after[0].new_value is not None

        # Stored scope row reflects new tag.
        stmt = select(Scope).where(Scope.identifier == "*.acme.com")
        updated = (await session.execute(stmt)).scalar_one()
        assert "max_bounty:7500" in (updated.tags or [])
        assert "max_bounty:5000" not in (updated.tags or [])

        # ---- Stage 3: re-ingest with one asset removed -------------------
        route.mock(return_value=httpx.Response(200, json=_h1_response(ASSET_REMOVED)))
        async with HackerOneClient(username="u", api_token="t", retries=0) as h1:
            result = await ingest_h1_org_assets(session, org_id, h1=h1)

        assert result["events"] == 1

        removed_stmt = select(ScopeChange).where(ScopeChange.event_type == "scope_removed")
        removed_events = (await session.execute(removed_stmt)).scalars().all()
        assert len(removed_events) == 1
        assert removed_events[0].asset_identifier == "api.acme.com"

        # The scopes row is intentionally NOT deleted (we only insert events);
        # downstream EV reranker decides whether to deactivate.
        all_scopes = (await session.execute(select(Scope))).scalars().all()
        assert len(all_scopes) == 3
