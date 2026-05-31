# SPDX-License-Identifier: AGPL-3.0-or-later
"""CWE → deterministic-oracle dispatch (plan 01-06).

Maps a finding's ``cwe`` string to one of the five field-validated oracles in
oracle-mcp (XSS / SSRF / SQLi / SSTI / open-redirect). Pure, no I/O: it only
resolves WHICH oracle coroutine to call and HOW to build its kwargs from the
finding's ``url`` / ``parameter``. The verify service runs the coroutine.

Scope (ROADMAP 01-06): only these five. IDOR / RCE / SSRF-IMDS exist in
oracle-mcp but are intentionally NOT dispatched here. Generic-injection CWEs
that are not SSTI-specific — CWE-74 (parent injection) and CWE-94 (code
injection) — resolve to ``None`` so they park in ``validation_pending``
(preserved for the Phase-2 RCE path) rather than being wrongly rejected by an
SSTI probe that cannot validate them (audit 01-06 S3).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from oracle_mcp.oracles import (
    oracle_open_redirect,
    oracle_sqli,
    oracle_ssrf,
    oracle_ssti,
    oracle_xss,
)
from oracle_mcp.result import OracleResult

# Fixed canary target for the open-redirect oracle: a redirect whose Location
# resolves to this host is unambiguous proof. Not a live endpoint — only its
# presence in the redirect chain is checked.
OPEN_REDIRECT_CANARY = "https://br-oracle-canary.example/"

OracleCoro = Callable[..., Awaitable[OracleResult]]
KwargsBuilder = Callable[[str, str], dict[str, str]]


@dataclass(frozen=True)
class OracleSpec:
    """A resolved oracle: its stable id, its coroutine, and a kwargs builder."""

    oracle_id: str
    coro: OracleCoro
    kwargs: KwargsBuilder


def normalise_cwe(cwe: str) -> str:
    """Lowercase and strip a trailing ``-candidate`` recon suffix."""
    token = cwe.strip().lower()
    suffix = "-candidate"
    if token.endswith(suffix):
        token = token[: -len(suffix)]
    return token


def _url_param(url: str, param: str) -> dict[str, str]:
    return {"url": url, "param": param}


def _url_param_target(url: str, param: str) -> dict[str, str]:
    return {"url": url, "param": param, "target": OPEN_REDIRECT_CANARY}


_XSS = OracleSpec("oracle_xss", oracle_xss, _url_param)
_SQLI = OracleSpec("oracle_sqli", oracle_sqli, _url_param)
_SSRF = OracleSpec("oracle_ssrf", oracle_ssrf, _url_param)
_SSTI = OracleSpec("oracle_ssti", oracle_ssti, _url_param)
_OPEN_REDIRECT = OracleSpec("oracle_open_redirect", oracle_open_redirect, _url_param_target)

# Both the CWE-NNN form and the bare type token map to the same oracle.
# NOTE (audit S3): CWE-74 / CWE-94 are deliberately ABSENT — generic injection
# is not SSTI-specific; routing it here would terminally reject a real bug.
_DISPATCH: dict[str, OracleSpec] = {
    "cwe-79": _XSS,
    "xss": _XSS,
    "cwe-89": _SQLI,
    "sqli": _SQLI,
    "cwe-918": _SSRF,
    "ssrf": _SSRF,
    "cwe-1336": _SSTI,
    "ssti": _SSTI,
    "cwe-601": _OPEN_REDIRECT,
    "open-redirect": _OPEN_REDIRECT,
    "open_redirect": _OPEN_REDIRECT,
}


def resolve_oracle(cwe: str | None) -> OracleSpec | None:
    """Return the :class:`OracleSpec` for *cwe*, or ``None`` if unsupported.

    Unsupported includes the deliberately-omitted generic-injection CWEs
    (CWE-74 / CWE-94) and anything outside the five in-scope oracles.
    """
    if not cwe:
        return None
    return _DISPATCH.get(normalise_cwe(cwe))
