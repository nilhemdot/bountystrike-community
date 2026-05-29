# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for ``audit_validator_compliance`` with a fake asyncpg
connection. Exercises the SQL surface and the
:class:`ComplianceReport` invariants without needing a live Postgres.
The real-PG path is covered by
``tests/integration/test_validator_compliance_postgres.py``.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from control_plane.domains.evidence_management.services import (
    ComplianceReport,
    audit_validator_compliance,
)

# ---------------------------------------------------------------------------
# 1. ComplianceReport — invariants on the dataclass.
# ---------------------------------------------------------------------------


def test_compliance_report_empty_is_compliant() -> None:
    report = ComplianceReport(total_validated=0, missing_ids=())
    assert report.missing_fingerprint == 0
    assert report.is_compliant is True


def test_compliance_report_all_paired_is_compliant() -> None:
    report = ComplianceReport(total_validated=5, missing_ids=())
    assert report.is_compliant is True


def test_compliance_report_missing_ids_breaks_compliance() -> None:
    report = ComplianceReport(
        total_validated=3,
        missing_ids=(uuid.uuid4(), uuid.uuid4()),
    )
    assert report.missing_fingerprint == 2
    assert report.is_compliant is False


def test_compliance_report_is_frozen() -> None:
    report = ComplianceReport(total_validated=0, missing_ids=())
    with pytest.raises(AttributeError):
        report.total_validated = 99  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 2. audit_validator_compliance — SQL surface.
# ---------------------------------------------------------------------------


async def test_audit_returns_zero_missing_when_query_empty() -> None:
    conn = AsyncMock()
    conn.fetch.return_value = []
    conn.fetchval.return_value = 0

    report = await audit_validator_compliance(conn)

    assert report.total_validated == 0
    assert report.missing_ids == ()
    assert report.is_compliant is True


async def test_audit_returns_missing_ids_in_query_order() -> None:
    id_a = uuid.uuid4()
    id_b = uuid.uuid4()
    conn = AsyncMock()
    conn.fetch.return_value = [{"id": id_a}, {"id": id_b}]
    conn.fetchval.return_value = 5

    report = await audit_validator_compliance(conn)

    assert report.total_validated == 5
    assert report.missing_ids == (id_a, id_b)
    assert report.missing_fingerprint == 2
    assert report.is_compliant is False


async def test_audit_uses_left_join_against_dedup_fingerprints() -> None:
    """The audit must be a LEFT JOIN — an INNER JOIN would silently
    drop rows that have no dedup entry, hiding exactly the failure
    we're trying to surface."""
    conn = AsyncMock()
    conn.fetch.return_value = []
    conn.fetchval.return_value = 0

    await audit_validator_compliance(conn)

    audit_sql = conn.fetch.call_args.args[0]
    assert "LEFT JOIN dedup_fingerprints" in audit_sql
    assert "d.fingerprint_hex IS NULL" in audit_sql
    assert "f.status = 'validated'" in audit_sql


async def test_audit_compares_finding_id_text_against_uuid_cast() -> None:
    """``dedup_fingerprints.finding_id`` is TEXT (per migration 02)
    while ``findings.id`` is UUID. The audit must explicitly cast the
    UUID to text so a producer-side type confusion (e.g., the
    validator-agent passing a UUID literal as bytes or vice versa)
    surfaces as a missing match instead of an opaque comparison."""
    conn = AsyncMock()
    conn.fetch.return_value = []
    conn.fetchval.return_value = 0

    await audit_validator_compliance(conn)

    audit_sql = conn.fetch.call_args.args[0]
    assert "f.id::text" in audit_sql


async def test_audit_program_handle_filter_passed_to_both_queries() -> None:
    conn = AsyncMock()
    conn.fetch.return_value = []
    conn.fetchval.return_value = 0

    await audit_validator_compliance(conn, program_handle="acme-corp")

    fetch_args = conn.fetch.call_args.args
    fetchval_args = conn.fetchval.call_args.args
    assert fetch_args[1] == "acme-corp"
    assert fetchval_args[1] == "acme-corp"
    # Both queries gate on the program filter so the count and the
    # missing-set always describe the same scope.
    assert "f.program_handle = $1" in fetch_args[0]
    assert "f.program_handle = $1" in fetchval_args[0]


async def test_audit_program_handle_none_means_global_scope() -> None:
    conn = AsyncMock()
    conn.fetch.return_value = []
    conn.fetchval.return_value = 0

    await audit_validator_compliance(conn)  # program_handle defaults to None

    fetch_args = conn.fetch.call_args.args
    assert fetch_args[1] is None
