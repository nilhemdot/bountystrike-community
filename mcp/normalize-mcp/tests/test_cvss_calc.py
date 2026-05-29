# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for CVSS scoring + severity mapping.

Sample vectors taken from FIRST.org published examples; expected scores
are the reference outputs. Any drift here is either a library bug or a
spec change — investigate before adjusting expectations.
"""

from __future__ import annotations

import pytest
from normalize_mcp.cvss_calc import (
    SEVERITY_BANDS,
    compute,
    detect_version,
    severity_from_score,
)

# ---------------------------------------------------------------------------
# detect_version
# ---------------------------------------------------------------------------


def test_detect_v31() -> None:
    assert detect_version("CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H") == "3.1"


def test_detect_v4() -> None:
    assert (
        detect_version(
            "CVSS:4.0/AV:N/AC:L/AT:N/PR:N/UI:N/VC:H/VI:H/VA:H/SC:N/SI:N/SA:N"
        )
        == "4.0"
    )


def test_detect_rejects_v2() -> None:
    with pytest.raises(ValueError):
        detect_version("AV:N/AC:L/Au:N/C:C/I:C/A:C")


def test_detect_rejects_garbage() -> None:
    with pytest.raises(ValueError):
        detect_version("not-a-vector")


# ---------------------------------------------------------------------------
# severity_from_score
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "score,expected",
    [
        (0.0, "informational"),
        (0.05, "informational"),
        (0.1, "low"),
        (3.9, "low"),
        (4.0, "medium"),
        (6.9, "medium"),
        (7.0, "high"),
        (8.9, "high"),
        (9.0, "critical"),
        (10.0, "critical"),
    ],
)
def test_severity_bands(score: float, expected: str) -> None:
    assert severity_from_score(score) == expected


def test_severity_rejects_out_of_range() -> None:
    with pytest.raises(ValueError):
        severity_from_score(-0.1)
    with pytest.raises(ValueError):
        severity_from_score(10.1)


# ---------------------------------------------------------------------------
# compute — v3.1
# ---------------------------------------------------------------------------


def test_compute_v31_critical_rce() -> None:
    # FIRST CVSS v3.1 example for an unauthenticated remote RCE.
    out = compute("CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H")
    assert out["version"] == "3.1"
    assert out["base_score"] >= 9.5
    assert out["severity"] == "critical"


def test_compute_v31_medium_xss() -> None:
    # Reflected XSS, requires user interaction.
    out = compute("CVSS:3.1/AV:N/AC:L/PR:N/UI:R/S:C/C:L/I:L/A:N")
    assert out["version"] == "3.1"
    assert 4.0 <= out["base_score"] < 7.0
    assert out["severity"] == "medium"


def test_compute_v31_high_idor() -> None:
    # Authenticated IDOR — requires PR:L, no UI.
    out = compute("CVSS:3.1/AV:N/AC:L/PR:L/UI:N/S:U/C:H/I:H/A:N")
    assert out["base_score"] >= 7.0
    assert out["severity"] == "high"


# ---------------------------------------------------------------------------
# compute — v4.0
# ---------------------------------------------------------------------------


def test_compute_v4_critical() -> None:
    # FIRST v4 example — full remote RCE, all C/I/A High.
    out = compute(
        "CVSS:4.0/AV:N/AC:L/AT:N/PR:N/UI:N/VC:H/VI:H/VA:H/SC:N/SI:N/SA:N"
    )
    assert out["version"] == "4.0"
    assert out["base_score"] >= 9.0
    assert out["severity"] == "critical"


def test_compute_v4_low() -> None:
    # All metrics Low — confidentiality only.
    out = compute(
        "CVSS:4.0/AV:N/AC:H/AT:P/PR:H/UI:A/VC:L/VI:N/VA:N/SC:N/SI:N/SA:N"
    )
    assert out["version"] == "4.0"
    assert out["base_score"] < 4.0
    assert out["severity"] == "low"


# ---------------------------------------------------------------------------
# compute — error cases
# ---------------------------------------------------------------------------


def test_compute_rejects_unknown_prefix() -> None:
    with pytest.raises(ValueError):
        compute("CVSS:2.0/AV:N/AC:L/Au:N/C:C/I:C/A:C")


def test_compute_rejects_malformed_vector() -> None:
    with pytest.raises(Exception):  # noqa: B017 - cvss library raises various exception types for malformed input
        # The cvss library raises its own exception type for malformed
        # bodies; we just want to confirm the wrapper does not silently
        # return a 0.0 score.
        compute("CVSS:3.1/AV:invalid")


# ---------------------------------------------------------------------------
# Severity bands constant — sanity
# ---------------------------------------------------------------------------


def test_severity_bands_sorted_descending() -> None:
    thresholds = [b[0] for b in SEVERITY_BANDS]
    assert thresholds == sorted(thresholds, reverse=True)
