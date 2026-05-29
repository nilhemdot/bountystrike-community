# SPDX-License-Identifier: AGPL-3.0-or-later

"""RCE oracle via benign command-output marker detection.

Injects ONLY benign ``echo`` / ``Write-Output`` payloads into a URL parameter
and checks whether the server reflects the generated nonce marker in its
response body.  No destructive commands are ever sent.

Detection confirms that user-supplied input is being executed as a shell
command on the target system.
"""

from __future__ import annotations

import secrets
import urllib.parse
from typing import Any

import httpx
import structlog

from oracle_mcp.result import OracleResult
from oracle_mcp.security import reject_destructive_payload

log = structlog.get_logger("oracle_mcp.oracles")

# Each tuple: (style_name, injection_template)
# The placeholder ``{nonce}`` is replaced at runtime.  The injection string is
# appended to the existing parameter value so we don't accidentally wipe a
# required value the server expects.
_INJECTION_STYLES: tuple[tuple[str, str], ...] = (
    ("unix_semicolon_echo", ";echo {nonce}_rce_marker"),
    ("unix_backtick_echo", "`echo {nonce}_rce_marker`"),
    ("windows_echo", "&echo {nonce}_rce_marker"),
    ("powershell_write_output", "|Write-Output {nonce}_rce_marker"),
)


def _build_injected_url(url: str, param: str, suffix: str) -> str:
    """Return *url* with *suffix* appended to the current value of *param*.

    If *param* is absent from the query string the suffix becomes the entire
    value.
    """
    parsed = urllib.parse.urlparse(url)
    qs = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    existing_values = qs.get(param, [""])
    original_value = existing_values[0]
    qs[param] = [original_value + suffix]
    new_query = urllib.parse.urlencode(qs, doseq=True)
    return parsed._replace(query=new_query).geturl()


async def oracle_rce(
    url: str,
    param: str,
    timeout_seconds: float = 10.0,
) -> OracleResult:
    """Detect RCE by injecting benign marker-echo payloads and checking output.

    Four injection styles are tried in order (Unix semicolon, Unix backtick,
    Windows ``&echo``, PowerShell ``Write-Output``).  The oracle stops and
    returns ``validated`` as soon as one style causes the server to echo back
    the generated nonce marker.

    Args:
        url: Target URL.  The *param* query-string key is used for injection.
        param: Query-string parameter to inject into.
        timeout_seconds: Per-request HTTP timeout in seconds.

    Returns:
        :class:`~oracle_mcp.result.OracleResult` with verdict:

        - ``validated`` — server reflected the nonce marker (RCE confirmed).
        - ``unreproducible`` — all four styles were attempted; no reflection found.
    """
    reject_destructive_payload(url)

    nonce = secrets.token_hex(8)
    marker = f"{nonce}_rce_marker"

    log.info(
        "rce.oracle.start",
        url=url,
        param=param,
        nonce=nonce,
    )

    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        for style_name, injection_template in _INJECTION_STYLES:
            injection_string = injection_template.format(nonce=nonce)
            injected_url = _build_injected_url(url, param, injection_string)

            log.debug(
                "rce.attempt",
                style=style_name,
                injected_url=injected_url,
            )

            try:
                response = await client.get(injected_url)
            except httpx.TimeoutException:
                log.debug("rce.attempt.timeout", style=style_name)
                continue

            if marker in response.text:
                evidence: dict[str, Any] = {
                    "injection_style": style_name,
                    "nonce": nonce,
                    "param": param,
                    "url": url,
                }
                log.info(
                    "rce.oracle.done",
                    verdict="validated",
                    style=style_name,
                )
                return OracleResult(
                    verdict="validated",
                    oracle_method="rce_echo_marker",
                    evidence=evidence,
                )

            log.debug("rce.attempt.no_marker", style=style_name)

    log.info("rce.oracle.done", verdict="unreproducible")
    return OracleResult(
        verdict="unreproducible",
        oracle_method="rce_echo_marker",
        evidence={"url": url, "param": param, "nonce": nonce},
        reason="none of the 4 injection styles reflected the nonce marker",
    )
