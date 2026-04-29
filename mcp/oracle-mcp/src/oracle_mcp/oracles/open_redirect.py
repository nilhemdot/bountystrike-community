"""Open Redirect oracle via HTTP redirect following.

Injects a target URL into a query parameter and follows all redirects.
If the final destination matches the injected target (by hostname comparison),
the vulnerability is confirmed.
"""

from __future__ import annotations

import urllib.parse
from typing import Any

import httpx
import structlog

from oracle_mcp.result import OracleResult
from oracle_mcp.security import reject_destructive_payload

log = structlog.get_logger("oracle_mcp.oracles")


def _inject_param(url: str, param: str, value: str) -> str:
    """Return *url* with *param* set to *value* in the query string."""
    parsed = urllib.parse.urlparse(url)
    qs = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    qs[param] = [value]
    new_query = urllib.parse.urlencode(qs, doseq=True)
    return parsed._replace(query=new_query).geturl()


def _same_origin(url_a: str, url_b: str) -> bool:
    """Return True if both URLs share the same scheme + netloc."""
    a = urllib.parse.urlparse(url_a)
    b = urllib.parse.urlparse(url_b)
    return a.scheme == b.scheme and a.netloc == b.netloc


def _matches_target(final_url: str, target: str) -> bool:
    """Return True when *final_url* resolves to the same host as *target*.

    Compares netloc (host:port) to avoid false positives like
    example.com.attacker.com matching example.com.
    """
    final_parsed = urllib.parse.urlparse(final_url)
    target_parsed = urllib.parse.urlparse(target)
    return final_parsed.netloc == target_parsed.netloc


async def oracle_open_redirect(
    url: str,
    param: str,
    target: str = "https://example.com",
    timeout_seconds: float = 10.0,
) -> OracleResult:
    """Verify an open redirect by injecting a target URL and following redirects.

    Args:
        url: Target URL with *param* as a query-string key.
        param: Query-string parameter to inject the redirect target into.
        target: The URL to redirect to (default ``https://example.com``).
        timeout_seconds: Request timeout in seconds.

    Returns:
        :class:`~oracle_mcp.result.OracleResult` with verdict
        ``validated`` or ``unreproducible``.
    """
    reject_destructive_payload(url)

    injected_url = _inject_param(url, param, target)

    log.info(
        "open_redirect.oracle.start",
        url=url,
        param=param,
        target=target,
        injected_url=injected_url,
    )

    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            max_redirects=10,
            timeout=timeout_seconds,
        ) as client:
            response = await client.get(injected_url)

        # Build redirect chain from response history
        redirect_chain: list[str] = [str(r.url) for r in response.history]
        final_url = str(response.url)
        redirect_chain.append(final_url)

        evidence: dict[str, Any] = {
            "param": param,
            "injected_url": injected_url,
            "final_url": final_url,
            "redirect_chain": redirect_chain,
            "target": target,
        }

        # No redirect occurred at all (no history means direct 2xx)
        if not response.history:
            log.info("open_redirect.oracle.no_redirect", final_url=final_url)
            return OracleResult(
                verdict="unreproducible",
                oracle_method="open_redirect_follow",
                evidence=evidence,
                reason="no redirect",
            )

        # Check if the redirect landed on the target host
        if _matches_target(final_url, target):
            log.info(
                "open_redirect.oracle.validated",
                final_url=final_url,
                target=target,
            )
            return OracleResult(
                verdict="validated",
                oracle_method="open_redirect_follow",
                evidence=evidence,
            )

        # Redirect occurred but stayed on the original origin
        original_origin = urllib.parse.urlparse(url).netloc
        final_origin = urllib.parse.urlparse(final_url).netloc

        if original_origin and original_origin == final_origin:
            reason = "redirect stayed on origin"
        else:
            reason = f"redirect landed on unexpected host: {final_origin}"

        log.info(
            "open_redirect.oracle.unreproducible",
            final_url=final_url,
            reason=reason,
        )
        return OracleResult(
            verdict="unreproducible",
            oracle_method="open_redirect_follow",
            evidence=evidence,
            reason=reason,
        )

    except httpx.TimeoutException:
        log.info("open_redirect.oracle.timeout")
        return OracleResult(
            verdict="unreproducible",
            oracle_method="open_redirect_follow",
            evidence={"param": param, "injected_url": injected_url, "target": target},
            reason="timeout",
        )
