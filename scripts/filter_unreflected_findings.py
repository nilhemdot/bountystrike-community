#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Post-scanner FP filter — drops unreflected xss-candidate hypothesis rows.

The recon-stage reflection probe (control_plane.domains.recon.service)
catches FP candidates emitted by recon's _classify_parameter fallthrough.
It does NOT catch candidates emitted directly by scanner-agent's step-6
INSERT — most notably arjun emissions that surfaced via response-anomaly
heuristics (length / status-code / response-time) rather than reflection.

This script closes the post-scanner gap. For each
``status='hypothesis' AND cwe='xss-candidate'`` row scoped to one
``scan_jobs.id``, it sends a single GET with a high-entropy sentinel
injected into the parameter and updates ``status='rejected'`` (with an
audit-trail tag in ``raw_finding.fp_class``) for any row that does not
reflect.

Usage::

    python scripts/filter_unreflected_findings.py --job-id <UUID>
    python scripts/filter_unreflected_findings.py --job-id <UUID> --dry-run
    python scripts/filter_unreflected_findings.py --job-id <UUID> --concurrency 8

Environment::

    DATABASE_URL    postgresql[+asyncpg]://...   (required)

Exit codes::

    0  filter ran (with or without drops)
    1  zero hypothesis rows for that job_id (likely wrong UUID)
    2  missing env / malformed args
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import secrets
import sys
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse
from uuid import UUID

import asyncpg
from control_plane.domains.recon.probers import HttpxReflectionProber

DEFAULT_CONCURRENCY = 4

SELECT_HYPOTHESIS_XSS_SQL = """
SELECT id, url, parameter
FROM findings
WHERE job_id = $1
  AND status = 'hypothesis'
  AND cwe = 'xss-candidate'
"""

UPDATE_REJECTED_SQL = """
UPDATE findings
SET status = 'rejected',
    raw_finding = jsonb_set(
        coalesce(raw_finding, '{}'::jsonb),
        '{fp_class}',
        to_jsonb($2::text)
    ),
    updated_at = now()
WHERE id = $1
"""

FP_CLASS_TAG = "unreflected-xss-postscan"


class ReflectionProber(Protocol):
    async def probe(self, url: str, parameter: str, sentinel: str) -> bool: ...


@dataclass(frozen=True, slots=True)
class FilterResult:
    """Summary of one filter run."""

    total: int
    dropped: int
    kept: int
    errors: int
    dry_run: bool


def _inject_param(url: str, parameter: str, value: str) -> str:
    parsed = urlparse(url)
    query = parse_qs(parsed.query, keep_blank_values=True)
    query[parameter] = [value]
    new_query = urlencode(query, doseq=True)
    return urlunparse(parsed._replace(query=new_query))


async def _probe_one(
    prober: ReflectionProber, url: str, parameter: str
) -> bool | None:
    """Returns True/False on success; None if the probe raised."""
    sentinel = f"BS5R{secrets.token_hex(8)}"
    probe_url = _inject_param(url, parameter, sentinel)
    try:
        return await prober.probe(probe_url, parameter, sentinel)
    except Exception:
        return None


async def filter_unreflected(
    conn: Any,
    job_id: UUID,
    prober: ReflectionProber,
    *,
    concurrency: int = DEFAULT_CONCURRENCY,
    dry_run: bool = False,
) -> FilterResult:
    """Core filter loop — separated from CLI plumbing for unit testing."""
    rows = await conn.fetch(SELECT_HYPOTHESIS_XSS_SQL, job_id)
    if not rows:
        return FilterResult(total=0, dropped=0, kept=0, errors=0, dry_run=dry_run)

    semaphore = asyncio.Semaphore(concurrency)

    async def _check(row) -> tuple[Any, bool | None]:
        async with semaphore:
            reflected = await _probe_one(prober, row["url"], row["parameter"])
            return row, reflected

    results = await asyncio.gather(*(_check(r) for r in rows))

    dropped = 0
    kept = 0
    errors = 0
    for row, reflected in results:
        if reflected is None:
            # Probe error — match recon's safe-default (treat as no reflection
            # and drop) to avoid leaking FPs through on a flaky network.
            errors += 1
            reflected = False
        if reflected:
            kept += 1
            continue
        if not dry_run:
            await conn.execute(UPDATE_REJECTED_SQL, row["id"], FP_CLASS_TAG)
        dropped += 1

    return FilterResult(
        total=len(rows),
        dropped=dropped,
        kept=kept,
        errors=errors,
        dry_run=dry_run,
    )


# ---------------------------------------------------------------------------
# CLI plumbing
# ---------------------------------------------------------------------------


def _get_dsn() -> str:
    raw = os.environ.get("DATABASE_URL")
    if not raw:
        print("ERROR: DATABASE_URL is not set", file=sys.stderr)
        sys.exit(2)
    return raw.replace("+asyncpg", "")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Drop unreflected xss-candidate hypothesis rows for one scan_job"
    )
    parser.add_argument(
        "--job-id", required=True, help="UUID of the scan_jobs.id to filter"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print actions without updating the database",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=DEFAULT_CONCURRENCY,
        help=f"Parallel probe count (default {DEFAULT_CONCURRENCY})",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the result summary as one JSON line on stdout",
    )
    return parser.parse_args(argv)


async def _main_async(args: argparse.Namespace) -> int:
    try:
        job_id = UUID(args.job_id)
    except ValueError:
        print(f"ERROR: --job-id is not a valid UUID: {args.job_id}", file=sys.stderr)
        return 2

    dsn = _get_dsn()
    conn = await asyncpg.connect(dsn)
    try:
        prober = HttpxReflectionProber()
        result = await filter_unreflected(
            conn,
            job_id,
            prober,
            concurrency=args.concurrency,
            dry_run=args.dry_run,
        )
    finally:
        await conn.close()

    payload = {
        "job_id": str(job_id),
        "total": result.total,
        "dropped": result.dropped,
        "kept": result.kept,
        "errors": result.errors,
        "dry_run": result.dry_run,
        "fp_class_tag": FP_CLASS_TAG,
    }
    if args.json:
        print(json.dumps(payload))
    else:
        verb = "would drop" if result.dry_run else "dropped"
        print(
            f"job_id={job_id} total={result.total} "
            f"{verb}={result.dropped} kept={result.kept} errors={result.errors}"
        )
    return 0 if result.total > 0 else 1


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    return asyncio.run(_main_async(args))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
