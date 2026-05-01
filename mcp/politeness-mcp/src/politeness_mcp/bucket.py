"""Per-host token bucket with adaptive backoff.

Token bucket semantics:
  capacity      — max burst (= ``rps_limit``; one second's worth of tokens).
  refill_rate   — tokens added per second (= ``rps_limit``).
  tokens        — current available; consumed by acquire().

Adaptive backoff (build-plan §2.3.1):
  - 429 / 503 from the target halves ``refill_rate`` for ``BACKOFF_SECONDS``.
  - 2xx / 3xx restores the configured rate after the cooldown elapses.

Time source is injected so tests run deterministically without sleeping.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Callable

# Backoff window after a 429/503 response.
BACKOFF_SECONDS = 60.0

# Wait cap per acquire — never block longer than this; if the wait would
# exceed it, the caller is told ``would_wait_s`` and decides what to do.
MAX_WAIT_SECONDS = 30.0

# Hard ceiling for any per-host rps_limit. The scope JWT can override the
# default 5 rps but never above this — defence in depth against a
# malformed JWT setting rps=10000.
MAX_RPS_CEILING = 50.0


@dataclass
class HostBucket:
    """Mutable per-host bucket state."""

    rps_limit: float
    tokens: float
    last_refill: float
    backoff_until: float = 0.0
    consecutive_429: int = 0
    request_count: int = 0
    error_count: int = 0
    last_response_at: float = 0.0


class TokenBucketLimiter:
    """In-memory politeness gate. Single-process scope.

    For multi-process / SaaS deployments, swap this with a Redis-backed
    Lua-script bucket; the public API (``acquire``, ``report``,
    ``status``) is preserved.
    """

    def __init__(
        self,
        default_rps: float = 5.0,
        time_source: Callable[[], float] | None = None,
        sleep_fn: Callable[[float], "asyncio.Future"] | None = None,
    ) -> None:
        if default_rps <= 0 or default_rps > MAX_RPS_CEILING:
            raise ValueError(f"default_rps out of range: {default_rps}")
        import time as _time

        self._default_rps = default_rps
        self._now: Callable[[], float] = time_source or _time.monotonic
        self._sleep = sleep_fn or asyncio.sleep
        self._buckets: dict[str, HostBucket] = {}
        self._lock = asyncio.Lock()

    def _refill(self, bucket: HostBucket) -> None:
        now = self._now()
        elapsed = max(0.0, now - bucket.last_refill)
        rate = self._effective_rate(bucket, now)
        bucket.tokens = min(
            bucket.rps_limit,
            bucket.tokens + elapsed * rate,
        )
        bucket.last_refill = now

    def _effective_rate(self, bucket: HostBucket, now: float) -> float:
        if now < bucket.backoff_until:
            return max(0.5, bucket.rps_limit * 0.5)
        return bucket.rps_limit

    def _get_or_create(self, host: str, rps_limit: float | None) -> HostBucket:
        bucket = self._buckets.get(host)
        if bucket is None:
            rate = float(rps_limit) if rps_limit else self._default_rps
            if rate <= 0 or rate > MAX_RPS_CEILING:
                rate = self._default_rps
            bucket = HostBucket(
                rps_limit=rate,
                tokens=rate,
                last_refill=self._now(),
            )
            self._buckets[host] = bucket
        elif rps_limit is not None and abs(bucket.rps_limit - rps_limit) > 1e-6:
            # JWT change for this host — refill state, swap rate.
            self._refill(bucket)
            bucket.rps_limit = float(min(rps_limit, MAX_RPS_CEILING))
        return bucket

    async def acquire(
        self,
        host: str,
        rps_limit: float | None = None,
    ) -> dict:
        """Block until a token is available; return wait stats.

        Returns: ``{host, waited_s, would_wait_s, granted}``.

        ``granted`` is True iff the token was successfully consumed; it is
        False when the projected wait exceeds ``MAX_WAIT_SECONDS`` — the
        caller decides whether to retry or skip.
        """
        async with self._lock:
            bucket = self._get_or_create(host, rps_limit)
            self._refill(bucket)
            if bucket.tokens >= 1.0:
                bucket.tokens -= 1.0
                bucket.request_count += 1
                return {
                    "host": host,
                    "waited_s": 0.0,
                    "would_wait_s": 0.0,
                    "granted": True,
                }
            rate = self._effective_rate(bucket, self._now())
            need = 1.0 - bucket.tokens
            would_wait = need / rate if rate > 0 else MAX_WAIT_SECONDS + 1
            if would_wait > MAX_WAIT_SECONDS:
                return {
                    "host": host,
                    "waited_s": 0.0,
                    "would_wait_s": would_wait,
                    "granted": False,
                }
        # Sleep outside the lock so other hosts proceed concurrently.
        await self._sleep(would_wait)
        async with self._lock:
            bucket = self._get_or_create(host, rps_limit)
            self._refill(bucket)
            bucket.tokens = max(0.0, bucket.tokens - 1.0)
            bucket.request_count += 1
            return {
                "host": host,
                "waited_s": would_wait,
                "would_wait_s": would_wait,
                "granted": True,
            }

    async def report(
        self,
        host: str,
        status_code: int,
        latency_ms: float | None = None,
    ) -> dict:
        """Adapt the bucket based on the observed response.

        ``status_code`` 429 / 503 → set ``backoff_until`` to ``now +
        BACKOFF_SECONDS`` and bump consecutive_429.
        Other 5xx → bump error_count but no backoff (transient infra).
        2xx / 3xx → reset consecutive_429.
        """
        async with self._lock:
            bucket = self._buckets.get(host)
            if bucket is None:
                return {"host": host, "tracked": False}
            now = self._now()
            bucket.last_response_at = now
            if status_code in (429, 503):
                bucket.consecutive_429 += 1
                bucket.backoff_until = now + BACKOFF_SECONDS
                bucket.error_count += 1
            elif 500 <= status_code < 600:
                bucket.error_count += 1
            else:
                bucket.consecutive_429 = 0
            return {
                "host": host,
                "tracked": True,
                "consecutive_429": bucket.consecutive_429,
                "backoff_active": now < bucket.backoff_until,
            }

    async def status(self, host: str) -> dict:
        async with self._lock:
            bucket = self._buckets.get(host)
            if bucket is None:
                return {"host": host, "known": False}
            self._refill(bucket)
            now = self._now()
            return {
                "host": host,
                "known": True,
                "rps_limit": bucket.rps_limit,
                "tokens_available": bucket.tokens,
                "backoff_active": now < bucket.backoff_until,
                "backoff_remaining_s": max(0.0, bucket.backoff_until - now),
                "consecutive_429": bucket.consecutive_429,
                "request_count": bucket.request_count,
                "error_count": bucket.error_count,
            }


__all__ = [
    "BACKOFF_SECONDS",
    "MAX_RPS_CEILING",
    "MAX_WAIT_SECONDS",
    "HostBucket",
    "TokenBucketLimiter",
]
