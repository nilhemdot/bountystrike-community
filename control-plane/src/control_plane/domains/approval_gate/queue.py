# SPDX-License-Identifier: AGPL-3.0-or-later

"""Operator-side T2/T3 approval queue (Phase 2 W7-8).

Backs the exploit-agent's Step-5 T2 gate (`.claude/agents/exploit-agent.md`):
the agent calls :func:`enqueue` when it needs sandbox sign-off, the operator
runs ``scripts/approve.py approve`` to flip the row to ``approved``, and the
orchestrator polls :func:`wait_for_approval` to fetch the issued token before
re-launching the agent with ``APPROVAL_TOKEN`` set.

The :class:`ApprovalRequest` aggregate in this package handles tier
classification + decision auditing. This module is the durable Postgres-backed
queue that operators interact with — intentionally small surface area to keep
the hot path between exploit-agent and operator obvious.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import asyncpg
import structlog

from .value_objects import ApprovalTier

log = structlog.get_logger("approval_queue")


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ApprovalQueueError(Exception):
    """Raised on queue-shape violations (duplicate enqueue, wrong status)."""


# ---------------------------------------------------------------------------
# Row dataclass
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class QueueEntry:
    """One row from ``approval_queue``."""

    finding_id: uuid.UUID
    tier: ApprovalTier
    poc_text: str | None
    status: str
    token: uuid.UUID | None
    requested_at: datetime
    approved_at: datetime | None
    approver_id: str | None
    approver_id_2: str | None
    reason: str | None
    expires_at: datetime


# ---------------------------------------------------------------------------
# Polling backoff
# ---------------------------------------------------------------------------


def _backoff_seconds(attempt: int) -> float:
    """Exponential backoff capped at 60s — start 5s, doubling each step.

    Attempt 0 → 5s, 1 → 10s, 2 → 20s, 3 → 40s, 4+ → 60s. The early-return
    guards against overflow when callers loop hard against a mocked sleep.
    """
    if attempt >= 4:
        return 60.0
    return 5.0 * (2 ** attempt)


# ---------------------------------------------------------------------------
# Queue API (asyncpg)
# ---------------------------------------------------------------------------


async def enqueue(
    conn: asyncpg.Connection,
    finding_id: uuid.UUID,
    tier: ApprovalTier,
    poc_text: str | None = None,
    sla_seconds: int | None = None,
) -> None:
    """Insert a pending request, or no-op if one already exists.

    The exploit-agent may be re-launched on transient failures; we want
    enqueue to be idempotent so the second invocation finds the existing
    pending row rather than crashing.
    """
    expires_at = datetime.now(UTC) + timedelta(
        seconds=sla_seconds if sla_seconds is not None else tier.review_sla_seconds
    )
    await conn.execute(
        """
        INSERT INTO approval_queue
            (finding_id, tier, poc_text, status, requested_at, expires_at)
        VALUES ($1, $2, $3, 'pending', now(), $4)
        ON CONFLICT (finding_id) DO NOTHING
        """,
        finding_id, tier.value, poc_text, expires_at,
    )
    log.info(
        "approval_queue.enqueued",
        finding_id=str(finding_id),
        tier=tier.value,
        expires_at=expires_at.isoformat(),
    )


async def approve(
    conn: asyncpg.Connection,
    finding_id: uuid.UUID,
    approver_id: str,
    reason: str = "",
) -> uuid.UUID | None:
    """Approve a pending request and return the issued token, or ``None``.

    For T3 (two-person review) the second distinct approver is required;
    the first :func:`approve` call records ``approver_id`` but the row stays
    pending and this function returns ``None``. The second distinct call
    lands ``approver_id_2``, flips status to ``approved``, and returns the
    issued token UUID. T2/T1/T0 clear on the first approval.

    Raises :class:`ApprovalQueueError` if the row is missing, already
    terminal, expired, or the same actor tries to approve a T3 row twice.

    Each branch runs its own transaction so partial state (T3 first
    approver) commits even when the function returns early — keeping the
    "raise on error / return on success" contract simple.
    """
    if not approver_id.strip():
        raise ValueError("approver_id must be non-empty")

    async with conn.transaction():
        row = await conn.fetchrow(
            """
            SELECT tier, status, approver_id, approver_id_2, token, expires_at
            FROM approval_queue
            WHERE finding_id = $1
            FOR UPDATE
            """,
            finding_id,
        )
        if row is None:
            raise ApprovalQueueError(f"no approval request for finding {finding_id}")

        now = datetime.now(UTC)
        if row["status"] == "pending" and row["expires_at"] < now:
            await conn.execute(
                "UPDATE approval_queue SET status='expired' WHERE finding_id=$1",
                finding_id,
            )
            raise ApprovalQueueError(
                f"approval request for {finding_id} expired at {row['expires_at']}"
            )
        if row["status"] != "pending":
            raise ApprovalQueueError(
                f"approval request for {finding_id} is {row['status']}; "
                f"only pending requests accept decisions"
            )

        tier = ApprovalTier(row["tier"])

        if tier == ApprovalTier.T3:
            if row["approver_id"] == approver_id:
                raise ApprovalQueueError(
                    f"actor {approver_id!r} already voted on T3 request {finding_id}"
                )
            if row["approver_id"] is None:
                await conn.execute(
                    """
                    UPDATE approval_queue
                    SET approver_id=$2, reason=$3
                    WHERE finding_id=$1
                    """,
                    finding_id, approver_id, reason,
                )
                log.info(
                    "approval_queue.t3_first_approver",
                    finding_id=str(finding_id),
                    approver=approver_id,
                )
                return None
            token = uuid.uuid4()
            await conn.execute(
                """
                UPDATE approval_queue
                SET status='approved', approver_id_2=$2, token=$3, approved_at=now()
                WHERE finding_id=$1
                """,
                finding_id, approver_id, token,
            )
            log.info(
                "approval_queue.t3_approved",
                finding_id=str(finding_id),
                approver_1=row["approver_id"],
                approver_2=approver_id,
            )
            return token

        # T0/T1/T2 — single approval is enough.
        token = uuid.uuid4()
        await conn.execute(
            """
            UPDATE approval_queue
            SET status='approved', approver_id=$2, reason=$3, token=$4, approved_at=now()
            WHERE finding_id=$1
            """,
            finding_id, approver_id, reason, token,
        )
        log.info(
            "approval_queue.approved",
            finding_id=str(finding_id),
            tier=tier.value,
            approver=approver_id,
        )
        return token


async def reject(
    conn: asyncpg.Connection,
    finding_id: uuid.UUID,
    approver_id: str,
    reason: str,
) -> None:
    """Reject a pending request — single rejection is a hard veto."""
    if not reason.strip():
        raise ValueError("reason must be non-empty for rejection")
    result = await conn.execute(
        """
        UPDATE approval_queue
        SET status='rejected', approver_id=$2, reason=$3
        WHERE finding_id=$1 AND status='pending'
        """,
        finding_id, approver_id, reason,
    )
    if result.endswith("0"):
        raise ApprovalQueueError(
            f"no pending approval request for finding {finding_id}"
        )
    log.warning(
        "approval_queue.rejected",
        finding_id=str(finding_id),
        approver=approver_id,
        reason=reason,
    )


async def get(
    conn: asyncpg.Connection,
    finding_id: uuid.UUID,
) -> QueueEntry | None:
    """Read one row by finding_id."""
    row = await conn.fetchrow(
        """
        SELECT finding_id, tier, poc_text, status, token,
               requested_at, approved_at, approver_id, approver_id_2,
               reason, expires_at
        FROM approval_queue
        WHERE finding_id = $1
        """,
        finding_id,
    )
    if row is None:
        return None
    return QueueEntry(
        finding_id=row["finding_id"],
        tier=ApprovalTier(row["tier"]),
        poc_text=row["poc_text"],
        status=row["status"],
        token=row["token"],
        requested_at=row["requested_at"],
        approved_at=row["approved_at"],
        approver_id=row["approver_id"],
        approver_id_2=row["approver_id_2"],
        reason=row["reason"],
        expires_at=row["expires_at"],
    )


async def list_pending(
    conn: asyncpg.Connection,
    tier: ApprovalTier | None = None,
) -> list[QueueEntry]:
    """List pending requests, optionally filtered by tier."""
    if tier is None:
        rows = await conn.fetch(
            """
            SELECT finding_id, tier, poc_text, status, token,
                   requested_at, approved_at, approver_id, approver_id_2,
                   reason, expires_at
            FROM approval_queue
            WHERE status = 'pending'
            ORDER BY requested_at ASC
            """,
        )
    else:
        rows = await conn.fetch(
            """
            SELECT finding_id, tier, poc_text, status, token,
                   requested_at, approved_at, approver_id, approver_id_2,
                   reason, expires_at
            FROM approval_queue
            WHERE status = 'pending' AND tier = $1
            ORDER BY requested_at ASC
            """,
            tier.value,
        )
    return [
        QueueEntry(
            finding_id=r["finding_id"],
            tier=ApprovalTier(r["tier"]),
            poc_text=r["poc_text"],
            status=r["status"],
            token=r["token"],
            requested_at=r["requested_at"],
            approved_at=r["approved_at"],
            approver_id=r["approver_id"],
            approver_id_2=r["approver_id_2"],
            reason=r["reason"],
            expires_at=r["expires_at"],
        )
        for r in rows
    ]


async def wait_for_approval(
    conn: asyncpg.Connection,
    finding_id: uuid.UUID,
    timeout_seconds: float = 24 * 3600,
) -> uuid.UUID | None:
    """Poll until the request is approved or the timeout elapses.

    Returns the issued token on approval, ``None`` on timeout / rejection /
    expiry. Uses exponential backoff (5s → 10s → 20s → 40s → 60s) to avoid
    hot-looping when operators take hours to approve.
    """
    deadline = asyncio.get_event_loop().time() + timeout_seconds
    attempt = 0
    while asyncio.get_event_loop().time() < deadline:
        entry = await get(conn, finding_id)
        if entry is None:
            log.warning("approval_queue.wait.missing", finding_id=str(finding_id))
            return None
        if entry.status == "approved" and entry.token is not None:
            return entry.token
        if entry.status in ("rejected", "expired"):
            log.warning(
                "approval_queue.wait.terminal",
                finding_id=str(finding_id),
                status=entry.status,
            )
            return None
        await asyncio.sleep(_backoff_seconds(attempt))
        attempt += 1
    log.warning(
        "approval_queue.wait.timeout",
        finding_id=str(finding_id),
        timeout_seconds=timeout_seconds,
    )
    return None


__all__ = [
    "ApprovalQueueError",
    "QueueEntry",
    "approve",
    "enqueue",
    "get",
    "list_pending",
    "reject",
    "wait_for_approval",
]
