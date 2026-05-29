#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Phase 3 exit-criteria dashboard (build-plan §10.5 §Exit criteria).

Prints a one-shot health snapshot of the five Phase 3 gates:

    1. confirmed-rate ≥ 70%        (v_confirmed_rate_weekly)
    2. avg scan cost ≤ $0.20       (v_scan_cost_by_job)
    3. P90 time-to-validate < 4h   (v_ttv_stats, P1/P2 only)
    4. EV rank correlation ρ ≥ 0.6 (calibration_service via hunt_outcomes)
    5. dedup recall ≥ 95%          (read from last harness report file)

Usage:
    python scripts/metrics.py
    python scripts/metrics.py --weeks 4              # confirmed-rate window
    python scripts/metrics.py --operator alice
    python scripts/metrics.py --json

Environment:
    DATABASE_URL  postgresql[+asyncpg]://...   (required)

Exit codes:
    0  all five gates green
    1  one or more gates red
"""

from __future__ import annotations

import argparse
import asyncio
import json as jsonlib
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import asyncpg

# control-plane on PYTHONPATH? Try direct import; fall back to sys.path nudge.
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "control-plane" / "src"))
from control_plane.domains.program_ranking.services.calibration_service import (  # noqa: E402
    calibration_report,
)
from control_plane.domains.program_ranking.value_objects.hunt_outcome import (  # noqa: E402
    HuntOutcome,
)

# Phase 3 thresholds (from build-plan §10.5).
CONFIRMED_RATE_TARGET = 0.70
SCAN_COST_TARGET = 0.20
TTV_P90_TARGET_HOURS = 4.0
EV_RHO_TARGET = 0.60
DEDUP_RECALL_TARGET = 0.95

# Last dedup recall harness report — written by tests/integration/test_dedup_recall_phase3.py.
DEDUP_REPORT_PATH = REPO_ROOT / "tests" / "reports" / "dedup_recall_phase3.json"


def _get_dsn() -> str:
    raw = os.environ.get("DATABASE_URL")
    if not raw:
        print("ERROR: DATABASE_URL is not set", file=sys.stderr)
        sys.exit(2)
    return raw.replace("+asyncpg", "")


# ---------------------------------------------------------------------------
# Metric queries (mirror the views from migration 07).
# ---------------------------------------------------------------------------

SQL_CONFIRMED_RATE = """
SELECT
    SUM(confirmed)::float / NULLIF(SUM(total_submitted), 0) AS rate,
    SUM(total_submitted) AS total_submitted,
    SUM(confirmed)       AS confirmed
FROM v_confirmed_rate_weekly
WHERE week >= $1::timestamptz
"""

SQL_SCAN_COST_AVG = """
SELECT
    AVG(total_cost_usd)::float                                       AS avg_cost,
    COUNT(*)                                                         AS jobs,
    COUNT(*) FILTER (WHERE exceeds_budget)                           AS breaches
FROM v_scan_cost_by_job
WHERE ($1::text IS NULL OR operator_id = $1)
  AND started_at >= $2::timestamptz
"""

SQL_TTV_STATS = """
SELECT severity, p90_ttv_hours, sla_breach_count, total
FROM v_ttv_stats
"""

SQL_HUNT_OUTCOMES = """
SELECT
    program_handle, operator_id,
    scan_job_id::text AS scan_job_id, ev_rank,
    submitted_count, confirmed_count,
    period_start, period_end
FROM hunt_outcomes
WHERE ev_rank IS NOT NULL
  AND submitted_count > 0
  AND ($1::text IS NULL OR operator_id = $1)
