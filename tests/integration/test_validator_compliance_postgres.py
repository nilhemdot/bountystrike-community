"""Real-Postgres integration tests for ``audit_validator_compliance``.

The validator-agent (`.claude/agents/validator.md` lines 159-169) is
LLM-driven and supposed to call ``dedup-mcp register_finding`` after
every ``validated`` verdict, but the agent's behavior cannot be
asserted statically. The audit shipped here closes the loop: after an
orchestrator dry-run, run the audit; if any ``validated`` finding
lacks a paired ``dedup_fingerprints`` row, the validator-agent
violated the spec.

These tests seed mixed compliant / non-compliant findings and assert
the audit flags exactly the unmatched ones.

Skipped when ``BS5_PG_TEST_DSN`` is unset so CI without a Postgres
fixture stays green. To run locally::

    BS5_PG_TEST_DSN=postgresql://bs:bspass@127.0.0.1:5432/bountystrike_dryrun \\
        uv run pytest tests/integration/test_validator_compliance_postgres.py -v
"""

from __future__ import annotations

import os
import sys
import uuid

import asyncpg
import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "control-plane", "src"))

from control_plane.domains.evidence_management.services import (  # noqa: E402
    audit_validator_compliance,
)

_DSN = os.environ.get("BS5_PG_TEST_DSN", "").replace("+asyncpg", "")
_skip_if_no_dsn = pytest.mark.skipif(
    not _DSN, reason="BS5_PG_TEST_DSN not set; skipping real-Postgres tests"
)

_TEST_PROGRAM = "validator-compliance-pg-test"


@pytest.fixture
async def conn():
    if not _DSN:
        pytest.skip("BS5_PG_TEST_DSN not set")
    c = await asyncpg.connect(_DSN)
    try:
        await c.execute(
            """
            INSERT INTO programs (handle, platform, name)
            VALUES ($1, 'hackerone', $1)
            ON CONFLICT DO NOTHING
            """,
            _TEST_PROGRAM,
        )
        await _wipe(c)
        yield c
    finally:
        await _wipe(c)
        await c.close()


async def _wipe(c: asyncpg.Connection) -> None:
    """Remove all test rows so each test starts clean and so the
    cross-program-isolation test never sees leftover data."""
    await c.execute(
        """
        DELETE FROM dedup_fingerprints
        WHERE finding_id IN (
            SELECT id::text FROM findings WHERE program_handle = $1
        )
        """,
        _TEST_PROGRAM,
    )
    await c.execute(
        "DELETE FROM findings WHERE program_handle = $1",
        _TEST_PROGRAM,
    )


async def _seed_validated_finding(
    c: asyncpg.Connection,
    cwe: str,
) -> uuid.UUID:
    fid = uuid.uuid4()
    await c.execute(
        """
        INSERT INTO findings (id, program_handle, platform, cwe, status)
        VALUES ($1, $2, 'hackerone', $3, 'validated'::finding_status)
        """,
        fid,
        _TEST_PROGRAM,
        cwe,
    )
    return fid


async def _register_dedup(c: asyncpg.Connection, fid: uuid.UUID, cwe: str) -> None:
    await c.execute(
        """
        INSERT INTO dedup_fingerprints
            (fingerprint_hex, platform, program_handle, vuln_type, finding_id)
        VALUES ($1, 'hackerone', $2, $3, $4)
        ON CONFLICT (fingerprint_hex) DO NOTHING
        """,
        f"fp-{fid.hex}",
        _TEST_PROGRAM,
        cwe,
        str(fid),
    )


# ---------------------------------------------------------------------------
# 1. Empty DB → compliant.
# ---------------------------------------------------------------------------


@_skip_if_no_dsn
@pytest.mark.asyncio
async def test_audit_empty_db_is_compliant(conn: asyncpg.Connection) -> None:
    report = await audit_validator_compliance(conn, program_handle=_TEST_PROGRAM)
    assert report.total_validated == 0
    assert report.missing_ids == ()
    assert report.is_compliant is True


# ---------------------------------------------------------------------------
# 2. Every validated finding has a paired dedup row → compliant.
# ---------------------------------------------------------------------------


@_skip_if_no_dsn
@pytest.mark.asyncio
async def test_audit_all_paired_is_compliant(conn: asyncpg.Connection) -> None:
    fid_a = await _seed_validated_finding(conn, "CWE-79")
    fid_b = await _seed_validated_finding(conn, "CWE-89")
    await _register_dedup(conn, fid_a, "xss")
    await _register_dedup(conn, fid_b, "sqli")

    report = await audit_validator_compliance(conn, program_handle=_TEST_PROGRAM)

    assert report.total_validated == 2
    assert report.is_compliant is True
    assert report.missing_ids == ()


