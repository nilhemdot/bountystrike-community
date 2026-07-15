"""Schema-Pydantic contract test via table introspection.

Purpose: catch schema drift between migration files and runtime
expectations by introspecting the live database schema and validating
table structure (columns, types, constraints).

Mechanism: connect to a Postgres database with all migrations applied,
query ``information_schema`` and ``pg_*`` catalog tables to extract
table definitions, and assert that critical tables exist with expected
columns and types.

Skipped when ``BS5_PG_TEST_DSN`` is unset so CI without a Postgres
fixture stays green. To run locally::

    BS5_PG_TEST_DSN=postgresql://bs:bspass@127.0.0.1:5432/bountystrike_dryrun \\
        uv run pytest tests/integration/test_schema_pydantic_contract.py -v

The DSN must point to a database with all migrations applied. The test
never writes to the database — it only reads schema metadata.
"""

from __future__ import annotations

import os
from pathlib import Path

import asyncpg
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

_DSN = os.environ.get("BS5_PG_TEST_DSN", "").replace("+asyncpg", "")
_skip_if_no_dsn = pytest.mark.skipif(
    not _DSN, reason="BS5_PG_TEST_DSN not set; skipping real-Postgres tests"
)


# ---------------------------------------------------------------------------
# Schema introspection helpers
# ---------------------------------------------------------------------------


async def _get_table_columns(conn: asyncpg.Connection, table_name: str) -> dict[str, str]:
    """Return {column_name: data_type} for the given table."""
    rows = await conn.fetch(
        """
        SELECT column_name, data_type, udt_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = $1
        ORDER BY ordinal_position
        """,
        table_name,
    )
    result = {}
    for row in rows:
        col_name = row["column_name"]
        # Prefer udt_name for custom types (e.g., finding_status enum)
        data_type = row["udt_name"] if row["data_type"] == "USER-DEFINED" else row["data_type"]
        result[col_name] = data_type
    return result


async def _table_exists(conn: asyncpg.Connection, table_name: str) -> bool:
    """Return True if the table exists in the public schema."""
    count = await conn.fetchval(
        """
        SELECT count(*)
        FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = $1
        """,
        table_name,
    )
    return count > 0


# ---------------------------------------------------------------------------
# Core table existence tests
# ---------------------------------------------------------------------------


@_skip_if_no_dsn
@pytest.mark.asyncio
async def test_core_tables_exist() -> None:
    """Verify all core tables from 01_schema.sql exist."""
    conn = await asyncpg.connect(_DSN)
    try:
        expected_tables = [
            "programs",
            "scopes",
            "scope_changes",
            "ev_score_history",
            "scan_jobs",
            "findings",
            "evidence_artifacts",
            "audit_log",
            "agent_sessions",
            "model_costs",
            "report_submissions",
        ]
        for table_name in expected_tables:
            exists = await _table_exists(conn, table_name)
            assert exists, f"Table {table_name} does not exist"
    finally:
        await conn.close()


@_skip_if_no_dsn
@pytest.mark.asyncio
async def test_migration_tables_exist() -> None:
    """Verify tables from additional migrations exist."""
    conn = await asyncpg.connect(_DSN)
    try:
        migration_tables = [
            "dedup_fingerprints",  # 02
            "approval_queue",  # 04
            "recon_assets",  # 06
            "operators",  # 07
            "hunt_outcomes",  # 07
        ]
        for table_name in migration_tables:
            exists = await _table_exists(conn, table_name)
            assert exists, f"Migration table {table_name} does not exist"
    finally:
        await conn.close()


# ---------------------------------------------------------------------------
# Critical column presence tests
# ---------------------------------------------------------------------------


@_skip_if_no_dsn
@pytest.mark.asyncio
async def test_findings_critical_columns() -> None:
    """Verify findings table has all critical columns including raw_finding (Bug-2 regression guard)."""
    conn = await asyncpg.connect(_DSN)
    try:
        columns = await _get_table_columns(conn, "findings")

        # Core columns from 01_schema.sql
        assert "id" in columns
        assert "program_handle" in columns
        assert "platform" in columns
        assert "cwe" in columns
        assert "status" in columns
        assert columns["status"] == "finding_status", "status should be finding_status enum"
        assert "embedding" in columns
        assert "deduplication_key" in columns

        # raw_finding added in 05_findings_raw_finding.sql (Bug-2 guard)
        assert "raw_finding" in columns, "raw_finding column missing (Bug-2 regression)"
        assert columns["raw_finding"] == "jsonb", "raw_finding should be jsonb"
    finally:
        await conn.close()


@_skip_if_no_dsn
@pytest.mark.asyncio
async def test_evidence_artifacts_critical_columns() -> None:
    """Verify evidence_artifacts table structure."""
    conn = await asyncpg.connect(_DSN)
    try:
        columns = await _get_table_columns(conn, "evidence_artifacts")

        assert "id" in columns
        assert "finding_id" in columns
        assert "content_hash" in columns
        assert "prev_audit_hash" in columns
        assert "oracle_data" in columns
        assert columns["oracle_data"] == "jsonb"
        assert "r2_key" in columns
        assert "created_at" in columns
    finally:
        await conn.close()


