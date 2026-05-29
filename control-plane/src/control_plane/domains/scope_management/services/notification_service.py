# SPDX-License-Identifier: AGPL-3.0-or-later

"""Scope-change notification delivery (plan 01-05).

Drains undelivered ``scope_changes`` rows (``notified_at IS NULL``) to a single
generic outbound webhook so a self-hosted operator is alerted when a watched
program's scope, payout, or status changes. Closes the 01-04 gap: diff events
are persisted but otherwise never leave the DB.

Delivery channel
----------------
One env var, ``SCOPE_WEBHOOK_URL`` (read at call time, not import). The payload
carries both ``text`` (Slack incoming-webhook key) and ``content`` (Discord
key) holding the same length-capped summary, plus a structured ``events`` array
that generic JSON consumers parse. Empty/unset/non-http(s) URL -> no-op.

Delivery semantics (AC-8): **at-least-once**, NOT exactly-once. A batch is
marked delivered (``notified_at = now()``) only AFTER its POST returns 2xx; if
the process crashes or the UPDATE/commit fails in the window between the 2xx and
the persisted mark, those rows stay ``notified_at IS NULL`` and are redelivered
on the next run. Duplicate notification is possible; silent loss is not.

Secret handling (M3): ``SCOPE_WEBHOOK_URL`` embeds an auth token (Slack/Discord
sign the path). It is NEVER logged, returned, or raised — only redacted to
``scheme://host`` ever appears in a log line.

Fail-open: a webhook outage or DB error never propagates out of
:func:`deliver_pending` in a way that would crash the scope_poll ingest path
(the call site also guards). On failure the run logs a WARNING with the HTTP
status / error class and the count of events still pending, and returns
``{"notified": 0, "pending": <backlog>}`` so a broken channel is distinguishable
from "no new events".
"""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime
from urllib.parse import urlparse

import httpx
import structlog
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.db import ScopeChange

logger = structlog.get_logger("control_plane.domains.scope_management.notification")

#: Max events per POST. Keeps payloads small and the rendered summary within the
#: strictest provider cap (Discord ``content`` <= 2000 chars).
BATCH_SIZE = 25

#: Discord's ``content`` hard cap. The summary string never exceeds this; full
#: detail always rides ``events[]`` (providers ignore unknown keys).
SUMMARY_MAX_CHARS = 2000

#: Per-run drain ceiling (batches). Bounds wall-clock on a large backlog.
MAX_BATCHES = 50

#: Short backoff between the single retry attempt.
_RETRY_BACKOFF_SECONDS = 0.5


class ScopeNotificationPayload(BaseModel):
    """Outbound webhook body.

    ``text`` (Slack) and ``content`` (Discord) hold the identical summary so a
    single payload satisfies both providers and any generic consumer; ``events``
    carries the full per-change detail.
    """

    text: str
    content: str
    events: list[dict]


def _redact(url: str) -> str:
    """Reduce a secret-bearing webhook URL to ``scheme://host`` for logging."""
    try:
        parts = urlparse(url)
    except ValueError:
        return "<unparseable-url>"
    if parts.scheme and parts.hostname:
        return f"{parts.scheme}://{parts.hostname}"
    return "<redacted>"


def _event_dict(row: ScopeChange) -> dict:
    """Compact per-event projection for the ``events[]`` array."""
    return {
        "event_type": row.event_type,
        "program_handle": row.program_handle,
        "platform": row.platform,
        "asset_identifier": row.asset_identifier,
        "detected_at": row.detected_at.isoformat() if row.detected_at else None,
    }


def _build_summary(events: list[dict]) -> str:
    """Render a human summary bounded by :data:`SUMMARY_MAX_CHARS`.

    Includes as many one-line descriptions as fit; on overflow it appends a
    "first M shown" footer rather than emitting an over-length string. The
    footer's worst-case length is reserved when deciding whether the next line
    fits, so the result is always <= the cap.
    """
    n = len(events)
    out = f"BountyStrike: {n} scope change(s)"
    for shown, e in enumerate(events):
        line = (
            f"\n- [{e['event_type']}] {e['program_handle']} "
            f"({e['platform']}): {e['asset_identifier']}"
        )
        footer = f"\n… {n} changes; first {shown} shown — see events[] / dashboard"
        if len(out) + len(line) + len(footer) > SUMMARY_MAX_CHARS:
            return out + footer
        out += line
    return out


def _is_retryable_status(code: int) -> bool:
    """429 (rate limit) and any 5xx are worth one retry; other 4xx are not."""
    return code == 429 or 500 <= code < 600


