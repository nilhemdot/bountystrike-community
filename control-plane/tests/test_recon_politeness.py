# SPDX-License-Identifier: AGPL-3.0-or-later

"""Recon politeness gating tests — deterministic, offline, no real sleep.

The prober is exercised against a REAL ``TokenBucketLimiter`` driven by a
manual clock (mirrors mcp/politeness-mcp/tests/test_bucket.py) so the
acquire/report/backoff math is genuinely exercised in microseconds. The
network is stubbed by monkeypatching ``httpx.AsyncClient.get`` — no sockets,
no DB, no docker.
"""

from __future__ import annotations

import httpx
import pytest
from control_plane.domains.recon.probers import HttpxReflectionProber
from control_plane.domains.recon.scope_filter import ScopeFilter
from politeness_mcp.bucket import MAX_RPS_CEILING, MAX_WAIT_SECONDS, TokenBucketLimiter
from structlog.testing import capture_logs


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


class FakeResponse:
    def __init__(self, *, body: str = "", status_code: int = 200) -> None:
        self.text = body
        self.status_code = status_code


def patch_get(
    monkeypatch: pytest.MonkeyPatch,
    *,
    body: str = "",
    status_code: int = 200,
    events: list | None = None,
) -> list[str]:
    """Stub httpx.AsyncClient.get; return the list of URLs it was called with."""
    calls: list[str] = []

    async def fake_get(self: httpx.AsyncClient, url: str, *args: object, **kw: object):
        calls.append(url)
        if events is not None:
            events.append(("get", url))
        return FakeResponse(body=body, status_code=status_code)

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    return calls


# ---------------------------------------------------------------------------
# AC-2 — acquire BEFORE the GET, report AFTER; host parsed from the URL.
# ---------------------------------------------------------------------------


async def test_acquire_before_get_report_after(monkeypatch: pytest.MonkeyPatch) -> None:
    limiter, _clock = make_limiter(default_rps=5)
    events: list = []
    patch_get(monkeypatch, body="SENT", status_code=200, events=events)

    real_acquire = limiter.acquire
    real_report = limiter.report

    async def spy_acquire(host: str, rps_limit: float | None = None):
        events.append(("acquire", host))
        return await real_acquire(host, rps_limit=rps_limit)

    async def spy_report(host: str, status_code: int, latency_ms: float | None = None):
        events.append(("report", host, status_code))
        return await real_report(host, status_code, latency_ms=latency_ms)

    monkeypatch.setattr(limiter, "acquire", spy_acquire)
    monkeypatch.setattr(limiter, "report", spy_report)

    prober = HttpxReflectionProber(limiter=limiter, rps_for_host=lambda _h: 5)
    result = await prober.probe("http://example.com/?x=1", "x", "SENT")

    assert result is True  # sentinel reflected
    assert events == [
        ("acquire", "example.com"),
        ("get", "http://example.com/?x=1"),
        ("report", "example.com", 200),
    ]


# ---------------------------------------------------------------------------
# AC-3 — relaxed_hosts per-host override is honoured.
# ---------------------------------------------------------------------------


async def test_relaxed_hosts_override(monkeypatch: pytest.MonkeyPatch) -> None:
    limiter, _clock = make_limiter(default_rps=5)
    patch_get(monkeypatch, body="", status_code=200)
    scope = ScopeFilter.from_jwt_claims(
        {"rate_limits": {"default_rps": 5, "relaxed_hosts": {"fast.example.com": 20}}}
    )
    prober = HttpxReflectionProber(limiter=limiter, rps_for_host=scope.rps_for_host)

    await prober.probe("http://fast.example.com/?x=1", "x", "SENT")
    await prober.probe("http://slow.example.com/?x=1", "x", "SENT")

    assert (await limiter.status("fast.example.com"))["rps_limit"] == 20
    assert (await limiter.status("slow.example.com"))["rps_limit"] == 5


