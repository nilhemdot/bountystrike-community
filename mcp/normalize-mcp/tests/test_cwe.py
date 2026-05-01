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
        ("xss", "CWE-79"),
        ("xss-candidate", "CWE-79"),
        ("stored-xss", "CWE-79"),
        ("reflected-xss", "CWE-79"),
        ("dom-xss", "CWE-79"),
        ("sqli", "CWE-89"),
        ("blind-sqli", "CWE-89"),
        ("ssrf", "CWE-918"),
        ("ssrf-imds", "CWE-918"),
        ("ssrf-imds-candidate", "CWE-918"),
        ("ssti", "CWE-94"),
        ("rce", "CWE-78"),
        ("command-injection", "CWE-78"),
        ("open-redirect", "CWE-601"),
        ("idor", "CWE-639"),
        ("auth-bypass", "CWE-287"),
        ("csrf", "CWE-352"),
        ("path-traversal", "CWE-22"),
        ("xxe", "CWE-611"),
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
        ("llm01-prompt-injection", "CWE-1426"),
        ("llm09-misinformation", "CWE-1426"),
        ("llm02-data-leakage", "CWE-200"),
        ("llm07-system-prompt-leak", "CWE-200"),
        ("llm06-excessive-agency", "CWE-269"),
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
