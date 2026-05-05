"""Schema contract test for migration 07 (Phase 3 calibration).

Asserts that ``infra/sql/07_phase3_calibration.sql`` has been applied
against the test database. The columns / tables / views below are the
exact set ``scripts/metrics.py``, ``scripts/cost_audit.py``, and
``scripts/reconcile_hunt_outcomes.py`` rely on — drift here breaks the
Phase 3 dashboard.

Skipped when ``BS5_PG_TEST_DSN`` is unset so CI without a Postgres
fixture stays green. To run locally::

    BS5_PG_TEST_DSN=postgresql://bs:bspass@127.0.0.1:5432/bountystrike_dryrun \\
        uv run pytest tests/integration/test_migration_07_phase3.py -v
"""

from __future__ import annotations

import os

import pytest

_DSN = os.environ.get("BS5_PG_TEST_DSN", "").replace("+asyncpg", "")
_skip_if_no_dsn = pytest.mark.skipif(
    not _DSN, reason="BS5_PG_TEST_DSN not set; skipping real-Postgres tests"
)


@pytest.fixture
async def conn():
    if not _DSN:
        pytest.skip("BS5_PG_TEST_DSN not set")
    import asyncpg
    c = await asyncpg.connect(_DSN)
    try:
        yield c
    finally:
        await c.close()


# ──────────────────────────────────────────────────────────────────────
# Schema additions to existing tables
# ──────────────────────────────────────────────────────────────────────


@_skip_if_no_dsn
@pytest.mark.asyncio
@pytest.mark.parametrize("column", ["validated_at", "severity"])
async def test_findings_has_phase3_columns(conn, column: str) -> None:
    row = await conn.fetchrow(
        """
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'findings' AND column_name = $1
        """,
        column,
    )
    assert row is not None, f"findings.{column} missing — run migration 07"


@_skip_if_no_dsn
@pytest.mark.asyncio
async def test_findings_severity_check_constraint_exists(conn) -> None:
    """severity must be P1-P4|info|NULL — enforced by CHECK constraint."""
    row = await conn.fetchrow(
        """
        SELECT pg_get_constraintdef(c.oid) AS def
        FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        WHERE t.relname = 'findings'
          AND pg_get_constraintdef(c.oid) ILIKE '%severity%'
        """,
    )
    assert row is not None, "no CHECK constraint on findings.severity"
    defn = row["def"].lower()
    for tier in ("p1", "p2", "p3", "p4", "info"):
        assert tier in defn, f"severity check missing tier '{tier}': {row['def']}"


@_skip_if_no_dsn
@pytest.mark.asyncio
async def test_findings_validated_at_trigger_exists(conn) -> None:
    """Trigger stamps validated_at on status → 'validated'."""
    row = await conn.fetchrow(
        """
        SELECT trigger_name FROM information_schema.triggers
        WHERE event_object_table = 'findings'
          AND trigger_name = 'trg_findings_validated_at'
        """,
    )
    assert row is not None, "trigger trg_findings_validated_at missing"


# ──────────────────────────────────────────────────────────────────────
# New tables
# ──────────────────────────────────────────────────────────────────────


@_skip_if_no_dsn
@pytest.mark.asyncio
@pytest.mark.parametrize("table", ["operators", "hunt_outcomes"])
async def test_phase3_table_exists(conn, table: str) -> None:
    row = await conn.fetchrow(
        """
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = $1
        """,
        table,
    )
    assert row is not None, f"table {table} missing — run migration 07"


@_skip_if_no_dsn
@pytest.mark.asyncio
async def test_hunt_outcomes_has_unique_constraint(conn) -> None:
    """(program_handle, operator_id, scan_job_id) must be unique so
    reconcile_hunt_outcomes.py can use ON CONFLICT DO NOTHING safely."""
    rows = await conn.fetch(
        """
        SELECT pg_get_constraintdef(c.oid) AS def
        FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        WHERE t.relname = 'hunt_outcomes' AND c.contype = 'u'
        """,
    )
    defs = " ".join(r["def"].lower() for r in rows)
    assert "program_handle" in defs and "operator_id" in defs and "scan_job_id" in defs, (
        f"hunt_outcomes UNIQUE constraint missing expected columns: {defs}"
    )


# ──────────────────────────────────────────────────────────────────────
# New views
# ──────────────────────────────────────────────────────────────────────


@_skip_if_no_dsn
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "view", ["v_confirmed_rate_weekly", "v_scan_cost_by_job", "v_ttv_stats"]
)
async def test_phase3_view_exists_and_queryable(conn, view: str) -> None:
    """View must exist AND be parseable (catches column-rename drift)."""
    row = await conn.fetchrow(
        """
        SELECT table_name FROM information_schema.views
        WHERE table_schema = 'public' AND table_name = $1
        """,
        view,
    )
    assert row is not None, f"view {view} missing — run migration 07"

    # Smoke-test the SELECT planner so column drift surfaces here, not
    # in scripts/metrics.py at the worst possible time.
    await conn.execute(f"SELECT * FROM {view} LIMIT 0")
