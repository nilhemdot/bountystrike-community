# SPDX-License-Identifier: AGPL-3.0-or-later

"""XSS oracle via Playwright DOM mutation.

Injects a self-executing XSS probe and detects JS execution by reading a
marker variable from the browser's global scope.  Three attempts are run;
the verdict is derived from the combination of successes and failures:

- All 3 succeed → ``validated``
- All 3 timeout  → ``unreproducible``
- Mixed result   → ``flaky``
"""

from __future__ import annotations

import urllib.parse
from typing import Any

import structlog
from playwright.async_api import TimeoutError as PlaywrightTimeout
from playwright.async_api import async_playwright

from oracle_mcp.result import OracleResult, Verdict
from oracle_mcp.security import reject_destructive_payload

log = structlog.get_logger("oracle_mcp.oracles")

_PROBE_PAYLOAD = '<img src=x onerror="window.__bs5xss=1">'
_MARKER_EXPR = "() => window.__bs5xss ?? 0"
_ATTEMPTS = 3


def _inject_param(url: str, param: str, value: str) -> str:
    """Return *url* with *param* replaced by *value* in the query string."""
    parsed = urllib.parse.urlparse(url)
    qs = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    qs[param] = [value]
    new_query = urllib.parse.urlencode(qs, doseq=True)
    return parsed._replace(query=new_query).geturl()


async def oracle_xss(
    url: str,
    param: str,
    timeout_ms: int = 5000,
) -> OracleResult:
    """Verify XSS by injecting a DOM-mutation probe and checking execution.

    Args:
        url: Target URL (must already contain *param* as a query parameter).
        param: Query-string parameter to inject into.
        timeout_ms: Per-navigation timeout in milliseconds.

    Returns:
        :class:`~oracle_mcp.result.OracleResult` with verdict
        ``validated``, ``unreproducible``, or ``flaky``.
    """
    reject_destructive_payload(url)

    injected_url = _inject_param(url, param, _PROBE_PAYLOAD)
    successes: list[bool] = []

    log.info(
        "xss.oracle.start",
        url=url,
        param=param,
        injected_url=injected_url,
        attempts=_ATTEMPTS,
    )

    async with async_playwright() as p:
        for attempt in range(_ATTEMPTS):
            browser = await p.chromium.launch(headless=True)
            try:
                page = await browser.new_page()
                try:
                    await page.goto(injected_url, timeout=timeout_ms)
                    marker: Any = await page.evaluate(_MARKER_EXPR)
                    triggered = bool(marker)
                    successes.append(triggered)
                    log.debug(
                        "xss.attempt",
                        attempt=attempt + 1,
                        triggered=triggered,
                    )
                except PlaywrightTimeout:
                    successes.append(False)
                    log.debug("xss.attempt.timeout", attempt=attempt + 1)
                finally:
                    await page.close()
            finally:
                await browser.close()

    success_count = sum(successes)
    timeout_count = _ATTEMPTS - success_count  # noqa: F841 — used for logic below

    evidence: dict[str, Any] = {
        "param": param,
        "injected_url": injected_url,
        "attempts": _ATTEMPTS,
        "successes": success_count,
    }

    verdict: Verdict
    reason: str | None = None

    if success_count == _ATTEMPTS:
        verdict = "validated"
    elif success_count == 0:
        verdict = "unreproducible"
        reason = "all attempts timed out or did not trigger XSS"
    else:
        verdict = "flaky"
        reason = f"{success_count}/{_ATTEMPTS} attempts triggered XSS"

    log.info("xss.oracle.done", verdict=verdict, success_count=success_count)

    return OracleResult(
        verdict=verdict,
        oracle_method="xss_dom_mutation",
        evidence=evidence,
        reason=reason,
    )
