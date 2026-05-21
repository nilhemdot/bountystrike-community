"""Tests for CWE normalisation."""

from __future__ import annotations

import pytest
from normalize_mcp.cwe import normalize

# ---------------------------------------------------------------------------
# Numeric / canonical input
# ---------------------------------------------------------------------------


def test_numeric_string() -> None:
    assert normalize("79") == "CWE-79"


def test_canonical_passthrough() -> None:
    assert normalize("CWE-79") == "CWE-79"


def test_lowercase_canonical() -> None:
    assert normalize("cwe-79") == "CWE-79"


def test_strips_whitespace() -> None:
    assert normalize("  CWE-79  ") == "CWE-79"


# ---------------------------------------------------------------------------
# Recon / oracle slugs
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "slug,expected",
    [
        # XSS family
        ("xss", "CWE-79"),
        ("xss-candidate", "CWE-79"),
        ("stored-xss", "CWE-79"),
        ("reflected-xss", "CWE-79"),
        ("dom-xss", "CWE-79"),
        # SQL / NoSQL / LDAP / XXE
        ("sqli", "CWE-89"),
        ("blind-sqli", "CWE-89"),
        ("nosql-injection", "CWE-943"),
        ("ldap-injection", "CWE-90"),
        ("xxe", "CWE-611"),
        ("xxe-via-svg", "CWE-611"),
        # SSRF
        ("ssrf", "CWE-918"),
        ("ssrf-imds", "CWE-918"),
        ("ssrf-imds-candidate", "CWE-918"),
        # Template / code / command injection
        ("ssti", "CWE-1336"),                 # NEW: was CWE-94, now precise
        ("rce", "CWE-94"),                    # NEW: was CWE-78, now broader parent
        ("command-injection", "CWE-78"),
        ("shell-injection", "CWE-78"),
        ("deserialization", "CWE-502"),       # NEW
        ("rce-deserialization", "CWE-502"),   # NEW
        ("log4shell", "CWE-94"),              # NEW
        ("prototype-pollution", "CWE-1321"),  # NEW
        # Auth / access / business logic
        ("auth-bypass", "CWE-287"),
        ("broken-auth", "CWE-287"),
        ("csrf", "CWE-352"),
        ("idor", "CWE-639"),
        ("mass-assignment", "CWE-915"),       # NEW
        ("race-condition", "CWE-362"),        # NEW
        ("path-traversal", "CWE-22"),
        ("open-redirect", "CWE-601"),
        ("cors-misconfig", "CWE-942"),        # NEW
        ("subdomain-takeover", "CWE-1357"),   # NEW
        ("graphql-introspection", "CWE-200"), # NEW
        # Smuggling / poisoning
        ("request-smuggling", "CWE-444"),     # NEW
        ("cache-poisoning", "CWE-444"),       # NEW
        ("host-header-injection", "CWE-444"), # NEW
    ],
)
def test_known_slug_mappings(slug: str, expected: str) -> None:
    assert normalize(slug) == expected


def test_case_insensitive_slug() -> None:
    assert normalize("XSS-Candidate") == "CWE-79"


# ---------------------------------------------------------------------------
# OWASP LLM Top 10
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "slug,expected",
    [
        # Full OWASP LLM Top 10 (2025) coverage. Mappings adjusted from
        # the v0.1 set per audit reviewer 3:
        #   - LLM06 was CWE-269 (Improper Privilege Mgmt); now CWE-250
        #     (Execution with Unnecessary Privileges) — closer fit.
        #   - LLM07 was CWE-200 generic; now CWE-209 (Generation of
        #     Error Message Containing Sensitive Information) — fits
        #     system-prompt-leak more precisely.
        #   - LLM03 / 04 / 05 / 08 were missing entirely.
        ("llm01-prompt-injection", "CWE-1426"),
        ("llm02-data-leakage", "CWE-200"),
        ("llm03-supply-chain", "CWE-1357"),
        ("llm04-data-poisoning", "CWE-1390"),
        ("llm05-improper-output-handling", "CWE-79"),
        ("llm06-excessive-agency", "CWE-250"),
        ("llm07-system-prompt-leak", "CWE-209"),
        ("llm08-vector-embedding-weakness", "CWE-1426"),
        ("llm09-misinformation", "CWE-1426"),
        ("llm10-unbounded-consumption", "CWE-400"),
    ],
)
def test_llm_owasp_mapping(slug: str, expected: str) -> None:
    assert normalize(slug) == expected


# ---------------------------------------------------------------------------
# Cloud cluster fallbacks
# ---------------------------------------------------------------------------


def test_cloud_iam_privesc_maps_to_269() -> None:
    assert normalize("cloud-iam-privesc") == "CWE-269"


def test_cloud_image_cve_maps_to_1395() -> None:
    assert normalize("cloud-image-cve") == "CWE-1395"


def test_cloud_default_falls_to_16() -> None:
    assert normalize("cloud-s3-public") == "CWE-16"
    assert normalize("cloud-sg-open") == "CWE-16"


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


def test_empty_input_raises() -> None:
    with pytest.raises(ValueError):
        normalize("")


def test_unknown_slug_raises() -> None:
    with pytest.raises(ValueError):
        normalize("totally-unknown-class")


def test_malformed_cwe_id_raises() -> None:
    with pytest.raises(ValueError):
        normalize("CWE-abc")
