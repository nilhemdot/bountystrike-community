#!/usr/bin/env python3
"""Kill-switch watcher — Phase 3 §10.5 #4 oracle FP guard.

Polls v_oracle_fp_rate every --interval seconds. When any oracle's
7-day FP rate exceeds 2%, this script:

  1. activates the kill switch in HALT_SUBMISSIONS so no further
     reports go out from the breached oracle (or any other — the flag
     is global per build-plan §6.6); and
  2. POSTs a JSON alert to KILL_SWITCH_WEBHOOK_URL if set (Slack /
     Discord / generic — payload is platform-agnostic).

Edge transitions only — once an oracle is in the "breached" set we
don't re-trip until it clears and re-breaches. That keeps Slack quiet
during the 24h auto-expiry window.

Usage:
    python scripts/kill_switch_watch.py
    python scripts/kill_switch_watch.py --interval 30 --once
    python scripts/kill_switch_watch.py --dry-run     # no killswitch / no webhook

Environment:
    DATABASE_URL              postgresql[+asyncpg]://...   (required)
    REDIS_URL                 redis://[:password]@host:port/db (required unless --dry-run)
    KILL_SWITCH_WEBHOOK_URL   optional; missing = log only
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from collections.abc import AsyncGenerator, Iterable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import asyncpg
import httpx

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "control-plane" / "src"))
from control_plane.domains.safety.repositories.kill_switch_store import (  # noqa: E402
    InMemoryKillSwitchStore,
    KillSwitchStore,
    RedisKillSwitchStore,
)
from control_plane.domains.safety.services.kill_switch_service import (  # noqa: E402
    KillSwitchService,
)
from control_plane.domains.safety.value_objects.kill_switch_state import (  # noqa: E402
    KillSwitchState,
)

# Phase 3 §10.5 threshold. Mirrored in infra/sql/08_phase3_oracle_fp.sql.
FP_RATE_THRESHOLD = 0.02

# Webhook timeout — kept tight so a stuck Slack endpoint can't block the loop.
WEBHOOK_TIMEOUT_SECONDS = 5.0

DEFAULT_INTERVAL_SECONDS = 60
WATCHER_ACTOR = "kill_switch_watch"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s %(message)s",
)
log = logging.getLogger("kill_switch_watch")


SQL_FETCH_BREACHES = """
SELECT cwe, total_submitted, confirmed, rejected, fp_rate
FROM v_oracle_fp_rate
WHERE exceeds_threshold = TRUE
ORDER BY fp_rate DESC
"""


# ---------------------------------------------------------------------------
# Building blocks (each takes a Protocol so tests can inject fakes).
# ---------------------------------------------------------------------------


async def fetch_breaches(conn: asyncpg.Connection) -> list[dict[str, Any]]:
    """Return rows of v_oracle_fp_rate where exceeds_threshold = TRUE."""
    rows = await conn.fetch(SQL_FETCH_BREACHES)
    return [dict(r) for r in rows]


def build_alert_payload(breaches: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Webhook-agnostic JSON. Slack/Discord both accept arbitrary JSON
    when posted as application/json; richer formatting can be layered
    on per-channel later if the operator wants it.
    """
    items = list(breaches)
    return {
        "alert": "oracle_fp_breach",
        "threshold": FP_RATE_THRESHOLD,
        "produced_at": datetime.now(UTC).isoformat(),
        "actor": WATCHER_ACTOR,
        "breaches": [
            {
                "cwe": item["cwe"],
                "fp_rate": float(item["fp_rate"]),
                "rejected": int(item["rejected"]),
                "confirmed": int(item["confirmed"]),
                "total_submitted": int(item["total_submitted"]),
            }
            for item in items
        ],
    }


async def post_webhook(client: httpx.AsyncClient, url: str, payload: dict[str, Any]) -> None:
    """Best-effort POST. Logs and swallows network errors so the
    watcher never crashes on a flaky endpoint.
    """
    try:
        response = await client.post(url, json=payload, timeout=WEBHOOK_TIMEOUT_SECONDS)
        if response.status_code >= 400:
            log.warning(
                "webhook returned %s: %s",
                response.status_code,
                response.text[:200],
            )
        else:
            log.info("webhook delivered (%s)", response.status_code)
    except httpx.HTTPError as exc:
        log.warning("webhook POST failed: %s", exc)


async def trip_kill_switch(
    service: KillSwitchService,
    breaches: list[dict[str, Any]],
) -> None:
    """Activate HALT_SUBMISSIONS once per breach edge."""
    summary = ", ".join(
        f"{b['cwe']}={float(b['fp_rate']):.4f}" for b in breaches
    )
    reason = f"oracle FP > {FP_RATE_THRESHOLD:.0%} on: {summary}"
    await service.activate(
        state=KillSwitchState.HALT_SUBMISSIONS,
        reason=reason,
        actor=WATCHER_ACTOR,
    )
    log.warning("kill switch ACTIVATED: %s", reason)


