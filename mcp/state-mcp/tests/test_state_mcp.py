"""Tests for state-mcp — store + server with mocked Postgres pool.

Live Postgres is not exercised; the asyncpg pool is mocked. An
integration suite that hits a real DB belongs in ``tests/integration/``.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from state_mcp.server import (
    _get_finding_impl,
    _query_artifacts_impl,
    _query_experience_kb_impl,
    _update_finding_status_impl,
)
from state_mcp.store import FINDING_STATUSES, StateStore


# ---------------------------------------------------------------------------
# FINDING_STATUSES — sanity check against schema enum
# ---------------------------------------------------------------------------


def test_status_set_includes_canonical_states() -> None:
    expected_subset = {
        "hypothesis",
        "validated",
        "approved",
        "submitted",
        "duplicate",
        "archived",
    }
    assert expected_subset <= FINDING_STATUSES


# ---------------------------------------------------------------------------
# StateStore — mock pool fixtures
# ---------------------------------------------------------------------------


def make_store_with_mock_conn(conn: AsyncMock) -> StateStore:
    """Build a StateStore where pool.acquire() yields *conn*."""
    pool = MagicMock()
    cm = AsyncMock()
    cm.__aenter__.return_value = conn
    cm.__aexit__.return_value = None
    pool.acquire = MagicMock(return_value=cm)
    return StateStore(pool)


@pytest.fixture
def conn() -> AsyncMock:
    return AsyncMock()


# ---------------------------------------------------------------------------
# get_finding
# ---------------------------------------------------------------------------


async def test_get_finding_returns_row(conn: AsyncMock) -> None:
    conn.fetchrow.return_value = {
        "id": "abc-123",
        "job_id": "job-1",
        "program_handle": "acme",
        "platform": "hackerone",
        "cwe": "CWE-79",
        "url": "https://x/y",
        "parameter": "q",
        "status": "validated",
        "evidence_hash": "deadbeef",
        "oracle_method": "oracle_xss",
        "validator_model": "claude-sonnet-4-6",
        "deduplication_key": "fp123",
        "created_at": None,
        "updated_at": None,
    }
    store = make_store_with_mock_conn(conn)
    result = await _get_finding_impl(store, "abc-123")
    assert result["found"] is True
    assert result["status"] == "validated"
    assert result["cwe"] == "CWE-79"


async def test_get_finding_missing_returns_not_found(conn: AsyncMock) -> None:
    conn.fetchrow.return_value = None
    store = make_store_with_mock_conn(conn)
    result = await _get_finding_impl(store, "nope")
    assert result == {"found": False, "finding_id": "nope"}


# ---------------------------------------------------------------------------
# query_artifacts
# ---------------------------------------------------------------------------


async def test_query_artifacts_empty(conn: AsyncMock) -> None:
    conn.fetch.return_value = []
    store = make_store_with_mock_conn(conn)
    result = await _query_artifacts_impl(store, "fid-x")
    assert result == {"finding_id": "fid-x", "count": 0, "artifacts": []}


async def test_query_artifacts_returns_rows(conn: AsyncMock) -> None:
    conn.fetch.return_value = [
        {
            "id": "art-1",
            "finding_id": "fid-x",
            "content_hash": "sha256:aa",
            "prev_audit_hash": None,
            "oracle_data": {"verdict": "validated"},
            "reproduction_command": "curl ...",
            "scope_token_jti": "j1",
            "sandbox_vm_id": "vm-1",
            "r2_key": "k/1",
            "created_at": None,
        },
    ]
    store = make_store_with_mock_conn(conn)
    result = await _query_artifacts_impl(store, "fid-x")
    assert result["count"] == 1
    assert result["artifacts"][0]["content_hash"] == "sha256:aa"
    assert result["artifacts"][0]["r2_key"] == "k/1"


# ---------------------------------------------------------------------------
# query_experience_kb
# ---------------------------------------------------------------------------


async def test_kb_cwe_only(conn: AsyncMock) -> None:
    conn.fetch.return_value = [
        {
            "id": "f1",
            "cwe": "CWE-918",
            "oracle_method": "oracle_ssrf_oast",
            "evidence_hash": "ev1",
            "url": "https://api.x/y",
            "parameter": "url",
            "status": "validated",
            "program_handle": "acme",
        }
    ]
    store = make_store_with_mock_conn(conn)
    out = await _query_experience_kb_impl(store, "CWE-918", None, None, 10)
    assert out["count"] == 1
    assert out["matches"][0]["oracle_method"] == "oracle_ssrf_oast"
    # Verify no product/version filter clause used
    assert conn.fetch.call_args.args[0].count("ILIKE") == 0


async def test_kb_with_product(conn: AsyncMock) -> None:
    conn.fetch.return_value = []
    store = make_store_with_mock_conn(conn)
    await _query_experience_kb_impl(store, "CWE-79", "wordpress", None, 5)
    sql = conn.fetch.call_args.args[0]
    args = conn.fetch.call_args.args
    assert "ILIKE" in sql
    assert "%wordpress%" in args


async def test_kb_with_product_and_version(conn: AsyncMock) -> None:
    conn.fetch.return_value = []
    store = make_store_with_mock_conn(conn)
    await _query_experience_kb_impl(store, "CWE-79", "wordpress", "6.4", 5)
    args = conn.fetch.call_args.args
    assert any("wordpress" in a and "6.4" in a for a in args if isinstance(a, str))


async def test_kb_status_filter_includes_terminal_only(conn: AsyncMock) -> None:
    conn.fetch.return_value = []
    store = make_store_with_mock_conn(conn)
    await _query_experience_kb_impl(store, "CWE-79", None, None, 5)
    args = conn.fetch.call_args.args
    statuses = next((a for a in args if isinstance(a, list)), None)
    assert statuses is not None
    assert set(statuses) == {"validated", "confirmed", "submitted"}


# ---------------------------------------------------------------------------
# update_finding_status
# ---------------------------------------------------------------------------


async def test_update_status_success_no_lock(conn: AsyncMock) -> None:
    conn.fetchrow.return_value = {"status": "validated"}
    store = make_store_with_mock_conn(conn)
    out = await _update_finding_status_impl(store, "fid-1", "validated", None)
    assert out == {"updated": True, "finding_id": "fid-1", "status": "validated"}


async def test_update_status_optimistic_lock_succeeds(conn: AsyncMock) -> None:
    conn.fetchrow.return_value = {"status": "exploit_attempt"}
    store = make_store_with_mock_conn(conn)
    out = await _update_finding_status_impl(
        store, "fid-1", "exploit_attempt", "hypothesis"
    )
    assert out["updated"] is True


async def test_update_status_optimistic_lock_fails(conn: AsyncMock) -> None:
    conn.fetchrow.return_value = None
    store = make_store_with_mock_conn(conn)
    out = await _update_finding_status_impl(
        store, "fid-1", "exploit_attempt", "hypothesis"
    )
    assert out == {"updated": False, "finding_id": "fid-1", "status": None}


async def test_update_status_rejects_unknown_target() -> None:
    store = make_store_with_mock_conn(AsyncMock())
    with pytest.raises(ValueError):
        await _update_finding_status_impl(store, "fid-1", "totally-bogus", None)


async def test_update_status_rejects_unknown_expected() -> None:
    store = make_store_with_mock_conn(AsyncMock())
    with pytest.raises(ValueError):
        await _update_finding_status_impl(
            store, "fid-1", "validated", "not-a-status"
        )


# ---------------------------------------------------------------------------
# Audit-fix coverage — query_experience_kb LIKE-metacharacter escaping
# (audit reviewer 3, MEDIUM).
# ---------------------------------------------------------------------------


def test_escape_like_handles_percent() -> None:
    from state_mcp.store import _escape_like

    assert _escape_like("foo%bar") == "foo\\%bar"


def test_escape_like_handles_underscore() -> None:
    from state_mcp.store import _escape_like

    assert _escape_like("foo_bar") == "foo\\_bar"


def test_escape_like_handles_backslash() -> None:
    from state_mcp.store import _escape_like

    assert _escape_like("foo\\bar") == "foo\\\\bar"


def test_escape_like_chains_substitutions() -> None:
    """Backslash must be escaped FIRST so it doesn't double-escape the
    backslash from a later substitution (e.g. the ``%`` → ``\\%``
    output)."""
    from state_mcp.store import _escape_like

    assert _escape_like("a%b_c") == "a\\%b\\_c"


async def test_kb_query_escapes_caller_supplied_metacharacters(conn: AsyncMock) -> None:
    """Caller passing ``product='_'`` must NOT match every URL — the
    metacharacter is escaped before the ILIKE pattern is built."""
    conn.fetch.return_value = []
    store = make_store_with_mock_conn(conn)
    await _query_experience_kb_impl(store, "CWE-89", "_", None, 5)
    sent_args = conn.fetch.call_args.args
    pattern = next((a for a in sent_args if isinstance(a, str) and a.startswith("%")), None)
    assert pattern is not None
    assert pattern == "%\\_%"


async def test_kb_query_includes_escape_clause(conn: AsyncMock) -> None:
    conn.fetch.return_value = []
    store = make_store_with_mock_conn(conn)
    await _query_experience_kb_impl(store, "CWE-89", "wordpress", "6.4", 5)
    sql = conn.fetch.call_args.args[0]
    # Source string ``ESCAPE '\\'`` parses as ``ESCAPE '\'`` at runtime.
    assert "ESCAPE '\\'" in sql


async def test_kb_query_escapes_both_product_and_version(conn: AsyncMock) -> None:
    conn.fetch.return_value = []
    store = make_store_with_mock_conn(conn)
    await _query_experience_kb_impl(store, "CWE-89", "p%a", "v_b", 5)
    sent_args = conn.fetch.call_args.args
    pattern = next((a for a in sent_args if isinstance(a, str) and a.startswith("%")), None)
    assert pattern == "%p\\%a%v\\_b%"
