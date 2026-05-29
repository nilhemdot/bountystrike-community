# SPDX-License-Identifier: AGPL-3.0-or-later

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
    # ------------------------------------------------------------------
    # Web — injection / XSS family
    # ------------------------------------------------------------------
    "xss": 79,
    "xss-candidate": 79,
    "stored-xss": 79,
    "reflected-xss": 79,
    "dom-xss": 79,
    "sqli": 89,
    "sqli-candidate": 89,
    "blind-sqli": 89,
    "nosql-injection": 943,
    "ldap-injection": 90,
    "xxe": 611,
    "xxe-via-svg": 611,
    "ssti": 1336,  # CWE-1336: Improper Neutralization of Special Elements
                   # Used in a Template Engine (more precise than the parent
                   # CWE-94 the v0.1 table used).
    "ssti-candidate": 1336,
    # OS / shell command injection — keep CWE-78 for command-injection;
    # the generic ``rce`` slug covers many roots, so map it to CWE-94
    # (Improper Control of Generation of Code) which is the broader
    # parent. Specific RCE subtypes carry their precise CWE.
    "rce": 94,
    "rce-candidate": 94,
    "command-injection": 78,
    "shell-injection": 78,
    "deserialization": 502,           # CWE-502 Deserialization of Untrusted Data
    "rce-deserialization": 502,
    "log4shell": 94,                  # CVE-2021-44228 family
    "prototype-pollution": 1321,      # CWE-1321 Improperly Controlled Modification
                                      # of Object Prototype Attributes
    "request-smuggling": 444,         # CWE-444 Inconsistent Interpretation
    "cache-poisoning": 444,
    "host-header-injection": 444,

    # ------------------------------------------------------------------
    # Web — auth / access / business logic
    # ------------------------------------------------------------------
    "auth-bypass": 287,
    "broken-auth": 287,
    "csrf": 352,
    "csrf-candidate": 352,
    "idor": 639,
    "idor-candidate": 639,
    "mass-assignment": 915,           # CWE-915 Modification of Dynamically-
                                      # Determined Object Attributes
    "race-condition": 362,
    "open-redirect": 601,
    "open-redirect-candidate": 601,
    "path-traversal": 22,
    "cors-misconfig": 942,            # CWE-942 Permissive Cross-domain Policy
    "subdomain-takeover": 1357,       # CWE-1357 Reliance on Insufficiently
                                      # Trustworthy Component
    "graphql-introspection": 200,

    # ------------------------------------------------------------------
    # Web — SSRF
    # ------------------------------------------------------------------
    "ssrf": 918,
    "ssrf-candidate": 918,
    "ssrf-imds": 918,
    "ssrf-imds-candidate": 918,

    # ------------------------------------------------------------------
    # OWASP LLM Top 10 (2025 revision) — these mappings are best-effort
    # because MITRE has not yet adopted dedicated CWEs for several LLM
    # weakness classes. Bug bounty platforms accept the parent weakness
    # ID; reporter-agent narrative carries the OWASP-LLM identifier.
    # ------------------------------------------------------------------
    "llm01-prompt-injection": 1426,   # CWE-1426 Improper Validation of
                                      # Generative AI Output
    "llm02-data-leakage": 200,
    "llm03-supply-chain": 1357,       # CWE-1357 Insufficiently Trustworthy
                                      # Component (model / dependency)
    "llm04-data-poisoning": 1390,     # CWE-1390 Weak Authentication / model
                                      # provenance proxy
    "llm05-improper-output-handling": 79,  # downstream XSS / template injection
    "llm06-excessive-agency": 250,    # CWE-250 Execution with Unnecessary
                                      # Privileges (more precise than CWE-269)
    "llm07-system-prompt-leak": 209,  # CWE-209 Generation of Error Message
                                      # Containing Sensitive Information
    "llm08-vector-embedding-weakness": 1426,
    "llm09-misinformation": 1426,
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
