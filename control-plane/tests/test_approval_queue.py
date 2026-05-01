"""Tests for approval_gate.queue — operator-side T2/T3 queue.

Uses a hand-rolled in-memory fake of the asyncpg.Connection surface we
exercise. Real-Postgres integration is covered separately in
``tests/integration``.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from control_plane.domains.approval_gate import (
    ApprovalQueueError,
    ApprovalTier,
    queue_approve,
    queue_enqueue,
    queue_get,
    queue_list_pending,
    queue_reject,
    queue_wait_for_approval,
)
from control_plane.domains.approval_gate.queue import _backoff_seconds

# ---------------------------------------------------------------------------
# Fake asyncpg.Connection — minimal surface for queue.py
# ---------------------------------------------------------------------------


class FakeConnection:
    """Stores rows in a dict keyed by finding_id; parses INSERT/UPDATE shape.

    We only need to support the queries queue.py issues; this is brittle by
    design — change queue.py SQL and the fake breaks loudly.
    """

    def __init__(self) -> None:
        self.rows: dict[uuid.UUID, dict[str, Any]] = {}
        self._in_txn = 0

    @asynccontextmanager
    async def transaction(self):
        self._in_txn += 1
        try:
            yield
        finally:
            self._in_txn -= 1

    async def execute(self, sql: str, *args: Any) -> str:
        sql_n = " ".join(sql.split())
        if sql_n.startswith("INSERT INTO approval_queue"):
            finding_id, tier, poc_text, expires_at = args
            if finding_id in self.rows:
                return "INSERT 0 0"
            self.rows[finding_id] = {
                "finding_id": finding_id,
                "tier": tier,
                "poc_text": poc_text,
                "status": "pending",
                "token": None,
                "requested_at": datetime.now(UTC),
                "approved_at": None,
                "approver_id": None,
                "approver_id_2": None,
                "reason": None,
                "expires_at": expires_at,
            }
            return "INSERT 0 1"

        if sql_n.startswith("UPDATE approval_queue SET status='expired'"):
            (finding_id,) = args
            if finding_id in self.rows:
                self.rows[finding_id]["status"] = "expired"
                return "UPDATE 1"
            return "UPDATE 0"

        if sql_n.startswith("UPDATE approval_queue SET approver_id=$2, reason=$3"):
            finding_id, approver_id, reason = args
            row = self.rows.get(finding_id)
            if row is None:
                return "UPDATE 0"
            row["approver_id"] = approver_id
            row["reason"] = reason
            return "UPDATE 1"

        if "SET status='approved', approver_id_2" in sql_n:
            finding_id, approver_id_2, token = args
            row = self.rows.get(finding_id)
            if row is None:
                return "UPDATE 0"
            row["status"] = "approved"
            row["approver_id_2"] = approver_id_2
            row["token"] = token
            row["approved_at"] = datetime.now(UTC)
            return "UPDATE 1"

        if "SET status='approved', approver_id=$2" in sql_n:
            finding_id, approver_id, reason, token = args
            row = self.rows.get(finding_id)
            if row is None:
                return "UPDATE 0"
            row["status"] = "approved"
            row["approver_id"] = approver_id
            row["reason"] = reason
            row["token"] = token
            row["approved_at"] = datetime.now(UTC)
            return "UPDATE 1"

        if "SET status='rejected'" in sql_n:
            finding_id, approver_id, reason = args
            row = self.rows.get(finding_id)
            if row is None or row["status"] != "pending":
                return "UPDATE 0"
            row["status"] = "rejected"
            row["approver_id"] = approver_id
            row["reason"] = reason
            return "UPDATE 1"

        raise NotImplementedError(f"Fake doesn't model: {sql_n[:80]}")

    async def fetchrow(self, sql: str, *args: Any) -> dict[str, Any] | None:
        sql_n = " ".join(sql.split())
        if "FROM approval_queue WHERE finding_id = $1 FOR UPDATE" in sql_n:
            (finding_id,) = args
            return self.rows.get(finding_id)
        if "FROM approval_queue WHERE finding_id = $1" in sql_n:
            (finding_id,) = args
            return self.rows.get(finding_id)
        raise NotImplementedError(f"Fake doesn't model fetchrow: {sql_n[:80]}")

    async def fetch(self, sql: str, *args: Any) -> list[dict[str, Any]]:
        sql_n = " ".join(sql.split())
        if "WHERE status = 'pending' AND tier = $1" in sql_n:
            (tier_val,) = args
            return sorted(
                [r for r in self.rows.values()
                 if r["status"] == "pending" and r["tier"] == tier_val],
                key=lambda r: r["requested_at"],
            )
        if "WHERE status = 'pending'" in sql_n:
            return sorted(
                [r for r in self.rows.values() if r["status"] == "pending"],
                key=lambda r: r["requested_at"],
            )
        raise NotImplementedError(f"Fake doesn't model fetch: {sql_n[:80]}")


# ---------------------------------------------------------------------------
# Backoff schedule
# ---------------------------------------------------------------------------


def test_backoff_starts_at_5s():
    assert _backoff_seconds(0) == 5.0


def test_backoff_doubles():
    assert _backoff_seconds(1) == 10.0
    assert _backoff_seconds(2) == 20.0
    assert _backoff_seconds(3) == 40.0


def test_backoff_caps_at_60s():
    assert _backoff_seconds(4) == 60.0
    assert _backoff_seconds(10) == 60.0
    assert _backoff_seconds(100) == 60.0


# ---------------------------------------------------------------------------
# enqueue
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enqueue_inserts_pending_row():
    conn = FakeConnection()
    fid = uuid.uuid4()
    await queue_enqueue(conn, fid, ApprovalTier.T2, poc_text="curl ...")

    row = conn.rows[fid]
    assert row["status"] == "pending"
    assert row["tier"] == "T2"
    assert row["poc_text"] == "curl ..."
    assert row["token"] is None
    assert row["expires_at"] > datetime.now(UTC)


@pytest.mark.asyncio
async def test_enqueue_idempotent_on_duplicate():
    conn = FakeConnection()
    fid = uuid.uuid4()
    await queue_enqueue(conn, fid, ApprovalTier.T2)
    first_requested = conn.rows[fid]["requested_at"]
    await queue_enqueue(conn, fid, ApprovalTier.T2)  # second call
    assert conn.rows[fid]["requested_at"] == first_requested


@pytest.mark.asyncio
async def test_enqueue_uses_custom_sla():
    conn = FakeConnection()
    fid = uuid.uuid4()
    await queue_enqueue(conn, fid, ApprovalTier.T2, sla_seconds=10)
    delta = conn.rows[fid]["expires_at"] - datetime.now(UTC)
    assert delta < timedelta(seconds=11)


# ---------------------------------------------------------------------------
# approve — T2
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_approve_t2_returns_token():
    conn = FakeConnection()
    fid = uuid.uuid4()
    await queue_enqueue(conn, fid, ApprovalTier.T2)

    token = await queue_approve(conn, fid, "operator-1", reason="pre-prod scan")

    assert isinstance(token, uuid.UUID)
    row = conn.rows[fid]
    assert row["status"] == "approved"
    assert row["token"] == token
    assert row["approver_id"] == "operator-1"
    assert row["reason"] == "pre-prod scan"


@pytest.mark.asyncio
async def test_approve_t2_rejects_empty_actor():
    conn = FakeConnection()
    fid = uuid.uuid4()
    await queue_enqueue(conn, fid, ApprovalTier.T2)

    with pytest.raises(ValueError):
        await queue_approve(conn, fid, "", reason="x")


@pytest.mark.asyncio
async def test_approve_missing_request_raises():
    conn = FakeConnection()
    fid = uuid.uuid4()
    with pytest.raises(ApprovalQueueError, match="no approval request"):
        await queue_approve(conn, fid, "operator-1")


@pytest.mark.asyncio
async def test_approve_already_approved_rejects():
    conn = FakeConnection()
    fid = uuid.uuid4()
    await queue_enqueue(conn, fid, ApprovalTier.T2)
    await queue_approve(conn, fid, "operator-1")

    with pytest.raises(ApprovalQueueError, match="is approved"):
        await queue_approve(conn, fid, "operator-2")


@pytest.mark.asyncio
async def test_approve_expired_drifts_to_expired():
    conn = FakeConnection()
    fid = uuid.uuid4()
    await queue_enqueue(conn, fid, ApprovalTier.T2)
    # Force expiry
    conn.rows[fid]["expires_at"] = datetime.now(UTC) - timedelta(seconds=1)

    with pytest.raises(ApprovalQueueError, match="expired"):
        await queue_approve(conn, fid, "operator-1")
    assert conn.rows[fid]["status"] == "expired"


# ---------------------------------------------------------------------------
# approve — T3
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_approve_t3_first_approver_pending():
    conn = FakeConnection()
    fid = uuid.uuid4()
    await queue_enqueue(conn, fid, ApprovalTier.T3)

    result = await queue_approve(conn, fid, "operator-1")

    assert result is None
    assert conn.rows[fid]["approver_id"] == "operator-1"
    assert conn.rows[fid]["status"] == "pending"


@pytest.mark.asyncio
async def test_approve_t3_two_distinct_actors_clears():
    conn = FakeConnection()
    fid = uuid.uuid4()
    await queue_enqueue(conn, fid, ApprovalTier.T3)

    first = await queue_approve(conn, fid, "operator-1")
    assert first is None

    token = await queue_approve(conn, fid, "operator-2")

    assert isinstance(token, uuid.UUID)
    row = conn.rows[fid]
    assert row["status"] == "approved"
    assert row["approver_id"] == "operator-1"
    assert row["approver_id_2"] == "operator-2"
    assert row["token"] == token


@pytest.mark.asyncio
async def test_approve_t3_same_actor_twice_rejects():
    conn = FakeConnection()
    fid = uuid.uuid4()
    await queue_enqueue(conn, fid, ApprovalTier.T3)

    first = await queue_approve(conn, fid, "operator-1")
    assert first is None
    with pytest.raises(ApprovalQueueError, match="already voted"):
        await queue_approve(conn, fid, "operator-1")


# ---------------------------------------------------------------------------
# reject
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reject_pending_marks_rejected():
    conn = FakeConnection()
    fid = uuid.uuid4()
    await queue_enqueue(conn, fid, ApprovalTier.T2)

    await queue_reject(conn, fid, "operator-1", reason="out of scope")

    assert conn.rows[fid]["status"] == "rejected"
    assert conn.rows[fid]["reason"] == "out of scope"


@pytest.mark.asyncio
async def test_reject_missing_request_raises():
    conn = FakeConnection()
    fid = uuid.uuid4()
    with pytest.raises(ApprovalQueueError):
        await queue_reject(conn, fid, "operator-1", reason="x")


@pytest.mark.asyncio
async def test_reject_requires_reason():
    conn = FakeConnection()
    fid = uuid.uuid4()
    await queue_enqueue(conn, fid, ApprovalTier.T2)
    with pytest.raises(ValueError):
        await queue_reject(conn, fid, "operator-1", reason="")


# ---------------------------------------------------------------------------
# get / list_pending
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_returns_entry():
    conn = FakeConnection()
    fid = uuid.uuid4()
    await queue_enqueue(conn, fid, ApprovalTier.T2, poc_text="curl X")

    entry = await queue_get(conn, fid)

    assert entry is not None
    assert entry.finding_id == fid
    assert entry.tier == ApprovalTier.T2
    assert entry.poc_text == "curl X"
    assert entry.status == "pending"


@pytest.mark.asyncio
async def test_get_missing_returns_none():
    conn = FakeConnection()
    assert await queue_get(conn, uuid.uuid4()) is None


@pytest.mark.asyncio
async def test_list_pending_filters_by_tier():
    conn = FakeConnection()
    fid_t2 = uuid.uuid4()
    fid_t3 = uuid.uuid4()
    await queue_enqueue(conn, fid_t2, ApprovalTier.T2)
    await queue_enqueue(conn, fid_t3, ApprovalTier.T3)

    t2_only = await queue_list_pending(conn, ApprovalTier.T2)
    assert [e.finding_id for e in t2_only] == [fid_t2]

    all_pending = await queue_list_pending(conn)
    assert {e.finding_id for e in all_pending} == {fid_t2, fid_t3}


# ---------------------------------------------------------------------------
# wait_for_approval
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_wait_for_approval_returns_token_immediately(monkeypatch):
    conn = FakeConnection()
    fid = uuid.uuid4()
    await queue_enqueue(conn, fid, ApprovalTier.T2)
    token = await queue_approve(conn, fid, "operator-1")

    # Should not even sleep — first poll sees approved.
    result = await queue_wait_for_approval(conn, fid, timeout_seconds=1.0)
    assert result == token


@pytest.mark.asyncio
async def test_wait_for_approval_returns_none_on_rejection(monkeypatch):
    conn = FakeConnection()
    fid = uuid.uuid4()
    await queue_enqueue(conn, fid, ApprovalTier.T2)
    await queue_reject(conn, fid, "operator-1", reason="oos")

    result = await queue_wait_for_approval(conn, fid, timeout_seconds=1.0)
    assert result is None


@pytest.mark.asyncio
async def test_wait_for_approval_returns_none_on_missing():
    conn = FakeConnection()
    result = await queue_wait_for_approval(conn, uuid.uuid4(), timeout_seconds=1.0)
    assert result is None


@pytest.mark.asyncio
async def test_wait_for_approval_times_out(monkeypatch):
    """Timeout returns None without raising."""
    conn = FakeConnection()
    fid = uuid.uuid4()
    await queue_enqueue(conn, fid, ApprovalTier.T2)

    # Patch backoff to 0 so the loop polls fast.
    import control_plane.domains.approval_gate.queue as q
    monkeypatch.setattr(q, "_backoff_seconds", lambda _attempt: 0.001)

    result = await queue_wait_for_approval(conn, fid, timeout_seconds=0.05)
    assert result is None
