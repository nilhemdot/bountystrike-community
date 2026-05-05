"""Unit tests for the EV calibration service (Phase 3 §10.5).

Pure-function coverage — no DB, no scipy mocking. We feed in synthetic
HuntOutcome lists with known correlation structure and assert the
service returns the expected Spearman ρ + verdict.
"""

from __future__ import annotations

import math

import pytest
from control_plane.domains.program_ranking.services.calibration_service import (
    _TARGET_RHO,
    calibration_report,
    compute_spearman_correlation,
)
from control_plane.domains.program_ranking.value_objects.hunt_outcome import HuntOutcome


def _outcome(rank: int, find_rate: float) -> HuntOutcome:
    """find_rate ∈ [0,1] → submitted=100, confirmed=floor(100·find_rate).

    100 submissions per outcome avoids the rank-tie collisions that 10
    would induce when rates are within 0.05 of each other.
    """
    submitted = 100
    confirmed = int(submitted * find_rate)
    return HuntOutcome(
        program_handle=f"prog-{rank}",
        operator_id="alice",
        scan_job_id=None,
        ev_rank=rank,
        submitted_count=submitted,
        confirmed_count=confirmed,
    )


# ──────────────────────────────────────────────────────────────────────
# compute_spearman_correlation
# ──────────────────────────────────────────────────────────────────────


def test_perfect_calibration_yields_rho_one() -> None:
    """Top EV ranks have highest find-rate → ρ ≈ 1.0."""
    outcomes = [_outcome(i, 1.0 - 0.05 * (i - 1)) for i in range(1, 11)]
    rho, _ = compute_spearman_correlation(outcomes)
    assert rho == pytest.approx(1.0, abs=1e-6)


def test_inverted_calibration_yields_rho_negative_one() -> None:
    """Top EV ranks have LOWEST find-rate → ρ ≈ -1.0."""
    outcomes = [_outcome(i, 0.05 * (i - 1)) for i in range(1, 11)]
    rho, _ = compute_spearman_correlation(outcomes)
    assert rho == pytest.approx(-1.0, abs=1e-6)


def test_random_calibration_yields_low_rho() -> None:
    """No relationship between rank and find-rate → |ρ| close to 0."""
    # Hand-crafted no-correlation pattern.
    rates = [0.5, 0.4, 0.6, 0.3, 0.7, 0.5, 0.5, 0.5, 0.5, 0.5]
    outcomes = [_outcome(i + 1, rates[i]) for i in range(10)]
    rho, _ = compute_spearman_correlation(outcomes)
    assert abs(rho) < 0.5


def test_too_few_outcomes_returns_zero() -> None:
    """scipy needs ≥ 3 points; below that the service returns (0, 1)."""
    rho, p = compute_spearman_correlation([_outcome(1, 0.9), _outcome(2, 0.5)])
    assert rho == 0.0
    assert p == 1.0


def test_empty_list_returns_zero() -> None:
    rho, p = compute_spearman_correlation([])
    assert rho == 0.0
    assert p == 1.0


def test_all_equal_ranks_returns_zero() -> None:
    """No variance in ranks → ρ undefined; service returns (0, 1)."""
    outcomes = [_outcome(5, 0.1 * i) for i in range(1, 6)]
    rho, p = compute_spearman_correlation(outcomes)
    assert rho == 0.0
    assert p == 1.0


def test_all_equal_rates_returns_zero() -> None:
    """No variance in find_rates → ρ undefined; service returns (0, 1)."""
    outcomes = [_outcome(i, 0.5) for i in range(1, 6)]
    rho, p = compute_spearman_correlation(outcomes)
    assert rho == 0.0
    assert p == 1.0


def test_skips_outcomes_with_null_ev_rank() -> None:
    """ev_rank=None outcomes are filtered out before correlation."""
    good = [_outcome(i, 1.0 - 0.1 * (i - 1)) for i in range(1, 6)]
    null_rank = HuntOutcome(
        program_handle="prog-x",
        operator_id="alice",
        scan_job_id=None,
        ev_rank=None,
        submitted_count=10,
        confirmed_count=5,
    )
    rho, _ = compute_spearman_correlation([*good, null_rank])
    # Should be the same as just `good` — null_rank gets filtered.
    assert rho > 0.9
    assert not math.isnan(rho)


# ──────────────────────────────────────────────────────────────────────
# calibration_report
# ──────────────────────────────────────────────────────────────────────


def test_report_passes_when_rho_above_target() -> None:
    """ρ ≥ 0.60 → passes=True, weight_recommendations=None."""
    outcomes = [_outcome(i, 1.0 - 0.05 * (i - 1)) for i in range(1, 11)]
    report = calibration_report(outcomes)
    assert report["passes"] is True
    assert report["rho"] >= _TARGET_RHO
    assert report["weight_recommendations"] is None
    assert report["n_outcomes"] == 10
    assert report["n_unique_programs"] == 10


def test_report_does_not_recommend_with_n_below_50() -> None:
    """Weight rec only fires with n ≥ 50, even if ρ is bad."""
    bad_outcomes = [_outcome(i, 0.05 * (i - 1)) for i in range(1, 11)]
    report = calibration_report(bad_outcomes)
    assert report["passes"] is False
    assert report["weight_recommendations"] is None  # n < 50


def test_report_emits_weight_rec_when_rho_low_and_n_large() -> None:
    """ρ < 0.60 AND n ≥ 50 → weight_recommendations populated."""
    # 60 outcomes with inverted correlation:
    #   rank 1   → find_rate ≈ 0.0 (worst)
    #   rank 60  → find_rate ≈ 0.59 (best)
    # ρ comes out strongly negative (≈ -1) → fails 0.60 gate.
    outcomes = [_outcome(i, 0.01 * (i - 1)) for i in range(1, 61)]
    report = calibration_report(outcomes)
    assert report["passes"] is False
    assert report["weight_recommendations"] is not None
    # Recommendations preserve the WEIGHTS_V2 shape.
    assert set(report["weight_recommendations"].keys()) == {
        "payout", "saturation", "ops", "fit", "cve_bonus",
    }


def test_report_handles_empty_input() -> None:
    report = calibration_report([])
    assert report["rho"] == 0.0
    assert report["passes"] is False
    assert report["n_outcomes"] == 0
    assert report["weight_recommendations"] is None
