"""Real-Postgres integration tests for ``approval_gate.queue``.

Catches transaction-semantic bugs the FakeConnection in
``control-plane/tests/test_approval_queue.py`` can't model. In particular,
asyncpg's :class:`Connection.transaction` rolls back partial writes on
exception — ``test_t3_first_approver_commits_before_returning`` exists to
guard against the regression that surfaced during the Phase 2 W7-8 dry-run
(`docs/phase1_signoff.md` Round 5).

Skipped when ``BS5_PG_TEST_DSN`` is unset so CI/dev without a Postgres
fixture stays green. To run locally::

    BS5_PG_TEST_DSN=postgresql://bs:bspass@172.18.0.3:5432/bountystrike_dryrun \\
        uv run pytest tests/integration/test_approval_queue_postgres.py -v

The DSN must point to a database that already has migrations 00–05
applied. Each test truncates the ``approval_queue`` and ``findings``
tables before running so tests are order-independent.
"""

from __future__ import annotations

import os
import sys
import uuid

import asyncpg
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, os.path.join(ROOT, "control-plane", "src"))

from control_plane.domains.approval_gate import (  # noqa: E402
    ApprovalQueueError,
    ApprovalTier,
    queue_approve,
    queue_enqueue,
    queue_get,
    queue_list_pending,
    queue_reject,
)

_DSN = os.environ.get("BS5_PG_TEST_DSN", "").replace("+asyncpg", "")
_skip_if_no_dsn = pytest.mark.skipif(
    not _DSN, reason="BS5_PG_TEST_DSN not set; skipping real-Postgres tests"
)


# ---------------------------------------------------------------------------
# Fixture: per-test truncate
# ---------------------------------------------------------------------------


@pytest.fixture
async def conn():
    if not _DSN:
        pytest.skip("BS5_PG_TEST_DSN not set")
    c = await asyncpg.connect(_DSN)
    try:
        # Truncate the queue + any test rows seeded by helpers below.
        await c.execute("TRUNCATE approval_queue CASCADE")
        await c.execute(
            "DELETE FROM findings WHERE program_handle = 'pg-test-fixture'"
        )
        # Make sure the parent scan_job exists — FK target.
        await c.execute(
            """
            INSERT INTO programs (handle, platform, name)
            VALUES ('pg-test-fixture', 'hackerone', 'pg-test-fixture')
            ON CONFLICT DO NOTHING
            """,
        )
        await c.execute(
            """
            INSERT INTO scan_jobs (id, program_handle, platform, status, started_at)
            VALUES ('99999999-9999-9999-9999-999999999999',
                    'pg-test-fixture', 'hackerone', 'queued', now())
            ON CONFLICT (id) DO NOTHING
            """,
        )
        yield c
    finally:
        await c.execute("TRUNCATE approval_queue CASCADE")
        await c.execute(
            "DELETE FROM findings WHERE program_handle = 'pg-test-fixture'"
        )
        await c.close()


async def _seed_finding(c: asyncpg.Connection) -> uuid.UUID:
    """Insert a hypothesis finding tied to the fixture scan_job."""
    fid = uuid.uuid4()
    await c.execute(
        """
        INSERT INTO findings
            (id, job_id, program_handle, platform, status, cwe, url, parameter, raw_finding)
        VALUES ($1, '99999999-9999-9999-9999-999999999999',
                'pg-test-fixture', 'hackerone', 'hypothesis',
                'CWE-79', 'https://pg-test/q', 'q', '{}'::jsonb)
        """,
        fid,
    )
    return fid


# ---------------------------------------------------------------------------
# T3 — the regression test the dry-run uncovered
# ---------------------------------------------------------------------------


@_skip_if_no_dsn
@pytest.mark.asyncio
async def test_t3_first_approver_commits_before_returning(conn):
    """REGRESSION: T3 first-approver must commit ``approver_id`` to disk
    before returning ``None``. Earlier code raised inside the transaction
    block, which asyncpg interprets as rollback — wiping the write.

    Detection mechanism: call approve() twice with the same actor. If the
    first commit landed, the second call must raise ``already voted``. If
    the rollback bug regresses, the second call would re-record the same
    actor as a fresh first-approver and return ``None``.
    """
    fid = await _seed_finding(conn)
    await queue_enqueue(conn, fid, ApprovalTier.T3)

    first = await queue_approve(conn, fid, "op1", reason="first")
    assert first is None

    # Read back from disk (separate query, not the in-process FakeConnection).
    entry = await queue_get(conn, fid)
    assert entry is not None
    assert entry.approver_id == "op1"
    assert entry.status == "pending"
    assert entry.token is None

    # Same actor again — must raise, NOT silently re-record.
    with pytest.raises(ApprovalQueueError, match="already voted"):
        await queue_approve(conn, fid, "op1", reason="repeat")


