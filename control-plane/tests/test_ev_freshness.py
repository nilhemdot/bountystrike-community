"""Freshness decay + CVE opportunity score (research/02 §Freshness decay)."""

from __future__ import annotations

import math

import pytest
from control_plane.domains.program_ranking import (
    LAMBDA_SCOPE,
    MU_KEV,
    compute_freshness,
    compute_kev_freshness,
    compute_scope_freshness,
    cve_opportunity_score,
)


def test_zero_hours_is_one() -> None:
    assert compute_scope_freshness(0.0) == pytest.approx(1.0)
    assert compute_kev_freshness(0.0) == pytest.approx(1.0)
    assert compute_freshness(0.0) == pytest.approx(1.0)


def test_scope_freshness_48h_is_about_097() -> None:
    # research/02: 0.97 @ 48h
    val = compute_scope_freshness(48.0)
    assert val == pytest.approx(0.9693, abs=0.01)


def test_kev_freshness_72h_is_about_050() -> None:
    # research/02: KEV halves in ~72h
    val = compute_kev_freshness(72.0)
    assert val == pytest.approx(0.4999, abs=0.01)


def test_scope_freshness_720h_is_about_063() -> None:
    # research/02: 0.63 @ 1mo (720h)
    val = compute_scope_freshness(720.0)
    assert val == pytest.approx(0.6263, abs=0.01)


def test_scope_freshness_one_week_is_about_089() -> None:
    # research/02: 0.89 @ 1wk (168h)
    val = compute_scope_freshness(168.0)
    assert val == pytest.approx(0.8966, abs=0.01)


def test_negative_hours_clamped_to_one() -> None:
    assert compute_scope_freshness(-5.0) == 1.0
    assert compute_kev_freshness(-5.0) == 1.0


def test_decay_constants_match_research() -> None:
    assert pytest.approx(0.00065) == LAMBDA_SCOPE
    assert pytest.approx(0.00963) == MU_KEV


def test_cve_opportunity_score_template_factor_quarters_it() -> None:
    """Public Nuclei template applies a 0.25x penalty (saturated)."""
    no_template = cve_opportunity_score(
        epss=0.8, kev_age_hours=0.0, has_nuclei_template=False
    )
    with_template = cve_opportunity_score(
        epss=0.8, kev_age_hours=0.0, has_nuclei_template=True
    )
    assert with_template == pytest.approx(no_template * 0.25, abs=0.001)


def test_cve_opportunity_score_uses_max_of_epss_and_cvss_floor() -> None:
    """exploit_prob = max(epss, cvss_exploitability * 0.3)."""
    # epss tiny → cvss_exploitability * 0.3 wins
    score = cve_opportunity_score(
        epss=0.01, kev_age_hours=0.0, has_nuclei_template=False, cvss_exploitability=1.0
    )
    assert score == pytest.approx(0.30, abs=0.01)


def test_cve_opportunity_score_kev_age_decays() -> None:
    """Older KEV publication → lower opportunity (freshness multiplier)."""
    fresh = cve_opportunity_score(epss=0.6, kev_age_hours=0.0, has_nuclei_template=False)
    stale = cve_opportunity_score(epss=0.6, kev_age_hours=72.0, has_nuclei_template=False)
    assert stale < fresh
    assert stale == pytest.approx(0.6 * math.exp(-MU_KEV * 72.0), abs=0.001)


def test_cve_opportunity_score_capped_at_one() -> None:
    score = cve_opportunity_score(
        epss=10.0, kev_age_hours=0.0, has_nuclei_template=False
    )
    assert score == pytest.approx(1.0)
