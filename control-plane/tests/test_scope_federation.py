# SPDX-License-Identifier: AGPL-3.0-or-later

"""Federation ingestion tests — bbscope v2 + projectdiscovery + idempotency.

SQLite (`sqlite+aiosqlite:///:memory:`) backs these so no Postgres is needed.
Clients are injected (a fake bbscope subprocess runner; an httpx MockTransport
for projectdiscovery) so nothing touches a real binary or the network.

Coverage:
1. bbscope v2 `poll`/`db` JSON parses + Intigriti `--oos` -> `in_scope=False`.
2. projectdiscovery `dist/data.json` `programs` key ingests as VDP scopes, and
   the legacy chaos-list filename is never referenced.
3. Combined multi-source ingest accumulates counts.
4. Idempotent re-ingest: identical feed -> 0 new rows, 0 diff events (AC-5).
"""

from __future__ import annotations

import inspect
import json
from collections.abc import AsyncIterator, Sequence
from typing import Any

import httpx
import pytest
import pytest_asyncio
from control_plane.db import Base, Scope, ScopeChange, make_session_factory
from control_plane.domains.scope_management.integrations import projectdiscovery as pd_module
from control_plane.domains.scope_management.integrations.bbscope import BbscopeClient
from control_plane.domains.scope_management.integrations.projectdiscovery import (
    ProjectDiscoveryClient,
)
from control_plane.domains.scope_management.services.ingest_service import (
    ingest_bbscope_all,
    ingest_projectdiscovery_all,
)
from sqlalchemy import JSON, BigInteger, Integer, event, select
from sqlalchemy.dialects.postgresql import ARRAY as PG_ARRAY
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.types import ARRAY as GENERIC_ARRAY

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
# Canned bbscope `db -o json` output, keyed by (platform, oos).
# ---------------------------------------------------------------------------

_BBSCOPE_DB: dict[tuple[str, bool], str] = {
    ("hackerone", False): json.dumps(
        [{"handle": "acme", "name": "Acme", "target": "*.acme.com", "category": "URL"}]
    ),
    ("bugcrowd", False): json.dumps([{"handle": "globex", "target": "*.globex.io"}]),
    ("intigriti", False): json.dumps(
        [{"handle": "initech", "target": "app.initech.com", "type": "url"}]
    ),
    ("intigriti", True): json.dumps(
        [{"handle": "initech", "target": "legacy.initech.com", "type": "url"}]
    ),
    ("yeswehack", False): json.dumps([{"handle": "umbrella", "target": "*.umbrella.io"}]),
}


def _make_bbscope_client() -> BbscopeClient:
    async def runner(argv: Sequence[str]) -> str:
        if argv[1] == "poll":
            return ""
        platform = argv[argv.index("-p") + 1]
        oos = "--oos" in argv
        return _BBSCOPE_DB.get((platform, oos), "[]")

    return BbscopeClient(runner=runner)


# ---------------------------------------------------------------------------
# projectdiscovery dist/data.json fixture via httpx MockTransport.
# ---------------------------------------------------------------------------

_PD_DATA = {
    "programs": [
        {
            "name": "Acme Inc",
            "url": "https://acme.com",
            "bounty": False,
            "domains": ["acme.com", "*.acme.com"],
        },
        {
            "name": "Globex",
            "url": "https://globex.io",
            "bounty": False,
            "domains": ["globex.io"],
        },
    ]
}


def _make_pd_client() -> ProjectDiscoveryClient:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_PD_DATA)

    return ProjectDiscoveryClient(transport=httpx.MockTransport(handler))


async def _count(session: AsyncSession, model: type) -> int:
    result = await session.execute(select(model))
    return len(list(result.scalars().all()))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bbscope_ingest_with_oos(session: AsyncSession) -> None:
    """bbscope v2 ingest: 4 programs; Intigriti OOS row stored in_scope=False."""
    result = await ingest_bbscope_all(session, client=_make_bbscope_client())

    assert result["programs"] == 4  # acme, globex, initech, umbrella
    assert result["scopes"] >= 5  # 4 in-scope + 1 intigriti OOS
    assert result["events"] >= 5

    # Intigriti OOS target persisted as an exclusion.
    oos = (
        await session.execute(select(Scope).where(Scope.identifier == "legacy.initech.com"))
    ).scalar_one()
    assert oos.in_scope is False
    assert oos.program_handle == "initech"

    in_scope_row = (
        await session.execute(select(Scope).where(Scope.identifier == "app.initech.com"))
    ).scalar_one()
    assert in_scope_row.in_scope is True

    # Events from bbscope are tagged with the bbscope source.
    changes = (await session.execute(select(ScopeChange))).scalars().all()
    assert changes and all(c.source == "bbscope" for c in changes)


@pytest.mark.asyncio
async def test_projectdiscovery_ingest(session: AsyncSession) -> None:
    """projectdiscovery VDP ingest from dist/data.json `programs` key."""
    result = await ingest_projectdiscovery_all(session, client=_make_pd_client())

    assert result["programs"] == 2
    assert result["scopes"] == 3  # acme: 2 domains, globex: 1
    assert result["events"] == 3

    rows = (await session.execute(select(Scope))).scalars().all()
    assert all(r.in_scope is True for r in rows)
    assert all("vdp" in (r.tags or []) for r in rows)
    # pd- namespaced handles avoid PK collisions with auth platforms.
    assert {r.program_handle for r in rows} == {"pd-acme-inc", "pd-globex"}


def test_projectdiscovery_never_references_chaos_list() -> None:
    """Trap #8: the legacy chaos-bugbounty-list.json filename is never used."""
    src = inspect.getsource(pd_module)
    assert "chaos-bugbounty-list.json" not in src
    assert "dist/data.json" in src


@pytest.mark.asyncio
async def test_combined_multi_source(session: AsyncSession) -> None:
    """bbscope + projectdiscovery ingest in one session accumulate independently."""
    bb = await ingest_bbscope_all(session, client=_make_bbscope_client())
    pd = await ingest_projectdiscovery_all(session, client=_make_pd_client())

    total_scopes = await _count(session, Scope)
    assert total_scopes == bb["scopes"] + pd["scopes"]
    assert bb["programs"] == 4
    assert pd["programs"] == 2


@pytest.mark.asyncio
async def test_idempotent_reingest(session: AsyncSession) -> None:
    """AC-5: identical feed re-ingest writes 0 new rows and 0 diff events."""
    first = await ingest_projectdiscovery_all(session, client=_make_pd_client())
    assert first["events"] == 3
    scopes_after_first = await _count(session, Scope)
    changes_after_first = await _count(session, ScopeChange)

    second = await ingest_projectdiscovery_all(session, client=_make_pd_client())
    assert second["events"] == 0

    assert await _count(session, Scope) == scopes_after_first
    assert await _count(session, ScopeChange) == changes_after_first
