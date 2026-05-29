# SPDX-License-Identifier: AGPL-3.0-or-later

"""CWE→oracle mapping helper that mirrors validator-agent spec.

Mirrors the table at ``.claude/agents/validator.md`` §CWE → Oracle Mapping.
Validator-agent is an LLM-runtime agent (no Python module). This helper
freezes the spec in code so operators can run a regression check before
boot — guards against model-version drift silently misrouting a finding's
``cwe`` to the wrong oracle.

Run as a script to dump the canonical fixture; import
``normalize_cwe_to_oracle`` from tests to assert invariants.

Audit reference: docs/audits/validator_agent_contract_audit_2026-05-13.md
§Gap 4.
"""

from __future__ import annotations

import sys

# Order matters for prefix matching: more specific prefixes first so
# ``ssrf-imds`` does not collapse onto ``verify_ssrf``.
_CWE_ID_MAP = {
    "cwe-79": "verify_xss",
    "cwe-89": "verify_sqli",
    "cwe-74": "verify_ssti",
    "cwe-94": "verify_ssti",
    "cwe-77": "verify_rce",
    "cwe-78": "verify_rce",
    "cwe-601": "verify_open_redirect",
    "cwe-639": "verify_idor",
    "cwe-284": "verify_idor",
    "cwe-918-imds": "verify_ssrf_imds",
    "cwe-918": "verify_ssrf",
}

_PREFIX_MAP: tuple[tuple[str, str], ...] = (
    ("ssrf-imds", "verify_ssrf_imds"),
    ("open-redirect", "verify_open_redirect"),
    ("xss", "verify_xss"),
    ("ssrf", "verify_ssrf"),
    ("sqli", "verify_sqli"),
    ("ssti", "verify_ssti"),
    ("idor", "verify_idor"),
    ("rce", "verify_rce"),
)


def normalize_cwe_to_oracle(cwe: str | None) -> str | None:
    """Map a ``findings.cwe`` value to an oracle-mcp tool name.

    Returns ``None`` when the value is unrecognised — validator-agent
    falls back to ``validation_pending`` in that case per validator.md
    §Error Handling ("Unrecognised CWE").
    """
    if not cwe:
        return None
    s = cwe.strip().lower()
    if s.endswith("-candidate"):
        s = s[: -len("-candidate")]
    if s in _CWE_ID_MAP:
        return _CWE_ID_MAP[s]
    for prefix, oracle in _PREFIX_MAP:
        if s == prefix or s.startswith(prefix + "-"):
            return oracle
    return None


# Canonical fixture — every recon-emitted CWE value + every CWE ID the
# spec table lists. Used as a smoke test when this file is run directly.
_FIXTURE: tuple[tuple[str, str | None], ...] = (
    ("xss-candidate", "verify_xss"),
    ("ssrf-candidate", "verify_ssrf"),
    ("ssrf-imds-candidate", "verify_ssrf_imds"),
    ("sqli-candidate", "verify_sqli"),
    ("ssti-candidate", "verify_ssti"),
    ("open-redirect-candidate", "verify_open_redirect"),
    ("idor-candidate", "verify_idor"),
    ("rce-candidate", "verify_rce"),
    ("CWE-79", "verify_xss"),
    ("CWE-89", "verify_sqli"),
    ("CWE-918", "verify_ssrf"),
    ("CWE-918-imds", "verify_ssrf_imds"),
    ("CWE-601", "verify_open_redirect"),
    ("CWE-639", "verify_idor"),
    ("CWE-284", "verify_idor"),
    ("CWE-77", "verify_rce"),
    ("CWE-78", "verify_rce"),
    ("CWE-74", "verify_ssti"),
    ("CWE-94", "verify_ssti"),
    ("bogus", None),
    ("", None),
)


def _print_fixture_table() -> int:
    fails = 0
    width = max(len(cwe) for cwe, _ in _FIXTURE)
    for cwe, expected in _FIXTURE:
        actual = normalize_cwe_to_oracle(cwe)
        ok = actual == expected
        if not ok:
            fails += 1
        marker = "ok " if ok else "FAIL"
        print(f"  [{marker}] {cwe:<{width}} → {actual!s:<22} (expected {expected!s})")
    print()
    print(f"{len(_FIXTURE) - fails}/{len(_FIXTURE)} cases pass.")
    return 0 if fails == 0 else 1


def main(argv: list[str]) -> int:
    del argv
    return _print_fixture_table()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
