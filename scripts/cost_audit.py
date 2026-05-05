#!/usr/bin/env python3
"""Per-scan LLM cost audit (Phase 3 exit criterion #2: avg < $0.20).

Queries the v_scan_cost_by_job view from migration 07 and prints a
table of per-job costs. Flags jobs that exceed the $0.20 solo target.

Usage:
    python scripts/cost_audit.py                       # last 7 days
    python scripts/cost_audit.py --since 30            # last 30 days
    python scripts/cost_audit.py --operator alice
    python scripts/cost_audit.py --job <UUID>          # one job, with model breakdown
    python scripts/cost_audit.py --summary             # just the headline numbers

Environment:
    DATABASE_URL  postgresql[+asyncpg]://...   (required)

Exit codes:
    0  all jobs within budget (or no data)
    1  one or more jobs exceeded $0.20
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import UTC, datetime, timedelta
from uuid import UUID

import asyncpg

BUDGET_USD = 0.20  # Phase 3 exit criterion target


def _get_dsn() -> str:
    raw = os.environ.get("DATABASE_URL")
    if not raw:
        print("ERROR: DATABASE_URL is not set", file=sys.stderr)
        sys.exit(2)
    return raw.replace("+asyncpg", "")


SQL_LIST = """
SELECT
    scan_job_id, program_handle, operator_id,
    started_at, total_cost_usd, exceeds_budget, models_used
FROM v_scan_cost_by_job
WHERE ($1::timestamptz IS NULL OR started_at >= $1)
  AND ($2::text        IS NULL OR operator_id = $2)
ORDER BY started_at DESC
LIMIT 200
"""

SQL_ONE_JOB_BREAKDOWN = """
SELECT
    mc.model,
    SUM(mc.tokens_in)  AS tokens_in,
    SUM(mc.tokens_out) AS tokens_out,
    SUM(mc.cost_usd)   AS cost_usd
FROM scan_jobs sj
JOIN model_costs mc
    ON mc.ts >= sj.started_at
   AND mc.ts <= COALESCE(sj.completed_at, now())
WHERE sj.id = $1
GROUP BY mc.model
ORDER BY cost_usd DESC NULLS LAST
"""


async def cmd_list(conn: asyncpg.Connection, args: argparse.Namespace) -> int:
    since: datetime | None = None
    if args.since is not None:
        since = datetime.now(UTC) - timedelta(days=args.since)

    rows = await conn.fetch(SQL_LIST, since, args.operator)
    if not rows:
        print("(no scan_jobs in window)")
        return 0

    print(
        f"{'started_at':<22} {'scan_job_id':<38} {'program':<20} "
        f"{'operator':<12} {'cost':>8} {'!':<2} {'models':>6}"
    )
    print("-" * 110)

    breaches = 0
    total_cost = 0.0
    for r in rows:
        cost = float(r["total_cost_usd"] or 0.0)
        total_cost += cost
        flag = "!" if r["exceeds_budget"] else " "
        if r["exceeds_budget"]:
            breaches += 1
        ts = r["started_at"].isoformat(timespec="seconds") if r["started_at"] else ""
        print(
            f"{ts:<22} {str(r['scan_job_id']):<38} "
            f"{(r['program_handle'] or '-'):<20} "
            f"{(r['operator_id'] or '-'):<12} "
            f"${cost:>6.4f} {flag:<2} {r['models_used'] or 0:>6}"
        )

    avg = total_cost / len(rows)
    print("-" * 110)
    print(
        f"jobs={len(rows)}  total=${total_cost:.4f}  "
        f"avg=${avg:.4f}  budget=${BUDGET_USD:.2f}  breaches={breaches}"
    )

    if avg > BUDGET_USD:
        print(f"WARN: average cost ${avg:.4f} exceeds budget ${BUDGET_USD:.2f}", file=sys.stderr)
    return 1 if breaches > 0 else 0


async def cmd_one(conn: asyncpg.Connection, args: argparse.Namespace) -> int:
    job_id = UUID(args.job)
    rows = await conn.fetch(SQL_ONE_JOB_BREAKDOWN, job_id)
    if not rows:
        print(f"(no model_costs entries linked to scan_job {job_id})")
        return 0

    print(f"{'model':<48} {'tokens_in':>12} {'tokens_out':>12} {'cost':>10}")
    print("-" * 90)
    total = 0.0
    for r in rows:
        cost = float(r["cost_usd"] or 0.0)
        total += cost
        print(
            f"{r['model']:<48} {int(r['tokens_in'] or 0):>12} "
            f"{int(r['tokens_out'] or 0):>12} ${cost:>8.4f}"
        )
    print("-" * 90)
    print(f"total: ${total:.4f}  budget: ${BUDGET_USD:.2f}")

    if total > BUDGET_USD:
        print(f"WARN: scan ${total:.4f} exceeds budget ${BUDGET_USD:.2f}", file=sys.stderr)
        return 1
    return 0


async def _main(args: argparse.Namespace) -> int:
    conn = await asyncpg.connect(_get_dsn())
    try:
        if args.job:
            return await cmd_one(conn, args)
        return await cmd_list(conn, args)
    finally:
        await conn.close()


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="cost_audit",
        description="Phase 3: per-scan LLM spend audit (target < $0.20)",
    )
    p.add_argument("--since", type=int, default=7, help="last N days (default 7)")
    p.add_argument("--operator", help="filter by operator_id")
    p.add_argument("--job", help="show per-model breakdown for one scan_job UUID")
    return p


def main() -> int:
    args = _build_parser().parse_args()
    return asyncio.run(_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
