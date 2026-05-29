# SPDX-License-Identifier: AGPL-3.0-or-later

"""Validator-spec compliance audit.

The validator-agent (`.claude/agents/validator.md` lines 159-169) is
specified to call ``dedup-mcp register_finding`` after every
``validated`` verdict, persisting a row in ``dedup_fingerprints`` keyed
by the structural fingerprint. The agent is LLM-driven, so no static
test can prove it follows the spec — the only honest check is a
post-run invariant: every ``findings.status='validated'`` row must
have a paired ``dedup_fingerprints.finding_id`` entry.

This module ships :func:`audit_validator_compliance`, a read-only
asyncpg query that returns a structured report. Operator workflows
run it after an orchestrator dry-run; CI runs it as a gate.

The audit deliberately compares ``dedup_fingerprints.finding_id`` (TEXT
in migration 02) against ``findings.id::text`` so a UUID/text mismatch
in the validator's MCP call surfaces as a missing match — not a silent
type-coercion success.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ComplianceReport:
    """Result of a validator-compliance audit.

    Attributes:
        total_validated: Count of ``findings.status = 'validated'`` rows
            in scope.
        missing_ids: List of finding UUIDs that lack a paired
            ``dedup_fingerprints.finding_id`` entry. Order matches the
            DB query (``ORDER BY findings.created_at ASC``) so failures
            point at the oldest non-compliant rows first.
    """

    total_validated: int
    missing_ids: tuple[uuid.UUID, ...]

    @property
    def missing_fingerprint(self) -> int:
        return len(self.missing_ids)

    @property
    def is_compliant(self) -> bool:
        return self.missing_fingerprint == 0


_AUDIT_SQL = """
SELECT f.id
FROM findings f
LEFT JOIN dedup_fingerprints d ON d.finding_id = f.id::text
WHERE f.status = 'validated'
  AND d.fingerprint_hex IS NULL
  AND ($1::text IS NULL OR f.program_handle = $1)
ORDER BY f.created_at ASC
"""

_TOTAL_SQL = """
SELECT count(*)
FROM findings f
WHERE f.status = 'validated'
  AND ($1::text IS NULL OR f.program_handle = $1)
"""


async def audit_validator_compliance(
    conn,
    *,
    program_handle: str | None = None,
) -> ComplianceReport:
    """Return the set of validated findings missing a dedup fingerprint.

    Args:
        conn: An ``asyncpg.Connection`` (or anything with the same
            ``fetch``/``fetchval`` async interface).
        program_handle: Optional scope filter. ``None`` audits across
            every program; pass a handle to scope to a single program
            (useful when running the audit per-job).

    Returns:
        :class:`ComplianceReport`. ``is_compliant`` is True iff every
        validated finding has a paired ``dedup_fingerprints`` entry.
    """
    rows = await conn.fetch(_AUDIT_SQL, program_handle)
    missing = tuple(r["id"] for r in rows)
    total = await conn.fetchval(_TOTAL_SQL, program_handle)
    return ComplianceReport(
        total_validated=int(total or 0),
        missing_ids=missing,
    )


__all__ = ["ComplianceReport", "audit_validator_compliance"]