async def _post_batch(client: httpx.AsyncClient, url: str, payload: dict) -> tuple[bool, str]:
    """POST once, retry once on transport error or 429/5xx.

    Returns ``(ok, status_or_error)`` where ``status_or_error`` is the HTTP
    status code as a string or the transport-exception class name. The URL is
    never included in the returned token (caller logs redacted).
    """
    last = "unknown"
    for attempt in (1, 2):
        try:
            resp = await client.post(url, json=payload)
        except httpx.HTTPError as exc:
            last = type(exc).__name__
            if attempt == 1:
                await asyncio.sleep(_RETRY_BACKOFF_SECONDS)
                continue
            return False, last
        code = resp.status_code
        if 200 <= code < 300:
            return True, str(code)
        last = str(code)
        if attempt == 1 and _is_retryable_status(code):
            await asyncio.sleep(_RETRY_BACKOFF_SECONDS)
            continue
        return False, last
    return False, last


async def _pending_count(session: AsyncSession) -> int:
    """Count rows still awaiting delivery (``notified_at IS NULL``)."""
    stmt = select(func.count()).select_from(ScopeChange).where(ScopeChange.notified_at.is_(None))
    return int(await session.scalar(stmt) or 0)


async def deliver_pending(
    session: AsyncSession,
    *,
    batch_size: int = BATCH_SIZE,
    max_batches: int = MAX_BATCHES,
) -> dict[str, int]:
    """Drain undelivered scope_changes to the configured webhook.

    Returns ``{"notified": <delivered this run>, "pending": <still NULL>}``.

    No-op (returns 0 delivered) when ``SCOPE_WEBHOOK_URL`` is empty/unset or
    carries a non-http(s) scheme; the backlog count is still surfaced so a
    misconfiguration is observable (AC-3, AC-9).

    Loops up to ``max_batches``: selects the next ``batch_size`` undelivered
    rows ``FOR UPDATE SKIP LOCKED`` (so an overlapping cron + manual run never
    double-send the same rows), POSTs them, and on 2xx marks that batch
    delivered and commits before moving on. A non-2xx (post-retry) or transport
    failure logs a WARNING and stops the run without marking — the rows stay
    redeliverable (AC-2). Fail-open: any unexpected error is caught and the
    backlog is returned rather than raised.
    """
    url = os.environ.get("SCOPE_WEBHOOK_URL", "").strip()
    if not url:
        pending = await _pending_count(session)
        logger.info("scope_notify.unconfigured", pending=pending)
        return {"notified": 0, "pending": pending}

    scheme = urlparse(url).scheme
    if scheme not in ("http", "https"):
        pending = await _pending_count(session)
        logger.warning(
            "scope_notify.invalid_scheme",
            webhook=_redact(url),
            scheme=scheme or "<none>",
            pending=pending,
        )
        return {"notified": 0, "pending": pending}

    notified = 0
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            for _ in range(max_batches):
                stmt = (
                    select(ScopeChange)
                    .where(ScopeChange.notified_at.is_(None))
                    .order_by(ScopeChange.id)
                    .limit(batch_size)
                    .with_for_update(skip_locked=True)
                )
                rows = list((await session.execute(stmt)).scalars().all())
                if not rows:
                    break

                ids = [r.id for r in rows]
                events = [_event_dict(r) for r in rows]
                payload = ScopeNotificationPayload(
                    text=_build_summary(events),
                    content=_build_summary(events),
                    events=events,
                )

                ok, status = await _post_batch(client, url, payload.model_dump())
                if not ok:
                    await session.rollback()  # release the row locks; keep rows NULL
                    pending = await _pending_count(session)
                    logger.warning(
                        "scope_notify.delivery_failed",
                        webhook=_redact(url),
                        status=status,
                        delivered_this_run=notified,
                        pending=pending,
                    )
                    return {"notified": notified, "pending": pending}

                await session.execute(
                    update(ScopeChange)
                    .where(ScopeChange.id.in_(ids))
                    .values(notified_at=datetime.now(UTC))
                )
                await session.commit()
                notified += len(ids)
    except Exception as exc:  # noqa: BLE001 — fail-open: never crash the poll
        await session.rollback()
        pending = await _pending_count(session)
        logger.warning(
            "scope_notify.unexpected_error",
            error=type(exc).__name__,
            delivered_this_run=notified,
            pending=pending,
        )
        return {"notified": notified, "pending": pending}

    pending = await _pending_count(session)
    logger.info("scope_notify.run_complete", notified=notified, pending=pending)
    return {"notified": notified, "pending": pending}


__all__ = [
    "BATCH_SIZE",
    "MAX_BATCHES",
    "SUMMARY_MAX_CHARS",
    "ScopeNotificationPayload",
    "deliver_pending",
]
