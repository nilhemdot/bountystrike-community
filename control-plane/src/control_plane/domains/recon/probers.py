# SPDX-License-Identifier: AGPL-3.0-or-later

"""Reflection-probe concrete implementations.

The ``ReflectionProber`` Protocol lives in :mod:`.service` next to the
service that consumes it. Concrete implementations live here so callers
outside the recon runtime (e.g. ``scripts/filter_unreflected_findings.py``)
can import them without dragging the recon CLI's ``__main__`` import
graph (asyncpg, scope JWT validator, etc.).
"""

from __future__ import annotations

from collections.abc import Callable
from urllib.parse import urlparse

import httpx
import structlog
from politeness_mcp.bucket import MAX_RPS_CEILING, TokenBucketLimiter

DEFAULT_TIMEOUT_SEC = 8.0

log = structlog.get_logger(__name__)


class HttpxReflectionProber:
    """Production reflection prober — single GET, substring match.

    Uses a short timeout so slow targets default to "no reflection" (drop).
    The exploit-agent's WebFetch probe is the catch-net for borderline cases
    flagged by validator; this prober's job is to drop the obvious FPs.

    Optional per-host politeness gating (plan 01-07): pass a
    :class:`TokenBucketLimiter` and an ``rps_for_host`` resolver and every GET
    is gated — ``acquire`` before the request, ``report`` after — with adaptive
    429/503 backoff. The gate is FAIL-OPEN: if a probe is rate-limit-skipped or
    the limiter errors, the candidate is KEPT (``probe`` returns ``True``) and a
    WARNING is logged. The deterministic oracle remains the sole gate that may
    reject a finding; our own throttle must never bury a real bug. With
    ``limiter=None`` (the default) behaviour is byte-identical to the ungated
    single-GET path.
    """

    name = "httpx"

    def __init__(
        self,
        timeout_sec: float = DEFAULT_TIMEOUT_SEC,
        *,
        limiter: TokenBucketLimiter | None = None,
        rps_for_host: Callable[[str], int] | None = None,
    ) -> None:
        self._timeout_sec = timeout_sec
        self._limiter = limiter
        self._rps_for_host = rps_for_host

    async def probe(self, url: str, parameter: str, sentinel: str) -> bool:
        del parameter  # only the URL + sentinel matter for substring check

        if self._limiter is None:
            # Ungated path — byte-identical to the pre-01-07 behaviour (AC-6).
            async with httpx.AsyncClient(
                timeout=self._timeout_sec, follow_redirects=True
            ) as client:
                response = await client.get(url)
                return sentinel in response.text

        # Per-host bucket key: lowercased hostname ONLY. Never fall back to the
        # full url — that would key a fresh bucket per URL and defeat per-host
        # throttling exactly when hostname parsing fails (audit M2).
        host = (urlparse(url).hostname or "_nohost").lower()

        rps: int | None = None
        if self._rps_for_host is not None:
            # Clamp an untrusted relaxed_hosts value to the ceiling so a
            # fat-fingered/malicious JWT cannot crash acquire (audit S1, AC-7).
            rps = int(min(self._rps_for_host(host), MAX_RPS_CEILING))

        try:
            grant = await self._limiter.acquire(host, rps_limit=rps)
        except Exception:  # noqa: BLE001 — limiter must never crash recon (S2)
            log.warning("recon.politeness.acquire_error", host=host, url=url)
            grant = None

        if grant is not None and grant.get("granted") is False:
            # Wait-cap exhausted: SKIP the GET but KEEP the candidate (fail-open,
            # audit M1). The oracle is the real gate — a throttle skip must not
            # read downstream as "unreflected → discard".
            log.warning("recon.politeness.probe_skipped", host=host, url=url)
            return True

        async with httpx.AsyncClient(timeout=self._timeout_sec, follow_redirects=True) as client:
            response = await client.get(url)

        try:
            await self._limiter.report(host, response.status_code)
        except Exception:  # noqa: BLE001 — report failure must not lose the result (S2)
            log.warning("recon.politeness.report_error", host=host, url=url)

        return sentinel in response.text


__all__ = ["DEFAULT_TIMEOUT_SEC", "HttpxReflectionProber"]