# ---------------------------------------------------------------------------
# AC-4 — a 429 response puts the host bucket into adaptive backoff.
# ---------------------------------------------------------------------------


async def test_429_triggers_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    limiter, _clock = make_limiter(default_rps=5)
    patch_get(monkeypatch, body="", status_code=429)
    prober = HttpxReflectionProber(limiter=limiter, rps_for_host=lambda _h: 5)

    await prober.probe("http://victim.example.com/?x=1", "x", "SENT")

    status = await limiter.status("victim.example.com")
    assert status["backoff_active"] is True
    assert status["consecutive_429"] == 1


# ---------------------------------------------------------------------------
# AC-5 — wait-cap exhaustion FAILS OPEN: skip GET, KEEP candidate, warn.
# ---------------------------------------------------------------------------


async def test_wait_cap_fails_open(monkeypatch: pytest.MonkeyPatch) -> None:
    limiter, _clock = make_limiter(default_rps=1)
    # Pre-create the host bucket (direct limiter call — no GET issued), then
    # drive its tokens deeply negative so the next acquire projects a wait far
    # beyond MAX_WAIT_SECONDS and returns granted=False.
    await limiter.acquire("slow.example.com")
    limiter._buckets["slow.example.com"].tokens = -(MAX_WAIT_SECONDS + 5.0)

    calls = patch_get(monkeypatch, body="SENT", status_code=200)
    # rps_for_host=None → acquire(host, rps_limit=None) keeps the pre-set bucket.
    prober = HttpxReflectionProber(limiter=limiter, rps_for_host=None)

    with capture_logs() as logs:
        result = await prober.probe("http://slow.example.com/?x=1", "x", "SENT")

    assert result is True  # candidate KEPT — oracle is the real gate
    assert calls == []  # the GET was never issued
    assert any(e["event"] == "recon.politeness.probe_skipped" for e in logs)


# ---------------------------------------------------------------------------
# AC-7 — per-host rps is clamped to MAX_RPS_CEILING before acquire.
# ---------------------------------------------------------------------------


async def test_rps_clamped_to_ceiling(monkeypatch: pytest.MonkeyPatch) -> None:
    limiter, _clock = make_limiter(default_rps=5)
    patch_get(monkeypatch, body="", status_code=200)
    captured: dict[str, float | None] = {}
    real_acquire = limiter.acquire

    async def spy_acquire(host: str, rps_limit: float | None = None):
        captured["rps_limit"] = rps_limit
        return await real_acquire(host, rps_limit=rps_limit)

    monkeypatch.setattr(limiter, "acquire", spy_acquire)
    scope = ScopeFilter.from_jwt_claims(
        {"rate_limits": {"default_rps": 5, "relaxed_hosts": {"x.example.com": 9999}}}
    )
    prober = HttpxReflectionProber(limiter=limiter, rps_for_host=scope.rps_for_host)

    # Must not raise despite the absurd JWT value.
    await prober.probe("http://x.example.com/?x=1", "x", "SENT")

    assert captured["rps_limit"] == MAX_RPS_CEILING
    assert (await limiter.status("x.example.com"))["rps_limit"] == MAX_RPS_CEILING


# ---------------------------------------------------------------------------
# AC-6 — ungated path (limiter=None) is byte-identical to the old behaviour.
# ---------------------------------------------------------------------------


async def test_ungated_path_unchanged_reflected(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = patch_get(monkeypatch, body="hello SENT world", status_code=200)
    prober = HttpxReflectionProber()  # no limiter
    result = await prober.probe("http://example.com/?x=1", "x", "SENT")
    assert result is True
    assert calls == ["http://example.com/?x=1"]  # exactly one GET


async def test_ungated_path_unchanged_unreflected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = patch_get(monkeypatch, body="nothing here", status_code=200)
    prober = HttpxReflectionProber()  # no limiter
    result = await prober.probe("http://example.com/?x=1", "x", "SENT")
    assert result is False
    assert len(calls) == 1
