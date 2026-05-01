"""FastMCP server for politeness-mcp.

Exposes three MCP tools:
  - acquire(host, rps_limit?)         — block for a token; returns wait stats
  - report_response(host, status, latency_ms?)
                                      — feedback for adaptive backoff
  - status(host)                      — debug query of bucket state

Transport: stdio (default FastMCP transport).
Entry point: ``politeness-mcp`` CLI script (see pyproject.toml).

Default per-host RPS = 5 (build-plan §2.3.1). Override via JWT-derived
``rps_limit`` argument on each ``acquire`` call.
"""

from __future__ import annotations

import os

from mcp.server.fastmcp import FastMCP

from politeness_mcp.bucket import TokenBucketLimiter

mcp = FastMCP("politeness-mcp")

_DEFAULT_RPS: float = float(os.environ.get("POLITENESS_DEFAULT_RPS", "5"))
_limiter: TokenBucketLimiter = TokenBucketLimiter(default_rps=_DEFAULT_RPS)


def _get_limiter() -> TokenBucketLimiter:
    return _limiter


@mcp.tool()
async def acquire(host: str, rps_limit: float | None = None) -> dict:
    """Acquire one outbound-request token for ``host``.

    Blocks (cooperatively) until a token is available or the projected
    wait exceeds the in-process ceiling. Caller MUST call this before
    every outbound request to a target host.

    Args:
        host: Target hostname (lowercase, no port). Caller is responsible
            for normalising — the limiter does not strip ports.
        rps_limit: Optional per-host RPS override from the scope JWT's
            ``rate_limits.relaxed_hosts`` map. None → use default 5 rps.

    Returns:
        ``{host, waited_s, would_wait_s, granted}``. When ``granted``
        is False the caller should defer the request — the bucket is
        oversubscribed and the wait would exceed ``MAX_WAIT_SECONDS``.
    """
    return await _get_limiter().acquire(host, rps_limit)


@mcp.tool()
async def report_response(
    host: str,
    status_code: int,
    latency_ms: float | None = None,
) -> dict:
    """Feed an observed response back to the politeness gate.

    Halves the refill rate for ``BACKOFF_SECONDS`` on 429 / 503
    (build-plan §2.3.1). Other 5xx codes increment ``error_count`` but
    do not throttle. 2xx / 3xx reset the consecutive-429 counter.

    Args:
        host: Same hostname passed to ``acquire``.
        status_code: HTTP status from the target.
        latency_ms: Optional response latency (telemetry only; not used
            for backoff decisions today).

    Returns:
        ``{host, tracked, consecutive_429, backoff_active}``. ``tracked``
        is False when the host has no bucket (caller skipped acquire) —
        treated as a no-op.
    """
    return await _get_limiter().report(host, status_code, latency_ms)


@mcp.tool()
async def status(host: str) -> dict:
    """Inspect the current bucket state for ``host``.

    Read-only. Useful for the orchestrator's politeness dashboard and
    for tests. Refills tokens as a side effect of reading (so callers
    see the current available count, not a stale snapshot).
    """
    return await _get_limiter().status(host)


def main() -> None:
    """Run the politeness-mcp FastMCP server (stdio transport)."""
    mcp.run()


if __name__ == "__main__":
    main()