# ---------------------------------------------------------------------------
# 3. No dedup rows at all → every validated finding flagged.
# ---------------------------------------------------------------------------


@_skip_if_no_dsn
@pytest.mark.asyncio
async def test_audit_zero_dedup_rows_flags_every_validated(
    conn: asyncpg.Connection,
) -> None:
    fid_a = await _seed_validated_finding(conn, "CWE-79")
    fid_b = await _seed_validated_finding(conn, "CWE-89")

    report = await audit_validator_compliance(conn, program_handle=_TEST_PROGRAM)

    assert report.total_validated == 2
    assert report.is_compliant is False
    assert report.missing_fingerprint == 2
    assert set(report.missing_ids) == {fid_a, fid_b}


# ---------------------------------------------------------------------------
# 4. Mixed — only the unmatched IDs are flagged.
# ---------------------------------------------------------------------------


@_skip_if_no_dsn
@pytest.mark.asyncio
async def test_audit_mixed_flags_only_unmatched(conn: asyncpg.Connection) -> None:
    paired = await _seed_validated_finding(conn, "CWE-79")
    unpaired_a = await _seed_validated_finding(conn, "CWE-89")
    unpaired_b = await _seed_validated_finding(conn, "CWE-22")
    await _register_dedup(conn, paired, "xss")

    report = await audit_validator_compliance(conn, program_handle=_TEST_PROGRAM)

    assert report.total_validated == 3
    assert report.is_compliant is False
    assert report.missing_fingerprint == 2
    assert set(report.missing_ids) == {unpaired_a, unpaired_b}
    # The compliant finding must NOT appear in missing_ids.
    assert paired not in report.missing_ids


# ---------------------------------------------------------------------------
# 5. Non-validated findings are not audited (hypothesis / archived /
#    duplicate skipped — only ``validated`` is in scope).
# ---------------------------------------------------------------------------


@_skip_if_no_dsn
@pytest.mark.asyncio
async def test_audit_ignores_non_validated_statuses(
    conn: asyncpg.Connection,
) -> None:
    # Validated finding without dedup → flagged.
    flagged = await _seed_validated_finding(conn, "CWE-79")
    # Hypothesis finding without dedup → must NOT be flagged.
    hypo_id = uuid.uuid4()
    await conn.execute(
        """
        INSERT INTO findings (id, program_handle, platform, cwe, status)
        VALUES ($1, $2, 'hackerone', 'CWE-200', 'hypothesis'::finding_status)
        """,
        hypo_id,
        _TEST_PROGRAM,
    )
    # Archived finding without dedup → must NOT be flagged either.
    arch_id = uuid.uuid4()
    await conn.execute(
        """
        INSERT INTO findings (id, program_handle, platform, cwe, status)
        VALUES ($1, $2, 'hackerone', 'CWE-300', 'archived'::finding_status)
        """,
        arch_id,
        _TEST_PROGRAM,
    )

    report = await audit_validator_compliance(conn, program_handle=_TEST_PROGRAM)

    assert report.total_validated == 1
    assert report.missing_ids == (flagged,)
    assert hypo_id not in report.missing_ids
    assert arch_id not in report.missing_ids


# ---------------------------------------------------------------------------
# 6. Program-handle scope — audit on program A doesn't see program B's
#    non-compliant rows.
# ---------------------------------------------------------------------------


@_skip_if_no_dsn
@pytest.mark.asyncio
async def test_audit_program_handle_scope_isolates(
    conn: asyncpg.Connection,
) -> None:
    other_program = "validator-compliance-pg-test-other"
    await conn.execute(
        """
        INSERT INTO programs (handle, platform, name)
        VALUES ($1, 'hackerone', $1)
        ON CONFLICT DO NOTHING
        """,
        other_program,
    )
    try:
        # Non-compliant finding under our program.
        ours = await _seed_validated_finding(conn, "CWE-79")
        # Non-compliant finding under a different program.
        theirs = uuid.uuid4()
        await conn.execute(
            """
            INSERT INTO findings (id, program_handle, platform, cwe, status)
            VALUES ($1, $2, 'hackerone', 'CWE-79', 'validated'::finding_status)
            """,
            theirs,
            other_program,
        )

        report = await audit_validator_compliance(
            conn, program_handle=_TEST_PROGRAM
        )

        assert report.total_validated == 1
        assert report.missing_ids == (ours,)
        assert theirs not in report.missing_ids
    finally:
        await conn.execute(
            "DELETE FROM findings WHERE program_handle = $1", other_program
        )
        await conn.execute(
            "DELETE FROM programs WHERE handle = $1", other_program
        )
