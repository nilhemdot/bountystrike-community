"""SSTI oracle via math-eval across 7 template dialects.

Injects a multiplication expression (a * b) into a query parameter and checks
whether the numeric result appears in the response body.  Tries 7 template
dialects in sequence and stops on the first hit.

Dialects:
  1. Jinja2/Flask  — {{a*b}}
  2. Twig/Pebble   — {{a*b}}
  3. Freemarker    — ${a*b}
  4. Velocity      — ${a*b} / #set($r=a*b)${r}
  5. Smarty        — {a*b}
  6. ERB (Ruby)    — <%= a*b %>
  7. MVEL          — @{a*b}
"""

from __future__ import annotations

import random
import urllib.parse
from typing import Any

import httpx
import structlog

from oracle_mcp.result import OracleResult
from oracle_mcp.security import reject_destructive_payload

log = structlog.get_logger("oracle_mcp.oracles")

# Each entry: (dialect_name, list_of_payloads_to_try)
# The first payload in the list that triggers is reported.
_DIALECTS: list[tuple[str, list[str]]] = []  # populated at module load


def _build_dialects(a: int, b: int) -> list[tuple[str, list[str]]]:
    """Return the 7 dialect entries with the given a and b substituted in."""
    return [
        ("jinja2", [f"{{{{{a}*{b}}}}}"])  ,  # {{a*b}}
        ("twig",   [f"{{{{{a}*{b}}}}}"])  ,  # {{a*b}}
        ("freemarker", [f"${{{a}*{b}}}"])  ,  # ${a*b}
        # Velocity: try both payloads; first match wins for this dialect
        ("velocity", [f"${{{a}*{b}}}", f"#set($r={a}*{b})${{r}}"]),
        ("smarty", [f"{{{a}*{b}}}"])  ,  # {a*b}
        ("erb",    [f"<%= {a}*{b} %>"])  ,  # <%= a*b %>
        ("mvel",   [f"@{{{a}*{b}}}"])  ,  # @{a*b}
    ]


def _inject_param(url: str, param: str, value: str) -> str:
    """Return *url* with *param* set to *value* in the query string."""
    parsed = urllib.parse.urlparse(url)
    qs = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    qs[param] = [value]
    new_query = urllib.parse.urlencode(qs, doseq=True)
    return parsed._replace(query=new_query).geturl()


async def oracle_ssti(
    url: str,
    param: str,
    timeout_seconds: float = 10.0,
) -> OracleResult:
    """Verify SSTI by injecting math-eval expressions across 7 template dialects.

    Args:
        url: Target URL with *param* as a query-string key.
        param: Query-string parameter to inject template payloads into.
        timeout_seconds: Per-request timeout in seconds.

    Returns:
        :class:`~oracle_mcp.result.OracleResult` with verdict
        ``validated`` or ``unreproducible``.
    """
    reject_destructive_payload(url)

    a = random.randint(10, 99)
    b = random.randint(10, 99)
    expected = a * b
    expected_str = str(expected)
    dialects = _build_dialects(a, b)

    log.info(
        "ssti.oracle.start",
        url=url,
        param=param,
        a=a,
        b=b,
        expected=expected,
        dialect_count=len(dialects),
    )

    timed_out_count = 0
    total_tried = 0

    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        for dialect_name, payloads in dialects:
            for payload in payloads:
                injected_url = _inject_param(url, param, payload)
                total_tried += 1
                try:
                    response = await client.get(injected_url)
                    if expected_str in response.text:
                        evidence: dict[str, Any] = {
                            "dialect": dialect_name,
                            "payload": payload,
                            "expected": expected_str,
                            "url": injected_url,
                            "param": param,
                        }
                        log.info(
                            "ssti.oracle.validated",
                            dialect=dialect_name,
                            payload=payload,
                            expected=expected_str,
                        )
                        return OracleResult(
                            verdict="validated",
                            oracle_method="ssti_math_eval",
                            evidence=evidence,
                        )
                except httpx.TimeoutException:
                    timed_out_count += 1
                    log.debug(
                        "ssti.dialect.timeout",
                        dialect=dialect_name,
                        payload=payload,
                    )

    log.info("ssti.oracle.unreproducible", total_tried=total_tried, timed_out=timed_out_count)

    if timed_out_count == total_tried:
        return OracleResult(
            verdict="unreproducible",
            oracle_method="ssti_math_eval",
            evidence={"param": param, "a": a, "b": b, "expected": expected_str},
            reason="all dialects timed out",
        )

    return OracleResult(
        verdict="unreproducible",
        oracle_method="ssti_math_eval",
        evidence={"param": param, "a": a, "b": b, "expected": expected_str},
        reason="no dialect matched",
    )
