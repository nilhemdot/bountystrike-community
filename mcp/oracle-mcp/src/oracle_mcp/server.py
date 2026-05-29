# SPDX-License-Identifier: AGPL-3.0-or-later

"""FastMCP server entry point for oracle-mcp.

Exposes eight MCP tools for the BountyStrike v5 validator-agent:
  - verify_xss           — DOM mutation probe via Playwright
  - verify_ssrf          — OAST callback via Interactsh
  - verify_sqli          — Timing side-channel via Welch's t-test
  - verify_ssti          — Math-eval probe across 7 template dialects
  - verify_open_redirect — HTTP redirect-follow to detect open redirects
  - verify_ssrf_imds     — SSRF via cloud metadata endpoint injection
  - verify_idor          — Cross-account resource access matrix (Jaccard similarity)
  - verify_rce           — Benign nonce-echo RCE detection (4 injection styles)

Transport: stdio (default FastMCP transport).
Entry point: ``oracle-mcp`` CLI script (see pyproject.toml).
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from oracle_mcp.oracles import (
    oracle_idor,
    oracle_open_redirect,
    oracle_rce,
    oracle_sqli,
    oracle_ssrf,
    oracle_ssrf_imds,
    oracle_ssti,
    oracle_xss,
)
from oracle_mcp.oracles.idor import SessionCredentials
from oracle_mcp.security import reject_destructive_payload

mcp = FastMCP("oracle-mcp")


@mcp.tool()
async def verify_xss(
    url: str,
    param: str,
    timeout_ms: int = 5000,
) -> dict:
    """Verify an XSS vulnerability via Playwright DOM mutation probing.

    Injects a self-executing XSS payload into *param* and checks whether
    JavaScript executed in a headless Chromium browser.  Three attempts are
    made; the verdict reflects the overall reliability of the finding.

    Args:
        url: Target URL that reflects *param* in the HTML response.
        param: Query-string parameter to inject.
        timeout_ms: Per-navigation timeout in milliseconds (default 5000).

    Returns:
        Serialised :class:`~oracle_mcp.result.OracleResult` dict with keys
        ``verdict``, ``oracle_method``, ``evidence``, and ``reason``.
    """
    reject_destructive_payload(url)
    result = await oracle_xss(url=url, param=param, timeout_ms=timeout_ms)
    return result.model_dump()


@mcp.tool()
async def verify_ssrf(
    url: str,
    param: str,
    poll_timeout_seconds: float = 15.0,
) -> dict:
    """Verify an SSRF vulnerability via Interactsh out-of-band callback.

    Injects a unique Interactsh callback URL into *param* and waits for the
    target server to make an out-of-band HTTP or DNS request to the callback
    host.

    Args:
        url: Target URL whose *param* is sent to the server as a URL.
        param: Query-string parameter to inject the callback URL into.
        poll_timeout_seconds: Seconds to wait for an OOB interaction (default 15).

    Returns:
        Serialised :class:`~oracle_mcp.result.OracleResult` dict.
    """
    reject_destructive_payload(url)
    result = await oracle_ssrf(
        url=url,
        param=param,
        poll_timeout_seconds=poll_timeout_seconds,
    )
    return result.model_dump()


@mcp.tool()
async def verify_sqli(
    url: str,
    param: str,
    baseline_n: int = 7,
    inject_n: int = 7,
    delay_seconds: float = 5.0,
    alpha: float = 0.01,
) -> dict:
    """Verify a SQL injection vulnerability via timing side-channel analysis.

    Compares response times for the original *param* (baseline) vs. a
    time-delay SQL payload (inject) using Welch's independent-samples t-test.
    Returns ``validated`` only when the difference is statistically significant
    and the mean injected delay exceeds half the requested sleep duration.

    Args:
        url: Target URL with *param* as a query-string key.
        param: Query-string parameter to inject the SQL payload into.
        baseline_n: Number of baseline (unmodified) requests (default 7).
        inject_n: Number of injected (time-delay) requests (default 7).
        delay_seconds: Seconds the SQL ``SLEEP`` should pause (default 5.0).
        alpha: Statistical significance threshold (default 0.01).

    Returns:
        Serialised :class:`~oracle_mcp.result.OracleResult` dict.
    """
    reject_destructive_payload(url)
    result = await oracle_sqli(
        url=url,
        param=param,
        baseline_n=baseline_n,
        inject_n=inject_n,
        delay_seconds=delay_seconds,
        alpha=alpha,
    )
    return result.model_dump()


@mcp.tool()
async def verify_ssti(
    url: str,
    param: str,
    timeout_seconds: float = 10.0,
) -> dict:
    """Verify a Server-Side Template Injection vulnerability via math-eval probing.

    Injects multiplication expressions into *param* across 7 template engine
    dialects (Jinja2, Twig, Freemarker, Velocity, Smarty, ERB, MVEL) and
    checks whether the numeric result appears in the response body.

    Args:
        url: Target URL with *param* as a query-string key.
        param: Query-string parameter to inject template payloads into.
        timeout_seconds: Per-request timeout in seconds (default 10.0).

    Returns:
        Serialised :class:`~oracle_mcp.result.OracleResult` dict with keys
        ``verdict``, ``oracle_method``, ``evidence``, and ``reason``.
    """
    reject_destructive_payload(url)
    result = await oracle_ssti(url=url, param=param, timeout_seconds=timeout_seconds)
    return result.model_dump()


@mcp.tool()
async def verify_open_redirect(
    url: str,
    param: str,
    target: str = "https://example.com",
    timeout_seconds: float = 10.0,
) -> dict:
    """Verify an open redirect vulnerability by following HTTP redirects.

    Injects *target* as the value of *param* and checks if the final URL
    (after all redirects) resolves to the same host as *target*.

    Args:
        url: Target URL with *param* as a query-string key.
        param: Query-string parameter to inject the redirect target into.
        target: The URL to redirect to (default ``https://example.com``).
        timeout_seconds: Request timeout in seconds (default 10.0).

    Returns:
        Serialised :class:`~oracle_mcp.result.OracleResult` dict.
    """
    reject_destructive_payload(url)
    result = await oracle_open_redirect(
        url=url,
        param=param,
        target=target,
        timeout_seconds=timeout_seconds,
    )
    return result.model_dump()


@mcp.tool()
async def verify_ssrf_imds(
    url: str,
    param: str,
    timeout_seconds: float = 10.0,
) -> dict:
    """Verify SSRF to cloud Instance Metadata Service (IMDS) via endpoint injection.

    Injects cloud metadata endpoints (AWS, GCP, Azure) into *param* and checks
    whether the response body contains provider-specific marker strings.

    Args:
        url: Target URL with *param* as the SSRF injection point.
        param: Query-string parameter to inject the IMDS URL into.
        timeout_seconds: Per-request timeout in seconds (default 10.0).

    Returns:
        Serialised :class:`~oracle_mcp.result.OracleResult` dict.
    """
    reject_destructive_payload(url)
    result = await oracle_ssrf_imds(
        url=url,
        param=param,
        timeout_seconds=timeout_seconds,
    )
    return result.model_dump()


@mcp.tool()
async def verify_idor(
    resource_url: str,
    owner_headers: dict,
    owner_cookies: dict,
    accessor_headers: dict,
    accessor_cookies: dict,
    expected_owner_status: int = 200,
    timeout_seconds: float = 10.0,
) -> dict:
    """Verify an IDOR vulnerability via cross-account resource access matrix.

    Checks whether account B (accessor) can access a resource belonging to
    account A (owner) using Jaccard word-set similarity to detect shared content.

    Args:
        resource_url: URL of the resource owned by account A.
        owner_headers: HTTP headers for account A's session.
        owner_cookies: Cookies for account A's session.
        accessor_headers: HTTP headers for account B's session.
        accessor_cookies: Cookies for account B's session.
        expected_owner_status: Expected HTTP status for the owner (default 200).
        timeout_seconds: Per-request timeout in seconds (default 10.0).

    Returns:
        Serialised :class:`~oracle_mcp.result.OracleResult` dict.
    """
    reject_destructive_payload(resource_url)
    owner = SessionCredentials(headers=owner_headers, cookies=owner_cookies)
    accessor = SessionCredentials(headers=accessor_headers, cookies=accessor_cookies)
    result = await oracle_idor(
        resource_url=resource_url,
        owner_session=owner,
        accessor_session=accessor,
        expected_owner_status=expected_owner_status,
        timeout_seconds=timeout_seconds,
    )
    return result.model_dump()


@mcp.tool()
async def verify_rce(
    url: str,
    param: str,
    timeout_seconds: float = 10.0,
) -> dict:
    """Verify RCE via benign nonce-echo detection across 4 injection styles.

    Injects a unique nonce-tagged ``echo`` command (Unix semicolon, backtick,
    Windows ``&echo``, PowerShell ``Write-Output``) and checks whether the
    server reflects the nonce in its response body.

    Args:
        url: Target URL with *param* as the injection point.
        param: Query-string parameter to append injection payloads to.
        timeout_seconds: Per-request timeout in seconds (default 10.0).

    Returns:
        Serialised :class:`~oracle_mcp.result.OracleResult` dict.
    """
    reject_destructive_payload(url)
    result = await oracle_rce(url=url, param=param, timeout_seconds=timeout_seconds)
    return result.model_dump()


def main() -> None:
    """Run the oracle-mcp FastMCP server (stdio transport)."""
    mcp.run()


if __name__ == "__main__":
    main()
