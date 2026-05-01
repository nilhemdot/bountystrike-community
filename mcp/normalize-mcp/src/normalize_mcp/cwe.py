"""CWE normalisation — accept varied input shapes; emit canonical ``CWE-NN``.

Recon and oracle outputs use a mix of legacy slugs (``xss-candidate``,
``ssrf``), MITRE numeric IDs (``79``), or full identifiers
(``CWE-79``). Reporter-agent and platform submission APIs require the
canonical ``CWE-<int>`` format. This module is the single normalisation
seam.
"""

from __future__ import annotations

import re

# Slug → MITRE CWE numeric ID. Sourced from the bug-class taxonomy in
# build-plan §5 / research/03-verifier-antislop.md. Extend with care —
# duplicating a slug means a recon emission will silently route to the
# wrong oracle.
SLUG_TO_CWE: dict[str, int] = {
    "xss": 79,
    "xss-candidate": 79,
    "stored-xss": 79,
    "reflected-xss": 79,
    "dom-xss": 79,
    "sqli": 89,
    "sqli-candidate": 89,
    "blind-sqli": 89,
    "ssrf": 918,
    "ssrf-candidate": 918,
    "ssrf-imds": 918,
    "ssrf-imds-candidate": 918,
    "ssti": 94,  # CWE-94 Improper Control of Generation of Code
    "ssti-candidate": 94,
    "rce": 78,  # CWE-78 OS Command Injection — most common RCE class
    "rce-candidate": 78,
    "command-injection": 78,
    "open-redirect": 601,
    "open-redirect-candidate": 601,
    "idor": 639,
    "idor-candidate": 639,
    "auth-bypass": 287,
    "csrf": 352,
    "path-traversal": 22,
    "ldap-injection": 90,
    "xxe": 611,
    # OWASP LLM Top 10 mappings — bug bounty platforms accept the parent
    # weakness IDs even though no direct CWE exists for prompt injection.
    "llm01-prompt-injection": 1426,  # CWE-1426 Improper Validation of Generative AI Output
    "llm02-data-leakage": 200,
    "llm07-system-prompt-leak": 200,
    "llm09-misinformation": 1426,
    "llm06-excessive-agency": 269,
    "llm10-unbounded-consumption": 400,
}

# Cloud findings don't map to a single CWE — most are misconfigurations
# (CWE-16) or insufficient privilege control (CWE-269).
CLOUD_PREFIX_DEFAULT = 16

_CWE_PATTERN = re.compile(r"^CWE-(\d+)$", re.IGNORECASE)


def normalize(value: str) -> str:
    """Return canonical ``CWE-<int>`` for ``value``.

    Accepts:
      - ``"79"``        → ``"CWE-79"``
      - ``"CWE-79"``    → ``"CWE-79"`` (idempotent)
      - ``"cwe-79"``    → ``"CWE-79"``
      - ``"xss"``       → ``"CWE-79"``
      - ``"cloud-iam-privesc"`` → ``"CWE-269"``  (Cloud IAM privesc)
      - ``"cloud-*"`` (any other cloud-prefix) → ``"CWE-16"``

    Raises:
        ValueError: input cannot be normalised.
    """
    raw = (value or "").strip()
    if not raw:
        raise ValueError("empty CWE input")

    # Numeric-only ⇒ wrap.
    if raw.isdigit():
        return f"CWE-{int(raw)}"

    # Already in CWE-N form (any case) ⇒ canonicalise case.
    m = _CWE_PATTERN.match(raw)
    if m:
        return f"CWE-{int(m.group(1))}"

    lowered = raw.lower()
    if lowered in SLUG_TO_CWE:
        return f"CWE-{SLUG_TO_CWE[lowered]}"

    # Cloud sub-class fallback — many cloud findings cluster under
    # CWE-16 (configuration). Specific clusters override below.
    if lowered.startswith("cloud-"):
        if "iam" in lowered or "privesc" in lowered:
            return "CWE-269"
        if "cve" in lowered:
            return "CWE-1395"  # Inclusion of Functionality from Untrusted Source
        return f"CWE-{CLOUD_PREFIX_DEFAULT}"

    raise ValueError(f"unrecognised CWE input {value!r}")


__all__ = ["SLUG_TO_CWE", "normalize"]