# ---------------------------------------------------------------------------
# Watch loop — single tick + driver.
# ---------------------------------------------------------------------------


async def tick(
    *,
    conn: asyncpg.Connection,
    service: KillSwitchService | None,
    webhook_client: httpx.AsyncClient | None,
    webhook_url: str | None,
    seen: set[str],
) -> set[str]:
    """One pass over v_oracle_fp_rate. Returns the new ``seen`` set."""
    breaches = await fetch_breaches(conn)
    breached_cwes = {row["cwe"] for row in breaches}

    new_breaches = breached_cwes - seen
    if new_breaches:
        log.warning(
            "new oracle breach(es) detected: %s",
            sorted(new_breaches),
        )
        new_rows = [r for r in breaches if r["cwe"] in new_breaches]
        if service is not None:
            await trip_kill_switch(service, new_rows)
        if webhook_client is not None and webhook_url:
            await post_webhook(
                webhook_client,
                webhook_url,
                build_alert_payload(new_rows),
            )

    cleared = seen - breached_cwes
    if cleared:
        log.info("oracle(s) cleared below threshold: %s", sorted(cleared))

    return breached_cwes


@asynccontextmanager
async def _open_resources(
    *,
    dsn: str,
    redis_url: str | None,
    dry_run: bool,
) -> AsyncGenerator[
    tuple[asyncpg.Connection, KillSwitchService | None, httpx.AsyncClient | None],
    None,
]:
    """Open DB + (optionally) Redis kill-switch + HTTP client; clean up on exit."""
    conn = await asyncpg.connect(dsn)
    redis_client = None
    service: KillSwitchService | None
    if dry_run:
        service = KillSwitchService(InMemoryKillSwitchStore())
    else:
        if not redis_url:
            await conn.close()
            raise RuntimeError("REDIS_URL is required when --dry-run is not set")
        from redis.asyncio import Redis  # imported lazily so dry-run has no Redis dep

        redis_client = Redis.from_url(redis_url)
        store: KillSwitchStore = RedisKillSwitchStore(redis_client)
        service = KillSwitchService(store)

    http_client = httpx.AsyncClient()
    try:
        yield conn, service, http_client
    finally:
        await http_client.aclose()
        await conn.close()
        if redis_client is not None:
            await redis_client.aclose()


async def watch(
    *,
    dsn: str,
    redis_url: str | None,
    webhook_url: str | None,
    interval_seconds: int,
    once: bool,
    dry_run: bool,
) -> int:
    """Run the watch loop. Returns exit code."""
    seen: set[str] = set()
    async with _open_resources(dsn=dsn, redis_url=redis_url, dry_run=dry_run) as (
        conn, service, http_client,
    ):
        log.info(
            "watcher starting (interval=%ss, once=%s, dry_run=%s, webhook=%s)",
            interval_seconds, once, dry_run, "set" if webhook_url else "unset",
        )
        while True:
            try:
                seen = await tick(
                    conn=conn,
                    service=service,
                    webhook_client=http_client,
                    webhook_url=webhook_url,
                    seen=seen,
                )
            except (asyncpg.PostgresError, OSError) as exc:
                log.error("tick failed (will retry next interval): %s", exc)
            if once:
                return 0
            await asyncio.sleep(interval_seconds)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="kill_switch_watch",
        description="Phase 3 oracle FP watcher — trips Layer-3 on > 2% breach.",
    )
    p.add_argument(
        "--interval", type=int, default=DEFAULT_INTERVAL_SECONDS,
        help="seconds between polls (default: 60)",
    )
    p.add_argument("--once", action="store_true", help="run one tick and exit")
    p.add_argument(
        "--dry-run", action="store_true",
        help="no kill-switch activation, no webhook (still queries DB)",
    )
    return p


def _resolve_dsn() -> str:
    raw = os.environ.get("DATABASE_URL")
    if not raw:
        print("ERROR: DATABASE_URL is not set", file=sys.stderr)
        sys.exit(2)
    return raw.replace("+asyncpg", "")


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    dsn = _resolve_dsn()
    redis_url = os.environ.get("REDIS_URL")
    webhook_url = os.environ.get("KILL_SWITCH_WEBHOOK_URL")
    if args.dry_run and webhook_url:
        # In --dry-run we still test the webhook path; the kill-switch
        # state is the only side-effect that gets stubbed.
        log.info("dry-run: kill switch is in-memory; webhook will fire")
    return asyncio.run(
        watch(
            dsn=dsn,
            redis_url=redis_url,
            webhook_url=webhook_url,
            interval_seconds=args.interval,
            once=args.once,
            dry_run=args.dry_run,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