@_skip_if_no_dsn
@pytest.mark.asyncio
async def test_t3_two_distinct_actors_clears(conn):
    fid = await _seed_finding(conn)
    await queue_enqueue(conn, fid, ApprovalTier.T3)

    first = await queue_approve(conn, fid, "op1")
    assert first is None

    token = await queue_approve(conn, fid, "op2", reason="ATO confirmed")
    assert isinstance(token, uuid.UUID)

    entry = await queue_get(conn, fid)
    assert entry is not None
    assert entry.status == "approved"
    assert entry.approver_id == "op1"
    assert entry.approver_id_2 == "op2"
    assert entry.token == token


# ---------------------------------------------------------------------------
# T2 — happy path + double-approve denial
# ---------------------------------------------------------------------------


@_skip_if_no_dsn
@pytest.mark.asyncio
async def test_t2_single_approval_issues_token(conn):
    fid = await _seed_finding(conn)
    await queue_enqueue(conn, fid, ApprovalTier.T2, poc_text="curl X")

    token = await queue_approve(conn, fid, "operator-1", reason="pre-prod scan")
    assert isinstance(token, uuid.UUID)

    entry = await queue_get(conn, fid)
    assert entry is not None
    assert entry.status == "approved"
    assert entry.token == token
    assert entry.approver_id == "operator-1"
    assert entry.poc_text == "curl X"


@_skip_if_no_dsn
@pytest.mark.asyncio
async def test_t2_double_approve_rejected(conn):
    fid = await _seed_finding(conn)
    await queue_enqueue(conn, fid, ApprovalTier.T2)
    await queue_approve(conn, fid, "operator-1")

    with pytest.raises(ApprovalQueueError, match="is approved"):
        await queue_approve(conn, fid, "operator-2")


# ---------------------------------------------------------------------------
# Reject path
# ---------------------------------------------------------------------------


@_skip_if_no_dsn
@pytest.mark.asyncio
async def test_reject_flips_status_and_blocks_subsequent_approve(conn):
    fid = await _seed_finding(conn)
    await queue_enqueue(conn, fid, ApprovalTier.T2)

    await queue_reject(conn, fid, "operator-1", reason="out of scope")

    entry = await queue_get(conn, fid)
    assert entry is not None
    assert entry.status == "rejected"
    assert entry.reason == "out of scope"

    with pytest.raises(ApprovalQueueError, match="is rejected"):
        await queue_approve(conn, fid, "operator-2")


# ---------------------------------------------------------------------------
# Enqueue idempotency under unique-constraint pressure
# ---------------------------------------------------------------------------


@_skip_if_no_dsn
@pytest.mark.asyncio
async def test_enqueue_idempotent_on_duplicate(conn):
    fid = await _seed_finding(conn)
    await queue_enqueue(conn, fid, ApprovalTier.T2, poc_text="first")
    await queue_enqueue(conn, fid, ApprovalTier.T2, poc_text="second")

    entry = await queue_get(conn, fid)
    assert entry is not None
    # ON CONFLICT DO NOTHING — first poc_text wins.
    assert entry.poc_text == "first"


# ---------------------------------------------------------------------------
# list_pending against real index
# ---------------------------------------------------------------------------


@_skip_if_no_dsn
@pytest.mark.asyncio
async def test_list_pending_filters_by_tier(conn):
    fid_t2 = await _seed_finding(conn)
    fid_t3 = await _seed_finding(conn)
    await queue_enqueue(conn, fid_t2, ApprovalTier.T2)
    await queue_enqueue(conn, fid_t3, ApprovalTier.T3)

    t2_only = await queue_list_pending(conn, ApprovalTier.T2)
    assert {e.finding_id for e in t2_only} == {fid_t2}

    all_pending = await queue_list_pending(conn)
    assert {e.finding_id for e in all_pending} == {fid_t2, fid_t3}
