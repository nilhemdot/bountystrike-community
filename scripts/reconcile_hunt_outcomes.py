#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Reconcile report_submissions → hunt_outcomes (Phase 3 calibration loop).

For each scan_job whose findings have been confirmed/rejected by the bug
bounty platform, this script writes a hunt_outcomes row attributing the
outcome to (program_handle, operator_id, scan_job_id) so the EV
calibration service can compute Spearman ρ between predicted EV rank and
actual find-rate.

Run periodically (cron or manual) after platform responses have arrived:

    python scripts/reconcile_hunt_outcomes.py
    python scripts/reconcile_hunt_outcomes.py --since 30   # last 30 days
    python scripts/reconcile_hunt_outcomes.py --dry-run    # preview only

Environment:
    DATABASE_URL  postgresql[+asyncpg]://...   (required)

Algorithm:
    1. Pick scan_jobs with at least one report_submission AND not yet
       reconciled (no hunt_outcomes row for that scan_job_id).
    2. For each scan_job:
         - submitted_count = COUNT(report_submissions WHERE finding.job_id=…)
         - confirmed_count = COUNT(report_submissions WHERE … status='confirmed')
         - ev_rank = rank of program_handle in ev_score_history at scan_jobs.started_at
                     (ROW_NUMBER OVER ORDER BY ev_score DESC, latest row per program ≤ started_at)
    3. Insert into hunt_outcomes (skip if already reconciled).

The ev_rank derivation needs explanation:
    ev_score_history is a time-series of (program_handle, computed_at,
    ev_score). For each program we take its most recent score before
    started_at, then ROW_NUMBER over those scores DESC. Programs with
    no prior score (cold start) are skipped (NULL ev_rank).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import UTC, datetime, timedelta
from uuid import UUID

import asyncpg


def _get_dsn() -> str:
    raw = os.environ.get("DATABASE_URL")
    if not raw:
        print("ERROR: DATABASE_URL is not set", file=sys.stderr)
        sys.exit(2)
    return raw.replace("+asyncpg", "")


# ---------------------------------------------------------------------------
# SQL — kept inline so the script is self-contained and reviewable.
# ---------------------------------------------------------------------------

# Find candidate scan_jobs: those with submissions but no hunt_outcomes row yet.
SQL_FIND_CANDIDATES = """
SELECT DISTINCT
    sj.id            AS scan_job_id,
    sj.program_handle,
    sj.operator_id,
    sj.started_at,
    sj.completed_at
FROM scan_jobs sj
JOIN findings f         ON f.job_id = sj.id
JOIN report_submissions rs ON rs.finding_id = f.id
LEFT JOIN hunt_outcomes ho ON ho.scan_job_id = sj.id
WHERE ho.id IS NULL
  AND sj.operator_id IS NOT NULL
  AND sj.program_handle IS NOT NULL
  AND ($1::timestamptz IS NULL OR sj.started_at >= $1)
ORDER BY sj.started_at DESC
"""

# Aggregate submission counts for one scan_job.
SQL_COUNT_SUBMISSIONS = """
SELECT
    COUNT(*)                                            AS submitted_count,
    COUNT(*) FILTER (WHERE rs.status = 'confirmed')     AS confirmed_count
FROM findings f
JOIN report_submissions rs ON rs.finding_id = f.id
WHERE f.job_id = $1
"""

# ev_rank: rank programs by latest ev_score recorded ≤ scan_started_at.
SQL_EV_RANK = """
WITH latest_per_program AS (
    SELECT DISTINCT ON (program_handle)
        program_handle,
        ev_score
    FROM ev_score_history
    WHERE computed_at <= $1
    ORDER BY program_handle, computed_at DESC
),
ranked AS (
    SELECT
        program_handle,
        ROW_NUMBER() OVER (ORDER BY ev_score DESC) AS rnk
    FROM latest_per_program
)
SELECT rnk FROM ranked WHERE program_handle = $2
"""

SQL_ENSURE_OPERATOR = """
INSERT INTO operators (id, display_name)
VALUES ($1, $2)
ON CONFLICT (id) DO NOTHING
"""

SQL_INSERT_OUTCOME = """
INSERT INTO hunt_outcomes (
    program_handle, operator_id, scan_job_id, ev_rank,
    submitted_count, confirmed_count, period_start, period_end
)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
ON CONFLICT (program_handle, operator_id, scan_job_id) DO NOTHING
RETURNING id
"""


# ---------------------------------------------------------------------------
# Reconciliation
# ---------------------------------------------------------------------------


async def reconcile(
    conn: asyncpg.Connection,
    since: datetime | None,
    dry_run: bool,
) -> int:
    candidates = await conn.fetch(SQL_FIND_CANDIDATES, since)
    if not candidates:
        print("(no scan_jobs with un-reconciled submissions)")
        return 0

    written = 0
    for cand in candidates:
        scan_job_id: UUID = cand["scan_job_id"]
        program_handle: str = cand["program_handle"]
        operator_id: str = cand["operator_id"]
        started_at: datetime = cand["started_at"]
        completed_at: datetime | None = cand["completed_at"]

        # Counts — query is COUNT(*) so always returns one row.
        counts = await conn.fetchrow(SQL_COUNT_SUBMISSIONS, scan_job_id)
        if counts is None:
            continue
        submitted = int(counts["submitted_count"])
        confirmed = int(counts["confirmed_count"])

        # EV rank at scan-start time
        ev_rank_row = await conn.fetchrow(SQL_EV_RANK, started_at, program_handle)
        ev_rank = int(ev_rank_row["rnk"]) if ev_rank_row else None

        msg = (
            f"scan_job={scan_job_id}  program={program_handle}  "
            f"operator={operator_id}  ev_rank={ev_rank}  "
            f"submitted={submitted}  confirmed={confirmed}"
        )

        if dry_run:
            print(f"[DRY] would write: {msg}")
            written += 1
            continue

        async with conn.transaction():
            # operator_id may be a free-form string from older scan_jobs
            # rows; ensure the FK target exists before inserting.
            await conn.execute(SQL_ENSURE_OPERATOR, operator_id, operator_id)
            row_id = await conn.fetchval(
                SQL_INSERT_OUTCOME,
                program_handle, operator_id, scan_job_id, ev_rank,
                submitted, confirmed, started_at, completed_at,
            )

        if row_id is not None:
            print(f"[OK]  wrote outcome id={row_id}: {msg}")
            written += 1
        else:
            # Race: another reconciler beat us. Idempotent.
            print(f"[SKIP] already reconciled: {msg}")

    print(f"\nReconciled {written} of {len(candidates)} candidate scan_jobs.")
    return 0


async def _main(args: argparse.Namespace) -> int:
    since: datetime | None = None
    if args.since is not None:
        since = datetime.now(UTC) - timedelta(days=args.since)

    conn = await asyncpg.connect(_get_dsn())
    try:
        return await reconcile(conn, since, dry_run=args.dry_run)
    finally:
        await conn.close()


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="reconcile_hunt_outcomes",
        description="Phase 3: backfill hunt_outcomes from report_submissions",
    )
    p.add_argument("--since", type=int, help="only scan_jobs newer than N days")
    p.add_argument("--dry-run", action="store_true", help="preview, do not write")
    return p


def main() -> int:
    args = _build_parser().parse_args()
    return asyncio.run(_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
