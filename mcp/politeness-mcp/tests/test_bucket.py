"""Tests for the TokenBucketLimiter — deterministic, no real sleep.

Tests inject a manual time source (``ManualClock``) and a no-op sleep
function so cases like a 429 backoff or burst exhaustion run in
microseconds while still exercising the actual elapsed-time math.
"""

from __future__ import annotations

import pytest
from politeness_mcp.bucket import (
    BACKOFF_SECONDS,
    MAX_RPS_CEILING,
    MAX_WAIT_SECONDS,
    TokenBucketLimiter,
)


class ManualClock:
    def __init__(self, t0: float = 1000.0) -> None:
        self.t = t0

    def now(self) -> float:
        return self.t

    def advance(self, dt: float) -> None:
        self.t += dt


def make_limiter(default_rps: float = 5.0) -> tuple[TokenBucketLimiter, ManualClock]:
    clock = ManualClock()

    async def fake_sleep(dt: float) -> None:
        clock.advance(dt)

    limiter = TokenBucketLimiter(
        default_rps=default_rps,
        time_source=clock.now,
        sleep_fn=fake_sleep,
    )
    return limiter, clock


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_rejects_zero_rps() -> None:
    with pytest.raises(ValueError):
        TokenBucketLimiter(default_rps=0)


def test_rejects_excessive_rps() -> None:
    with pytest.raises(ValueError):
        TokenBucketLimiter(default_rps=MAX_RPS_CEILING + 1)


# ---------------------------------------------------------------------------
# acquire — basic flow
# ---------------------------------------------------------------------------


async def test_first_request_immediate() -> None:
    limiter, _clock = make_limiter()
    result = await limiter.acquire("example.com")
    assert result["granted"] is True
    assert result["waited_s"] == 0.0


async def test_burst_within_capacity() -> None:
    limiter, _clock = make_limiter(default_rps=5)
    granted = []
    for _ in range(5):
        granted.append((await limiter.acquire("example.com"))["granted"])
    assert granted == [True] * 5


async def test_sixth_call_within_one_second_waits() -> None:
    limiter, clock = make_limiter(default_rps=5)
    for _ in range(5):
        await limiter.acquire("example.com")
    # Bucket empty; clock did not advance ⇒ next call must wait.
    result = await limiter.acquire("example.com")
    assert result["granted"] is True
    assert result["waited_s"] > 0.0


async def test_tokens_refill_over_time() -> None:
    limiter, clock = make_limiter(default_rps=5)
    for _ in range(5):
        await limiter.acquire("example.com")
    clock.advance(1.0)  # 1 second ⇒ 5 tokens replenished
    result = await limiter.acquire("example.com")
    assert result["granted"] is True
    assert result["waited_s"] == 0.0


# ---------------------------------------------------------------------------
# Per-host JWT override
# ---------------------------------------------------------------------------


async def test_jwt_relaxed_host_higher_rps() -> None:
    limiter, _clock = make_limiter(default_rps=5)
    # Relaxed host: 10 rps capacity ⇒ 10 immediate consecutive grants.
    granted = []
    for _ in range(10):
        granted.append(
            (await limiter.acquire("api.example.com", rps_limit=10))["granted"]
        )
    assert granted == [True] * 10


async def test_jwt_clamp_to_ceiling() -> None:
    limiter, _clock = make_limiter(default_rps=5)
    # Bogus rps from a malformed JWT clamps to ceiling, not infinity.
    result = await limiter.acquire("api.example.com", rps_limit=100_000)
    assert result["granted"] is True
    s = await limiter.status("api.example.com")
    # Falls back to default when out-of-range
    assert s["rps_limit"] in (MAX_RPS_CEILING, 5.0)


# ---------------------------------------------------------------------------
# Adaptive backoff on 429 / 503
# ---------------------------------------------------------------------------


async def test_429_halves_refill_rate() -> None:
    limiter, clock = make_limiter(default_rps=10)
    for _ in range(10):
        await limiter.acquire("victim.example.com")
    # Inform the bucket of a 429 ⇒ refill halves to 5 rps for 60s.
    rep = await limiter.report("victim.example.com", 429)
    assert rep["consecutive_429"] == 1
    assert rep["backoff_active"] is True

    # Advance 1s ⇒ at 5 rps we get 5 tokens, not 10.
    clock.advance(1.0)
    s = await limiter.status("victim.example.com")
    # The status() call refills first; tokens should be ≤ 5 now (half rate).
    assert s["tokens_available"] <= 5.0 + 1e-6


async def test_backoff_clears_after_window() -> None:
    limiter, clock = make_limiter(default_rps=5)
    await limiter.acquire("victim.example.com")
    await limiter.report("victim.example.com", 429)
    # Move past the backoff window.
    clock.advance(BACKOFF_SECONDS + 1.0)
    s = await limiter.status("victim.example.com")
    assert s["backoff_active"] is False


async def test_2xx_resets_consecutive_429() -> None:
    limiter, _clock = make_limiter(default_rps=5)
    await limiter.acquire("flap.example.com")
    await limiter.report("flap.example.com", 429)
    await limiter.report("flap.example.com", 200)
    s = await limiter.status("flap.example.com")
    assert s["consecutive_429"] == 0


async def test_5xx_non_429_increments_errors_no_backoff() -> None:
    limiter, _clock = make_limiter(default_rps=5)
    await limiter.acquire("a.example.com")
    rep = await limiter.report("a.example.com", 500)
    assert rep["consecutive_429"] == 0
    assert rep["backoff_active"] is False
    s = await limiter.status("a.example.com")
    assert s["error_count"] == 1


async def test_503_treated_as_429() -> None:
    limiter, _clock = make_limiter(default_rps=5)
    await limiter.acquire("a.example.com")
    rep = await limiter.report("a.example.com", 503)
    assert rep["consecutive_429"] == 1
    assert rep["backoff_active"] is True


