#!/usr/bin/env python3
"""Operator CLI for the T2/T3 approval queue (Phase 2 W7-8).

Subcommands:

    list                  — show all pending approval requests
    list --tier T3        — filter by tier
    show <finding_id>     — pretty-print one queue entry (incl. PoC text)
    approve <finding_id> --as <operator_id> [--reason "..."]
    reject  <finding_id> --as <operator_id> --reason "..."

Environment:

    DATABASE_URL          — postgresql[+asyncpg]://... (required)

The CLI talks directly to the ``approval_queue`` table via the queue helpers
in ``control_plane.domains.approval_gate.queue``. No FastAPI / web layer
needed for sprint scope; later phases may wrap this in an HTTP handler.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import uuid
from datetime import UTC, datetime

import asyncpg
from control_plane.domains.approval_gate import (
    ApprovalQueueError,
    ApprovalTier,
    queue_approve,
    queue_get,
    queue_list_pending,
    queue_reject,
)


def _get_dsn() -> str:
    raw = os.environ.get("DATABASE_URL")
    if not raw:
        print("ERROR: DATABASE_URL is not set", file=sys.stderr)
        sys.exit(2)
    return raw.replace("+asyncpg", "")


def _fmt_age(when: datetime) -> str:
    delta = datetime.now(UTC) - when
    secs = int(delta.total_seconds())
    if secs < 60:
        return f"{secs}s"
    if secs < 3600:
        return f"{secs // 60}m"
    if secs < 86400:
        return f"{secs // 3600}h"
    return f"{secs // 86400}d"


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


async def cmd_list(args: argparse.Namespace) -> int:
    tier = ApprovalTier(args.tier) if args.tier else None
    conn = await asyncpg.connect(_get_dsn())
    try:
        entries = await queue_list_pending(conn, tier)
    finally:
        await conn.close()

    if not entries:
        print("(no pending approval requests)")
        return 0

    print(f"{'finding_id':<38} {'tier':<4} {'age':<6} {'expires_in':<12} actor")
    print("-" * 80)
    for e in entries:
        expires_in = (e.expires_at - datetime.now(UTC)).total_seconds()
        expires_str = (
            f"-{abs(int(expires_in))}s" if expires_in < 0 else f"{int(expires_in)}s"
        )
        actor = e.approver_id or ""
        print(
            f"{str(e.finding_id):<38} {e.tier.value:<4} "
            f"{_fmt_age(e.requested_at):<6} {expires_str:<12} {actor}"
        )
    return 0


async def cmd_show(args: argparse.Namespace) -> int:
    fid = uuid.UUID(args.finding_id)
    conn = await asyncpg.connect(_get_dsn())
    try:
        entry = await queue_get(conn, fid)
    finally:
        await conn.close()

    if entry is None:
        print(f"ERROR: no approval request for finding {fid}", file=sys.stderr)
        return 1

    output = {
        "finding_id": str(entry.finding_id),
        "tier": entry.tier.value,
        "status": entry.status,
        "token": str(entry.token) if entry.token else None,
        "requested_at": entry.requested_at.isoformat(),
        "approved_at": entry.approved_at.isoformat() if entry.approved_at else None,
        "expires_at": entry.expires_at.isoformat(),
        "approver_id": entry.approver_id,
        "approver_id_2": entry.approver_id_2,
        "reason": entry.reason,
        "poc_text": entry.poc_text,
    }
    print(json.dumps(output, indent=2))
    return 0


async def cmd_approve(args: argparse.Namespace) -> int:
    fid = uuid.UUID(args.finding_id)
    conn = await asyncpg.connect(_get_dsn())
    try:
        try:
            token = await queue_approve(conn, fid, args.as_actor, reason=args.reason or "")
        except ApprovalQueueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
    finally:
        await conn.close()

    if token is None:
        print(f"OK (1/2): first approver recorded for T3 finding {fid}")
        return 0

    print(f"APPROVED finding={fid} token={token}")
    return 0


async def cmd_reject(args: argparse.Namespace) -> int:
    fid = uuid.UUID(args.finding_id)
    conn = await asyncpg.connect(_get_dsn())
    try:
        try:
            await queue_reject(conn, fid, args.as_actor, reason=args.reason)
        except ApprovalQueueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
    finally:
        await conn.close()
    print(f"REJECTED finding={fid} reason={args.reason!r}")
    return 0


# ---------------------------------------------------------------------------
# Argparse
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="approve", description="BountyStrike T2/T3 approval CLI")
    sub = p.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="list pending requests")
    p_list.add_argument("--tier", choices=["T0", "T1", "T2", "T3"], help="filter by tier")
    p_list.set_defaults(func=cmd_list)

    p_show = sub.add_parser("show", help="show one request")
    p_show.add_argument("finding_id")
    p_show.set_defaults(func=cmd_show)

    p_approve = sub.add_parser("approve", help="approve one request")
    p_approve.add_argument("finding_id")
    p_approve.add_argument("--as", dest="as_actor", required=True, help="operator id")
    p_approve.add_argument("--reason", default="", help="optional approval note")
    p_approve.set_defaults(func=cmd_approve)

    p_reject = sub.add_parser("reject", help="reject one request")
    p_reject.add_argument("finding_id")
    p_reject.add_argument("--as", dest="as_actor", required=True, help="operator id")
    p_reject.add_argument("--reason", required=True, help="rejection reason (required)")
    p_reject.set_defaults(func=cmd_reject)

    return p


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    return asyncio.run(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
