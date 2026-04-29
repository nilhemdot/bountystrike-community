"""SSRF oracle via Interactsh OAST (Out-of-band Application Security Testing).

Registers a unique callback token, injects the callback URL into the target
request, waits for an out-of-band interaction, and reports whether the server
made a network request to our controlled domain.
"""

from __future__ import annotations

import urllib.parse
from typing import Any

import httpx
import structlog

from oracle_mcp.oast import get_default_client
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


async def oracle_ssrf(
    url: str,
    param: str,
    poll_timeout_seconds: float = 15.0,
) -> OracleResult:
    """Verify SSRF by injecting an Interactsh callback URL and waiting for a hit.

    Args:
        url: Target URL whose *param* will receive the callback URL.
        param: Query-string parameter to inject the OAST callback into.
        poll_timeout_seconds: Seconds to wait for an out-of-band interaction.

    Returns:
        :class:`~oracle_mcp.result.OracleResult` with verdict
        ``validated`` or ``unreproducible``.
    """
    reject_destructive_payload(url)

    client = get_default_client()

    log.info("ssrf.oracle.start", url=url, param=param)

    async with client:
        token = await client.register_token()
        try:
            callback_url = token.callback_url
            injected_url = _inject_param(url, param, callback_url)

            log.debug(
                "ssrf.injecting",
                callback_url=callback_url,
                injected_url=injected_url,
            )

            async with httpx.AsyncClient(timeout=30.0) as http:
                try:
                    await http.get(injected_url)
                except httpx.HTTPError as exc:
                    log.debug("ssrf.trigger_request.error", error=str(exc))

            interactions = await client.poll_interactions(
                token,
                timeout=poll_timeout_seconds,
            )

            if interactions:
                first = interactions[0]
                evidence: dict[str, Any] = {
                    "callback_url": callback_url,
                    "interaction_count": len(interactions),
                    "interaction_type": first.interaction_type,
                    "source_ip": first.source_ip,
                    "timestamp": first.timestamp,
                    "param": param,
                }
                log.info(
                    "ssrf.oracle.validated",
                    interaction_count=len(interactions),
                )
                return OracleResult(
                    verdict="validated",
                    oracle_method="ssrf_oast_interactsh",
                    evidence=evidence,
                )

            log.info("ssrf.oracle.unreproducible")
            return OracleResult(
                verdict="unreproducible",
                oracle_method="ssrf_oast_interactsh",
                evidence={"callback_url": callback_url, "param": param},
                reason="no out-of-band interaction received within timeout",
            )
        finally:
            await client.deregister(token)