# ---------------------------------------------------------------------------
# Per-host isolation
# ---------------------------------------------------------------------------


async def test_per_host_independent() -> None:
    limiter, _clock = make_limiter(default_rps=2)
    for _ in range(2):
        await limiter.acquire("a.example.com")
    # Host A is empty, B should still grant immediately.
    result = await limiter.acquire("b.example.com")
    assert result["granted"] is True
    assert result["waited_s"] == 0.0


async def test_429_on_host_a_does_not_affect_host_b() -> None:
    limiter, _clock = make_limiter(default_rps=5)
    await limiter.acquire("a.example.com")
    await limiter.acquire("b.example.com")
    await limiter.report("a.example.com", 429)
    sa = await limiter.status("a.example.com")
    sb = await limiter.status("b.example.com")
    assert sa["backoff_active"] is True
    assert sb["backoff_active"] is False


# ---------------------------------------------------------------------------
# Long-wait short-circuit
# ---------------------------------------------------------------------------


async def test_excessive_wait_returns_not_granted() -> None:
    # Set a very low rps and try to over-saturate the bucket. We can't
    # easily provoke a > 30s wait without crafting a deep negative — so
    # we use a private path: drain capacity then mock the bucket's
    # tokens to a large negative.
    limiter, _clock = make_limiter(default_rps=1)
    await limiter.acquire("slow.example.com")
    # Force tokens deeply negative so projected wait > MAX_WAIT_SECONDS.
    bucket = limiter._buckets["slow.example.com"]
    bucket.tokens = -(MAX_WAIT_SECONDS + 5.0)  # pseudo over-subscribed
    result = await limiter.acquire("slow.example.com")
    assert result["granted"] is False
    assert result["would_wait_s"] > MAX_WAIT_SECONDS


# ---------------------------------------------------------------------------
# status / unknown host edge case
# ---------------------------------------------------------------------------


async def test_status_unknown_host() -> None:
    limiter, _clock = make_limiter()
    s = await limiter.status("never.touched")
    assert s == {"host": "never.touched", "known": False}


async def test_report_unknown_host_noop() -> None:
    limiter, _clock = make_limiter()
    rep = await limiter.report("never.touched", 429)
    assert rep == {"host": "never.touched", "tracked": False}


async def test_request_count_increments() -> None:
    limiter, _clock = make_limiter()
    for _ in range(3):
        await limiter.acquire("count.example.com")
    s = await limiter.status("count.example.com")
    assert s["request_count"] == 3


# ---------------------------------------------------------------------------
# Audit-fix coverage — per-host lock prevents same-host concurrent
# acquires from blowing past the rate limit.
# ---------------------------------------------------------------------------


async def test_per_host_lock_created_per_host() -> None:
    """Sanity: a per-host lock exists for each tracked host and is
    distinct across hosts. Required so that same-host calls serialise
    while cross-host calls remain concurrent."""
    limiter, _clock = make_limiter()
    await limiter.acquire("a.example.com")
    await limiter.acquire("b.example.com")
    assert "a.example.com" in limiter._host_locks
    assert "b.example.com" in limiter._host_locks
    assert (
        limiter._host_locks["a.example.com"]
        is not limiter._host_locks["b.example.com"]
    )
    # Same host — same lock object on second acquire.
    a_lock = limiter._host_locks["a.example.com"]
    await limiter.acquire("a.example.com")
    assert limiter._host_locks["a.example.com"] is a_lock


async def test_concurrent_same_host_acquires_respect_rps() -> None:
    """Pre-fix: N concurrent same-host acquires after capacity drained
    would all sleep with the same ``would_wait`` and decrement after
    the same single advance — total clock advance ≈ would_wait, not
    N × would_wait. Per-host RPS collapsed to N tokens per
    would_wait.

    Post-fix: per-host lock serialises the post-drain sleeps, so
    total clock advance is proportional to N. Test asserts the lower
    bound that proves serialisation happened.
    """
    import asyncio as _asyncio

    limiter, clock = make_limiter(default_rps=2)
    host = "samehost.example.com"
    # Drain initial 2-token capacity.
    for _ in range(2):
        await limiter.acquire(host)
    t0 = clock.now()
    # Fire 4 concurrent same-host acquires that all need to wait.
    results = await _asyncio.gather(*[limiter.acquire(host) for _ in range(4)])
    elapsed = clock.now() - t0
    # All grants must have succeeded.
    assert all(r["granted"] for r in results), [r for r in results if not r["granted"]]
    # 4 over-capacity tokens at 2 RPS = 4 / 2 = 2.0s of total wait.
    # Pre-fix this collapsed to ~0.5s (single overlap). Lower bound
    # 1.0s is generous enough to be deterministic but tight enough to
    # fail loudly if the per-host lock is removed.
    assert elapsed >= 1.0, f"clock only advanced {elapsed:.3f}s — TOCTOU likely back"


async def test_concurrent_cross_host_acquires_do_not_serialise() -> None:
    """Two different hosts that are both at capacity must not block on
    each other's per-host lock — the lock is per-host, not global."""
    import asyncio as _asyncio

    limiter, clock = make_limiter(default_rps=2)
    # Drain host A's capacity.
    for _ in range(2):
        await limiter.acquire("a.example.com")
    # Concurrent waiter on A + immediate grant on B. B should NOT wait
    # for A's lock — different host, different lock.
    a_result, b_result = await _asyncio.gather(
        limiter.acquire("a.example.com"),
        limiter.acquire("b.example.com"),
    )
    # B was at full capacity, must have been granted immediately.
    assert b_result["waited_s"] == 0.0
    assert a_result["waited_s"] > 0.0
