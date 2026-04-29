"""Oracle functions exposed by oracle-mcp.

Phase 1.1a: XSS, SSRF, SQLi.
Phase 1.1b: SSTI, Open Redirect, SSRF→IMDS.
Phase 1.1c: IDOR, RCE.
"""

from __future__ import annotations

from .idor import oracle_idor
from .open_redirect import oracle_open_redirect
from .rce import oracle_rce
from .sqli import oracle_sqli
from .ssrf import oracle_ssrf
from .ssrf_imds import oracle_ssrf_imds
from .ssti import oracle_ssti
from .xss import oracle_xss

__all__ = [
    "oracle_xss",
    "oracle_ssrf",
    "oracle_sqli",
    "oracle_ssti",
    "oracle_open_redirect",
    "oracle_ssrf_imds",
    "oracle_idor",
    "oracle_rce",
]
