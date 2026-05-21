"""Tests for ev-mcp — DB loader + FastMCP tools."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from control_plane.domains.program_ranking.value_objects import (
    OperatorProfile,
)
from ev_mcp.db import ProgramFeatureLoader

# ---------------------------------------------------------------------------
# Helpers — minimal asyncpg row stand-ins
# ---------------------------------------------------------------------------


def _program_row(
    handle: str,
    *,
    platform: str = "hackerone",
    payout_max: float = 5000.0,
    payout_min: float = 100.0,
    bounty_paid_ratio: float = 0.7,
    triage_acceptance_rate: float = 0.8,
    dup_rate: float = 0.1,
    last_modified_at=None,
) -> dict:
    return {
        "handle": handle,
        "platform": platform,
        "payout_min": payout_min,
        "payout_max": payout_max,
        "bounty_paid_ratio": bounty_paid_ratio,
        "triage_acceptance_rate": triage_acceptance_rate,
        "dup_rate": dup_rate,
        "last_modified_at": last_modified_at,
    }


def _scope_row(program_handle: str, asset_type: str, n: int) -> dict:
    return {"program_handle": program_handle, "asset_type": asset_type, "n": n}


# ---------------------------------------------------------------------------
# 1. ProgramFeatureLoader — list_features
# ---------------------------------------------------------------------------


async def test_list_features_no_filters_returns_all_with_distribution():
    conn = AsyncMock()
    conn.fetch.side_effect = [
        [_program_row("acme"), _program_row("beta", platform="bugcrowd")],
        [
            _scope_row("acme", "domain", 5),
            _scope_row("acme", "android", 1),
            _scope_row("beta", "smart_contract", 3),
        ],
    ]
    loader = ProgramFeatureLoader()
    features = await loader.list_features(conn)
    assert len(features) == 2

    by_handle = {f.handle: f for f in features}
    assert by_handle["acme"].asset_distribution == {"domain": 5, "android": 1}
    assert by_handle["beta"].asset_distribution == {"smart_contract": 3}


async def test_list_features_platforms_filter_passes_to_sql():
    conn = AsyncMock()
    conn.fetch.side_effect = [[], []]
    loader = ProgramFeatureLoader()
    await loader.list_features(conn, platforms=["hackerone", "immunefi"])
    first_call = conn.fetch.call_args_list[0]
    sql = first_call.args[0]
    assert "platform = ANY($1)" in sql
    assert first_call.args[1] == ["hackerone", "immunefi"]


async def test_list_features_require_bounty_filters_zero_payout():
    conn = AsyncMock()
    conn.fetch.side_effect = [[], []]
    loader = ProgramFeatureLoader()
    await loader.list_features(conn, require_bounty=True)
    sql = conn.fetch.call_args_list[0].args[0]
    assert "payout_max" in sql and "> 0" in sql


async def test_list_features_skips_scope_query_when_no_programs():
    conn = AsyncMock()
    conn.fetch.return_value = []
    loader = ProgramFeatureLoader()
    features = await loader.list_features(conn)
    assert features == []
    # Only the programs query ran — no point asking for scopes of zero handles.
    assert conn.fetch.call_count == 1


# ---------------------------------------------------------------------------
# 2. ProgramFeatureLoader — get_features
# ---------------------------------------------------------------------------


async def test_get_features_unknown_handle_returns_none():
    conn = AsyncMock()
    conn.fetchrow.return_value = None
    loader = ProgramFeatureLoader()
    assert await loader.get_features(conn, "nope") is None


async def test_get_features_empty_handle_returns_none_without_query():
    conn = AsyncMock()
    loader = ProgramFeatureLoader()
    assert await loader.get_features(conn, "") is None
    conn.fetchrow.assert_not_called()


async def test_get_features_builds_distribution_from_scopes():
    conn = AsyncMock()
    conn.fetchrow.return_value = _program_row("acme")
    conn.fetch.return_value = [
        {"asset_type": "domain", "n": 4},
        {"asset_type": "executable", "n": 2},
    ]
    loader = ProgramFeatureLoader()
    features = await loader.get_features(conn, "acme")
    assert features is not None
    assert features.asset_distribution == {"domain": 4, "executable": 2}
    assert features.payout_max == 5000.0


async def test_get_features_coerces_string_dates():
    conn = AsyncMock()
    row = _program_row("acme", last_modified_at="2026-04-29T12:00:00")
    conn.fetchrow.return_value = row
    conn.fetch.return_value = []
    loader = ProgramFeatureLoader()
    features = await loader.get_features(conn, "acme")
    assert features is not None
    assert isinstance(features.last_modified_at, datetime)


# ---------------------------------------------------------------------------
# 3. Server tools — exercised against a stubbed pool/loader
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def stub_pool(monkeypatch: pytest.MonkeyPatch):
    """Replace the module-level pool getter with one yielding an AsyncMock conn.

    Each test decides what the conn returns by setting
    ``conn.fetch.side_effect`` / ``conn.fetchrow.return_value`` via the
    ``test_conn`` fixture below.
    """
    import ev_mcp.server as srv

    test_conn = AsyncMock()
    pool = MagicMock()

    class _Acquire:
        async def __aenter__(self):
            return test_conn

        async def __aexit__(self, *_):
            return False

    pool.acquire = lambda: _Acquire()

    async def fake_get_pool():
        return pool

    monkeypatch.setattr(srv, "_get_pool", fake_get_pool)
    monkeypatch.setattr(srv, "_pool", pool)
    setattr(srv, "test_conn", test_conn)  # for tests to grab


@pytest.fixture
def test_conn():
    import ev_mcp.server as srv

    return getattr(srv, "test_conn")


# ----- rank_programs -------------------------------------------------------


async def test_server_rank_programs_returns_sorted_results(test_conn):
    test_conn.fetch.side_effect = [
        [
            _program_row("acme",  payout_max=8000, bounty_paid_ratio=0.9,
                         triage_acceptance_rate=0.9, dup_rate=0.05,
                         last_modified_at=datetime(2026, 4, 28, tzinfo=UTC)),
            _program_row("beta",  payout_max=2000, bounty_paid_ratio=0.4,
                         triage_acceptance_rate=0.5, dup_rate=0.3,
                         last_modified_at=datetime(2026, 1, 1, tzinfo=UTC)),
        ],
        [
            _scope_row("acme", "domain", 4),
            _scope_row("beta", "domain", 2),
        ],
    ]

    from ev_mcp.server import rank_programs

    result = await rank_programs(operator_profile={
        "asset_type_pref": {"domain": 1.0},
    })
    assert result["count"] == 2
    handles = [r["program"]["handle"] for r in result["results"]]
    # acme has materially better signals — must rank first.
    assert handles[0] == "acme"
    # Ranks are 1-based and monotonic in result order.
    assert [r["rank"] for r in result["results"]] == [1, 2]


async def test_server_rank_programs_min_ev_score_filters(test_conn):
    test_conn.fetch.side_effect = [
        [_program_row("low", payout_max=10, bounty_paid_ratio=0.01)],
        [],
    ]
    from ev_mcp.server import rank_programs
    result = await rank_programs(min_ev_score=0.99)
    assert result["count"] == 0


async def test_server_rank_programs_clamps_oversize_limit(test_conn):
    test_conn.fetch.side_effect = [[], []]
    from ev_mcp.server import rank_programs
    result = await rank_programs(limit=1000)
    assert result["limit"] == 200


async def test_server_rank_programs_rejects_zero_limit(test_conn):
    from ev_mcp.server import rank_programs
    result = await rank_programs(limit=0)
    assert "error" in result


async def test_server_rank_programs_default_operator_profile_works(test_conn):
    """No operator_profile passed → default profile, no crash."""
    test_conn.fetch.side_effect = [
        [_program_row("acme")],
        [_scope_row("acme", "domain", 1)],
    ]
    from ev_mcp.server import rank_programs
    result = await rank_programs()
    assert result["count"] == 1


# ----- get_program_details -------------------------------------------------


async def test_server_get_program_details_hit(test_conn):
    test_conn.fetchrow.return_value = _program_row(
        "acme", last_modified_at=datetime(2026, 4, 28, tzinfo=UTC)
    )
    test_conn.fetch.return_value = [_scope_row("acme", "domain", 5)]

    from ev_mcp.server import get_program_details
    result = await get_program_details("acme")
    assert result["program"]["handle"] == "acme"
    assert result["score"]["ev_score"] >= 0.0
    assert "weights_version" in result["score"]


async def test_server_get_program_details_miss_returns_marker(test_conn):
    test_conn.fetchrow.return_value = None
    from ev_mcp.server import get_program_details
    result = await get_program_details("nope")
    assert result == {"error": "not_found", "program_handle": "nope"}


async def test_server_get_program_details_empty_handle_rejects(test_conn):
    from ev_mcp.server import get_program_details
    result = await get_program_details("")
    assert "error" in result


async def test_server_get_program_details_passes_operator_profile_to_scoring(
    test_conn,
):
    """Operator preference for an asset type the program has → boost f_fit."""
    test_conn.fetchrow.return_value = _program_row("acme")
    test_conn.fetch.return_value = [_scope_row("acme", "smart_contract", 3)]

    from ev_mcp.server import get_program_details

    no_pref = await get_program_details("acme")
    pref = await get_program_details(
        "acme",
        operator_profile={"asset_type_pref": {"smart_contract": 1.0}},
    )
    assert pref["score"]["f_fit"] > no_pref["score"]["f_fit"]


# ---------------------------------------------------------------------------
# 4. JSON serializability of all tool returns
# ---------------------------------------------------------------------------


async def test_tool_returns_are_json_serializable(test_conn):
    # rank_programs consumes (programs, scopes); get_program_details
    # consumes one more `fetch` (scopes for the single program).
    test_conn.fetch.side_effect = [
        [_program_row("acme")],
        [_scope_row("acme", "domain", 1)],
        [_scope_row("acme", "domain", 1)],
    ]
    test_conn.fetchrow.return_value = _program_row("acme")

    from ev_mcp.server import get_program_details, rank_programs

    a = await rank_programs()
    b = await get_program_details("acme")
    for payload in (a, b):
        json.dumps(payload)  # raises TypeError if any field is non-serializable


# ---------------------------------------------------------------------------
# 5. _operator_profile_from_dict — defaults + missing keys
# ---------------------------------------------------------------------------


def test_operator_profile_from_dict_defaults():
    from ev_mcp.server import _operator_profile_from_dict
    op = _operator_profile_from_dict(None)
    assert isinstance(op, OperatorProfile)
    assert op.time_budget_hours == 40.0
    assert op.cost_budget_usd == 50.0


def test_operator_profile_from_dict_passes_overrides():
    from ev_mcp.server import _operator_profile_from_dict
    op = _operator_profile_from_dict({
        "time_budget_hours": 12,
        "cost_budget_usd": 5,
        "asset_type_pref": {"domain": 0.8},
    })
    assert op.time_budget_hours == 12.0
    assert op.cost_budget_usd == 5.0
    assert op.asset_type_pref == {"domain": 0.8}
