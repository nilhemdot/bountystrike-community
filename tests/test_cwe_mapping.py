"""Unit tests for scripts.check_cwe_mapping.

Locks the validator-agent CWE → oracle map at ``.claude/agents/validator.md``
§CWE → Oracle Mapping. Mirrors the rationale in
``docs/audits/validator_agent_contract_audit_2026-05-13.md`` §Gap 4 —
the mapping lives in agent runtime and can silently drift across model
versions; this fixture catches drift if the helper is updated.
"""

from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, ROOT)

from scripts.check_cwe_mapping import normalize_cwe_to_oracle  # noqa: E402


@pytest.mark.parametrize(
    "cwe,expected",
    [
        # Recon-emitted *-candidate forms (recon.md:134-144).
        ("xss-candidate", "verify_xss"),
        ("ssrf-candidate", "verify_ssrf"),
        ("ssrf-imds-candidate", "verify_ssrf_imds"),
        ("sqli-candidate", "verify_sqli"),
        ("ssti-candidate", "verify_ssti"),
        ("open-redirect-candidate", "verify_open_redirect"),
        ("idor-candidate", "verify_idor"),
        ("rce-candidate", "verify_rce"),
        # Canonical CWE IDs (validator.md:54-66).
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
        # Bare normalised forms (post strip + lowercase).
        ("xss", "verify_xss"),
        ("ssrf-imds", "verify_ssrf_imds"),
        # Whitespace + case variants — spec says case-insensitive prefix.
        ("  XSS-Candidate  ", "verify_xss"),
        # Unknown → None (validator drops to validation_pending).
        ("", None),
        (None, None),
        ("CWE-9999", None),
        ("bogus", None),
    ],
)
def test_normalize_cwe_to_oracle(cwe, expected):
    assert normalize_cwe_to_oracle(cwe) == expected


def test_specificity_ordering():
    """``ssrf-imds`` must NOT collapse onto ``verify_ssrf``.

    The spec's prefix-match has an implicit specificity ordering. This
    test guards the helper from a reordering regression — without
    ``ssrf-imds`` matched first, the prefix ``ssrf`` would win and
    every IMDS finding would silently route to the wrong oracle.
    """
    assert normalize_cwe_to_oracle("ssrf-imds") == "verify_ssrf_imds"
    assert normalize_cwe_to_oracle("ssrf-imds-candidate") == "verify_ssrf_imds"
    assert normalize_cwe_to_oracle("ssrf") == "verify_ssrf"
    assert normalize_cwe_to_oracle("ssrf-candidate") == "verify_ssrf"