LIMIT 500
"""


# ---------------------------------------------------------------------------
# Gate evaluation — each function returns (label, passed, detail_dict).
# ---------------------------------------------------------------------------


async def gate_confirmed_rate(
    conn: asyncpg.Connection, since: datetime
) -> tuple[str, bool, dict]:
    row = await conn.fetchrow(SQL_CONFIRMED_RATE, since)
    if row is None or row["total_submitted"] is None:
        return ("confirmed_rate", False, {"reason": "no submissions in window"})
    rate = float(row["rate"] or 0.0)
    return (
        "confirmed_rate",
        rate >= CONFIRMED_RATE_TARGET,
        {
            "rate": rate,
            "target": CONFIRMED_RATE_TARGET,
            "submitted": int(row["total_submitted"]),
            "confirmed": int(row["confirmed"] or 0),
        },
    )


async def gate_scan_cost(
    conn: asyncpg.Connection, operator: str | None, since: datetime
) -> tuple[str, bool, dict]:
    row = await conn.fetchrow(SQL_SCAN_COST_AVG, operator, since)
    if row is None or row["jobs"] == 0:
        return ("scan_cost", False, {"reason": "no scan_jobs in window"})
    avg = float(row["avg_cost"] or 0.0)
    return (
        "scan_cost",
        avg <= SCAN_COST_TARGET,
        {
            "avg_usd": avg,
            "target_usd": SCAN_COST_TARGET,
            "jobs": int(row["jobs"]),
            "breaches": int(row["breaches"] or 0),
        },
    )


async def gate_ttv(conn: asyncpg.Connection) -> tuple[str, bool, dict]:
    rows = await conn.fetch(SQL_TTV_STATS)
    if not rows:
        return ("ttv_p90", False, {"reason": "no validated P1/P2 findings"})
    worst_p90 = 0.0
    breakdown = {}
    for r in rows:
        p90 = float(r["p90_ttv_hours"] or 0.0)
        worst_p90 = max(worst_p90, p90)
        breakdown[r["severity"]] = {
            "p90_hours": p90,
            "breaches": int(r["sla_breach_count"] or 0),
            "total": int(r["total"] or 0),
        }
    return (
        "ttv_p90",
        worst_p90 <= TTV_P90_TARGET_HOURS,
        {"p90_hours": worst_p90, "target_hours": TTV_P90_TARGET_HOURS, "by_severity": breakdown},
    )


async def gate_ev_correlation(
    conn: asyncpg.Connection, operator: str | None
) -> tuple[str, bool, dict]:
    rows = await conn.fetch(SQL_HUNT_OUTCOMES, operator)
    outcomes = [
        HuntOutcome(
            program_handle=r["program_handle"],
            operator_id=r["operator_id"],
            scan_job_id=r["scan_job_id"],
            ev_rank=r["ev_rank"],
            submitted_count=r["submitted_count"],
            confirmed_count=r["confirmed_count"],
            period_start=r["period_start"],
            period_end=r["period_end"],
        )
        for r in rows
    ]
    report = calibration_report(outcomes)
    return (
        "ev_rank_correlation",
        bool(report["passes"]),
        {
            "rho": report["rho"],
            "p_value": report["p_value"],
            "target_rho": EV_RHO_TARGET,
            "n_outcomes": report["n_outcomes"],
        },
    )


def gate_dedup_recall() -> tuple[str, bool, dict]:
    if not DEDUP_REPORT_PATH.exists():
        return (
            "dedup_recall",
            False,
            {"reason": f"no harness report at {DEDUP_REPORT_PATH}"},
        )
    data = jsonlib.loads(DEDUP_REPORT_PATH.read_text())
    recall = float(data.get("recall", 0.0))
    return (
        "dedup_recall",
        recall >= DEDUP_RECALL_TARGET,
        {
            "recall": recall,
            "target": DEDUP_RECALL_TARGET,
            "n_pairs": int(data.get("n_pairs", 0)),
            "fp_rate": float(data.get("fp_rate", 0.0)),
            "report_age_seconds": int(
                datetime.now(UTC).timestamp() - DEDUP_REPORT_PATH.stat().st_mtime
            ),
        },
    )


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def _print_human(gates: list[tuple[str, bool, dict]]) -> None:
    print("\nPhase 3 exit-criteria dashboard")
    print("=" * 60)
    for label, passed, detail in gates:
        marker = "OK " if passed else "FAIL"
        print(f"[{marker}] {label}")
        for k, v in detail.items():
            if isinstance(v, dict):
                print(f"        {k}:")
                for kk, vv in v.items():
                    print(f"          {kk}: {vv}")
            elif isinstance(v, float):
                print(f"        {k}: {v:.4f}")
            else:
                print(f"        {k}: {v}")
    print("=" * 60)
    n_pass = sum(1 for _, ok, _ in gates if ok)
    print(f"{n_pass} / {len(gates)} gates passing")


async def _main(args: argparse.Namespace) -> int:
    since = datetime.now(UTC) - timedelta(weeks=args.weeks)

    conn = await asyncpg.connect(_get_dsn())
    try:
        gates = [
            await gate_confirmed_rate(conn, since),
            await gate_scan_cost(conn, args.operator, since),
            await gate_ttv(conn),
            await gate_ev_correlation(conn, args.operator),
        ]
    finally:
        await conn.close()

    gates.append(gate_dedup_recall())  # offline (file)

    if args.json:
        print(jsonlib.dumps(
            {label: {"passed": ok, **detail} for label, ok, detail in gates},
            indent=2,
            default=str,
        ))
    else:
        _print_human(gates)

    return 0 if all(ok for _, ok, _ in gates) else 1


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="metrics",
        description="Phase 3 exit-criteria health dashboard",
    )
    p.add_argument("--weeks", type=int, default=4, help="window for cost + confirmed-rate")
    p.add_argument("--operator", help="filter cost + EV correlation by operator_id")
    p.add_argument("--json", action="store_true", help="emit JSON instead of human output")
    return p


def main() -> int:
    args = _build_parser().parse_args()
    return asyncio.run(_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