@_skip_if_no_dsn
@pytest.mark.asyncio
async def test_dedup_fingerprints_structure() -> None:
    """Verify dedup_fingerprints matches migration 02."""
    conn = await asyncpg.connect(_DSN)
    try:
        columns = await _get_table_columns(conn, "dedup_fingerprints")

        assert "fingerprint_hex" in columns
        assert "platform" in columns
        assert "program_handle" in columns
        assert "vuln_type" in columns
        assert "finding_id" in columns
        assert "first_seen_at" in columns
    finally:
        await conn.close()


@_skip_if_no_dsn
@pytest.mark.asyncio
async def test_approval_queue_structure() -> None:
    """Verify approval_queue matches migration 04."""
    conn = await asyncpg.connect(_DSN)
    try:
        columns = await _get_table_columns(conn, "approval_queue")

        # Migration 04 keys the table on finding_id (PRIMARY KEY); there is no
        # separate id column, and the queue timestamp is requested_at.
        assert "finding_id" in columns
        assert "tier" in columns
        assert "status" in columns
        assert "requested_at" in columns
        assert "expires_at" in columns
    finally:
        await conn.close()


@_skip_if_no_dsn
@pytest.mark.asyncio
async def test_recon_assets_structure() -> None:
    """Verify recon_assets matches migration 06."""
    conn = await asyncpg.connect(_DSN)
    try:
        columns = await _get_table_columns(conn, "recon_assets")

        # Migration 06 stores assets keyed on job_id (→ scan_jobs); columns are
        # id/job_id/host/url/tech/status_code/raw/created_at.
        assert "id" in columns
        assert "job_id" in columns
        assert "host" in columns
        assert "url" in columns
        assert "tech" in columns
        assert "created_at" in columns
    finally:
        await conn.close()


@_skip_if_no_dsn
@pytest.mark.asyncio
async def test_operators_table_structure() -> None:
    """Verify operators table from migration 07."""
    conn = await asyncpg.connect(_DSN)
    try:
        columns = await _get_table_columns(conn, "operators")

        # Migration 07: operators is keyed on id (TEXT PK) with display_name +
        # skill_vector; there is no operator_id/name/active.
        assert "id" in columns
        assert "display_name" in columns
        assert "skill_vector" in columns
        assert "created_at" in columns
    finally:
        await conn.close()


@_skip_if_no_dsn
@pytest.mark.asyncio
async def test_hunt_outcomes_structure() -> None:
    """Verify hunt_outcomes table from migration 07."""
    conn = await asyncpg.connect(_DSN)
    try:
        columns = await _get_table_columns(conn, "hunt_outcomes")

        # Migration 07: per-(program, operator, scan_job) calibration summary —
        # ev_rank / submitted_count / confirmed_count, not cwe/outcome/hunted_at.
        assert "id" in columns
        assert "operator_id" in columns
        assert "program_handle" in columns
        assert "ev_rank" in columns
        assert "confirmed_count" in columns
        assert "created_at" in columns
    finally:
        await conn.close()


# ---------------------------------------------------------------------------
# Type validation tests
# ---------------------------------------------------------------------------


@_skip_if_no_dsn
@pytest.mark.asyncio
async def test_findings_embedding_vector_type() -> None:
    """Verify findings.embedding is vector(1536) from pgvector."""
    conn = await asyncpg.connect(_DSN)
    try:
        # Query pg_attribute to check vector dimension
        row = await conn.fetchrow(
            """
            SELECT a.atttypid::regtype::text AS type_name, a.atttypmod
            FROM pg_attribute a
            JOIN pg_class c ON a.attrelid = c.oid
            WHERE c.relname = 'findings' AND a.attname = 'embedding'
            """,
        )
        assert row is not None, "findings.embedding column not found"
        assert "vector" in row["type_name"], f"Expected vector type, got {row['type_name']}"
    finally:
        await conn.close()


@_skip_if_no_dsn
@pytest.mark.asyncio
async def test_finding_status_enum_exists() -> None:
    """Verify finding_status enum type exists with expected values."""
    conn = await asyncpg.connect(_DSN)
    try:
        # Check enum exists
        enum_values = await conn.fetch(
            """
            SELECT e.enumlabel
            FROM pg_type t
            JOIN pg_enum e ON t.oid = e.enumtypid
            WHERE t.typname = 'finding_status'
            ORDER BY e.enumsortorder
            """,
        )
        assert len(enum_values) > 0, "finding_status enum not found"

        labels = [row["enumlabel"] for row in enum_values]
        # Critical states from 01_schema.sql
        assert "hypothesis" in labels
        assert "validated" in labels
        assert "approved" in labels
        assert "submitted" in labels
        assert "confirmed" in labels
        assert "duplicate" in labels
    finally:
        await conn.close()
