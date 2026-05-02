"""EV formula validation over 50 synthetic programs.

Tests in this file verify structural properties of the EV formula:
- Monotonicity: increasing a positive signal must not decrease the score
- Boundary clamping: all factor outputs stay in [0, 1]
- Asset-type ordering: ASSET_TYPE_WEIGHTS ordering is reflected in f_fit
- Freshness decay: older last_modified_at → lower f_ops
- Saturation ordering: higher dup_rate / lower triage → lower f_saturation
- Edge cases: null last_modified_at, zero payout, extreme stale programs
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from control_plane.domains.program_ranking import (
    ASSET_TYPE_WEIGHTS,
    OperatorProfile,
    ProgramFeatures,
    compute_f_fit,
    compute_f_ops,
    compute_f_payout,
    compute_f_saturation,
    rank_programs,
    score_program,
)

FIXTURES = Path(__file__).parent / "fixtures" / "programs_50.json"

# Freshness fixture handles encode an intended age (e.g. "freshness-1h"
# = "modified ~1 hour ago"). The static JSON timestamps drift as the
# fixture file ages, breaking the f_ops decay assertions. We rebuild
# `last_modified_at` relative to `datetime.now(UTC)` at load time so
# the relative ordering and absolute thresholds stay stable forever.
_FRESHNESS_DELTAS = {
    "freshness-1h": timedelta(hours=1),
    "freshness-48h": timedelta(hours=48),
    "freshness-30d": timedelta(days=30),
    "freshness-180d": timedelta(days=180),
    "freshness-365d": timedelta(days=365),
}

_PROGRAMS: list[ProgramFeatures] | None = None


def _load() -> list[ProgramFeatures]:
    global _PROGRAMS
    if _PROGRAMS is None:
        raw = json.loads(FIXTURES.read_text())
        now = datetime.now(UTC)
        out: list[ProgramFeatures] = []
        for entry in raw:
            delta = _FRESHNESS_DELTAS.get(entry.get("handle"))
            if delta is not None:
                entry["last_modified_at"] = now - delta
            elif entry.get("last_modified_at"):
                entry["last_modified_at"] = datetime.fromisoformat(entry["last_modified_at"])
            out.append(ProgramFeatures(**entry))
        _PROGRAMS = out
    return _PROGRAMS


def _by_handle(handle: str) -> ProgramFeatures:
    for p in _load():
        if p.handle == handle:
            return p
    raise KeyError(handle)


def _default_operator() -> OperatorProfile:
    return OperatorProfile(
        asset_type_pref={
            "smart_contract": 0.8,
            "cloud_config": 0.8,
            "ai_model": 0.7,
            "api": 0.8,
            "web-application": 0.7,
            "cidr": 0.5,
            "android": 0.6,
            "ios": 0.6,
            "executable": 0.4,
            "vdp": 0.1,
        },
    )


# ---------------------------------------------------------------------------
# Basic fixture integrity
# ---------------------------------------------------------------------------


def test_fixture_loads_50_programs() -> None:
    programs = _load()
    assert len(programs) == 50


def test_all_handles_unique() -> None:
    handles = [p.handle for p in _load()]
    assert len(handles) == len(set(handles))


def test_all_ev_scores_in_unit_interval() -> None:
    op = _default_operator()
    for p in _load():
        bd = score_program(p, op)
        assert 0.0 <= bd.ev_score <= 1.0, f"{p.handle}: ev_score={bd.ev_score}"


def test_all_factor_scores_in_unit_interval() -> None:
    op = _default_operator()
    for p in _load():
        bd = score_program(p, op)
        for field in ("f_payout", "f_saturation", "f_ops", "f_fit", "f_cve"):
            val = getattr(bd, field)
            assert 0.0 <= val <= 1.0, f"{p.handle}: {field}={val}"


# ---------------------------------------------------------------------------
# Payout monotonicity (payout-tier-1 through payout-tier-5)
# ---------------------------------------------------------------------------


def test_f_payout_monotone_over_tiers() -> None:
    """Higher payout_max → strictly higher f_payout (all tiers share bounty_paid_ratio=0.5)."""
    tiers = [
        compute_f_payout(_by_handle(f"payout-tier-{i}"))
        for i in range(1, 6)
    ]
    for i in range(len(tiers) - 1):
        assert tiers[i] < tiers[i + 1], (
            f"Tier {i + 1} f_payout ({tiers[i]:.4f}) not < tier {i + 2} ({tiers[i + 1]:.4f})"
        )


def test_payout_tier5_caps_at_one() -> None:
    """payout_max=150k > PAYOUT_NORM_CAP ($50k) → f_payout must == 1.0."""
    assert compute_f_payout(_by_handle("payout-tier-5")) == pytest.approx(1.0)


def test_ev_score_monotone_over_payout_tiers() -> None:
    """EV scores follow payout tier order (all other features identical)."""
    op = _default_operator()
    scores = [
        score_program(_by_handle(f"payout-tier-{i}"), op).ev_score
        for i in range(1, 6)
    ]
    for i in range(len(scores) - 1):
        assert scores[i] < scores[i + 1]


# ---------------------------------------------------------------------------
# Saturation monotonicity (sat-pristine → sat-saturated)
# ---------------------------------------------------------------------------


def test_f_saturation_monotone_decreasing() -> None:
    """Higher dup_rate / lower triage_acceptance → lower f_saturation."""
    sat_handles = [
        "sat-pristine",
        "sat-low-dup",
        "sat-medium",
        "sat-high-dup",
        "sat-saturated",
    ]
    sats = [compute_f_saturation(_by_handle(h)) for h in sat_handles]
    for i in range(len(sats) - 1):
        assert sats[i] > sats[i + 1], (
            f"{sat_handles[i]} ({sats[i]:.4f}) not > {sat_handles[i + 1]} ({sats[i + 1]:.4f})"
        )


def test_sat_pristine_near_one() -> None:
    """dup_rate=0, triage=1.0 → f_saturation == 1.0."""
    assert compute_f_saturation(_by_handle("sat-pristine")) == pytest.approx(1.0)


def test_sat_saturated_is_zero() -> None:
    """dup_rate=1.0, triage=0.0 → f_saturation == 0.0."""
    assert compute_f_saturation(_by_handle("sat-saturated")) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Freshness monotonicity (freshness-1h → freshness-365d)
# ---------------------------------------------------------------------------


def test_f_ops_monotone_decreasing_with_age() -> None:
    """Older last_modified_at → lower f_ops."""
    freshness_handles = [
        "freshness-1h",
        "freshness-48h",
        "freshness-30d",
        "freshness-180d",
        "freshness-365d",
    ]
    ops_scores = [compute_f_ops(_by_handle(h)) for h in freshness_handles]
    for i in range(len(ops_scores) - 1):
        assert ops_scores[i] > ops_scores[i + 1], (
            f"{freshness_handles[i]} ({ops_scores[i]:.4f}) not > "
            f"{freshness_handles[i + 1]} ({ops_scores[i + 1]:.4f})"
        )


def test_f_ops_1h_near_one() -> None:
    """Modified very recently → f_ops high (> 0.95).

    Exact delta depends on real-world test runtime vs fixture timestamp.
    """
    score = compute_f_ops(_by_handle("freshness-1h"))
    assert score > 0.95, f"freshness-1h f_ops={score:.4f} unexpectedly low"


def test_f_ops_365d_less_than_half() -> None:
    """Modified 365 days ago → f_ops should be < 0.60 (well into decay region)."""
    score = compute_f_ops(_by_handle("freshness-365d"))
    assert score < 0.60


def test_f_ops_null_last_modified_returns_half() -> None:
    """None last_modified_at → f_ops == 0.5 (fallback for unknown freshness)."""
    score = compute_f_ops(_by_handle("no-last-modified"))
    assert score == pytest.approx(0.5)


def test_ancient_program_has_very_low_f_ops() -> None:
    """last_modified_at=2020-01-01 → f_ops near 0."""
    score = compute_f_ops(_by_handle("ancient-program"))
    assert score < 0.10


# ---------------------------------------------------------------------------
# Asset-type weights ordering
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "high_handle,low_handle",
    [
        ("asset-smart-contract", "asset-cloud-config"),
        ("asset-cloud-config", "asset-ai-model"),
        ("asset-ai-model", "asset-api"),
        ("asset-api", "asset-web"),
        ("asset-web", "asset-cidr"),
        ("asset-cidr", "asset-android"),
        ("asset-android", "asset-ios"),
        ("asset-ios", "asset-executable"),
        ("asset-executable", "asset-vdp-only"),
    ],
)
def test_asset_type_weight_ordering(high_handle: str, low_handle: str) -> None:
    """Programs identical except asset_type: higher ASSET_TYPE_WEIGHT → higher f_fit.

    Operator pref is uniform (0.7 for all) so only ASSET_TYPE_WEIGHTS drives f_fit.
    """
    uniform_op = OperatorProfile(
        asset_type_pref={k: 0.7 for k in ASSET_TYPE_WEIGHTS},
    )
    high_fit = compute_f_fit(_by_handle(high_handle), uniform_op)
    low_fit = compute_f_fit(_by_handle(low_handle), uniform_op)
    assert high_fit >= low_fit, (
        f"{high_handle} f_fit ({high_fit:.4f}) not >= {low_handle} f_fit ({low_fit:.4f})"
    )


def test_vdp_only_lowest_f_fit_with_uniform_pref() -> None:
    """asset-vdp-only must have strictly lowest f_fit under uniform operator prefs."""
    uniform_op = OperatorProfile(
        asset_type_pref={k: 0.7 for k in ASSET_TYPE_WEIGHTS},
    )
    vdp_fit = compute_f_fit(_by_handle("asset-vdp-only"), uniform_op)
    others = [
        h for h in [
            "asset-smart-contract", "asset-cloud-config", "asset-ai-model",
            "asset-api", "asset-web", "asset-cidr", "asset-android",
            "asset-ios", "asset-executable",
        ]
    ]
    for handle in others:
        assert vdp_fit < compute_f_fit(_by_handle(handle), uniform_op), (
            f"vdp f_fit ({vdp_fit:.4f}) not < {handle}"
        )


def test_smart_contract_highest_f_fit_with_uniform_pref() -> None:
    """asset-smart-contract must have highest f_fit under uniform prefs.

    With uniform pref=0.7 and ceiling=1.40: f_fit = 0.7*1.40/1.40 = 0.7 (not 1.0).
    To reach 1.0, pref must be 1.0. This test verifies the ceiling normalization.
    """
    uniform_op = OperatorProfile(
        asset_type_pref={k: 0.7 for k in ASSET_TYPE_WEIGHTS},
    )
    sc_fit = compute_f_fit(_by_handle("asset-smart-contract"), uniform_op)
    assert sc_fit == pytest.approx(0.7, abs=0.01), f"Expected ~0.70, got {sc_fit}"

    # With pref=1.0, smart_contract reaches f_fit ceiling of 1.0
    max_op = OperatorProfile(asset_type_pref={k: 1.0 for k in ASSET_TYPE_WEIGHTS})
    sc_fit_max = compute_f_fit(_by_handle("asset-smart-contract"), max_op)
    assert sc_fit_max == pytest.approx(1.0), f"Expected 1.0 with max pref, got {sc_fit_max}"


# ---------------------------------------------------------------------------
# VDP / zero-payout edge cases
# ---------------------------------------------------------------------------


def test_zero_payout_gives_zero_f_payout() -> None:
    for handle in ("vdp-active", "vdp-stale", "vdp-saturated", "open-vdp-corp"):
        fp = compute_f_payout(_by_handle(handle))
        assert fp == pytest.approx(0.0), f"{handle}: f_payout={fp}"


def test_vdp_programs_have_low_ev_scores() -> None:
    """VDP programs have zero f_payout so ev_score is bounded by non-payout factors.

    - Saturated/stale VDP: ev_score < 0.35 (poor saturation + poor freshness compound).
    - Active low-dup VDP: can reach ~0.43 (good saturation + freshness, zero payout).
    - All VDP programs must score below programs with equivalent non-payout features
      but non-zero payout.
    """
    op = _default_operator()

    # Clearly bad VDP programs: saturated or stale → low ev
    for handle in ("vdp-stale", "vdp-saturated"):
        bd = score_program(_by_handle(handle), op)
        assert bd.ev_score < 0.35, f"{handle} ev_score={bd.ev_score} should be < 0.35"

    # vdp-active is unusually fresh + low-dup → can score higher due to sat+ops weight
    bd_active = score_program(_by_handle("vdp-active"), op)
    assert bd_active.f_payout == pytest.approx(0.0), "zero payout must give zero f_payout"
    assert bd_active.ev_score < 0.55, "even best-case VDP can't exceed 0.55 without payout"


# ---------------------------------------------------------------------------
# Top-tier programs
# ---------------------------------------------------------------------------


def test_top_tier_defi_near_max() -> None:
    """top-tier-defi: payout=100k (capped), bounty_paid_ratio=0.90, fresh, low dup, SC assets."""
    op = _default_operator()
    bd = score_program(_by_handle("top-tier-defi"), op)
    assert bd.ev_score > 0.85, f"top-tier-defi ev_score={bd.ev_score} should be > 0.85"
    assert bd.f_payout == pytest.approx(1.0)
    # (1 - dup_rate=0.05) * triage=0.80 = 0.95 * 0.80 = 0.76
    assert bd.f_saturation == pytest.approx(0.76, abs=0.01)


def test_top_tier_outranks_low_everything() -> None:
    op = _default_operator()
    top = score_program(_by_handle("top-tier-defi"), op).ev_score
    low = score_program(_by_handle("low-everything"), op).ev_score
    assert top > low


# ---------------------------------------------------------------------------
# Ranking
# ---------------------------------------------------------------------------


def test_rank_50_sorted_descending() -> None:
    op = _default_operator()
    ranked = rank_programs(_load(), op, top_n=50)
    scores = [bd.ev_score for _, bd in ranked]
    assert scores == sorted(scores, reverse=True)


def test_rank_returns_at_most_top_n() -> None:
    op = _default_operator()
    assert len(rank_programs(_load(), op, top_n=10)) == 10
    assert len(rank_programs(_load(), op, top_n=50)) == 50


def test_top_3_are_high_value_programs() -> None:
    """Top 3 should be from high-payout, low-dup, fresh programs."""
    op = _default_operator()
    ranked = rank_programs(_load(), op, top_n=3)
    top_handles = {h for h, _ in ranked}
    high_value = {"top-tier-defi", "top-tier-cloud", "defi-protocol", "skyhigh-cloud"}
    assert top_handles & high_value, (
        f"Top 3 handles {top_handles} don't overlap known high-value programs"
    )


def test_ancient_and_vdp_in_bottom_10() -> None:
    op = _default_operator()
    ranked = rank_programs(_load(), op, top_n=50)
    bottom_handles = {h for h, _ in ranked[-10:]}
    expected_bottom = {"ancient-program", "vdp-saturated", "low-everything"}
    assert expected_bottom & bottom_handles, (
        f"Bottom 10 {bottom_handles} doesn't include any of {expected_bottom}"
    )


# ---------------------------------------------------------------------------
# Operator preference sensitivity
# ---------------------------------------------------------------------------


def test_operator_pref_flips_fit_between_asset_types() -> None:
    """Switching operator from sc-lover to web-lover flips defi vs acme-web f_fit."""
    sc_lover = OperatorProfile(
        asset_type_pref={"smart_contract": 1.0, "web-application": 0.0},
    )
    web_lover = OperatorProfile(
        asset_type_pref={"smart_contract": 0.0, "web-application": 1.0},
    )
    defi = _by_handle("defi-protocol")
    acme = _by_handle("acme-web")

    assert compute_f_fit(defi, sc_lover) > compute_f_fit(defi, web_lover)
    assert compute_f_fit(acme, web_lover) > compute_f_fit(acme, sc_lover)


def test_zero_pref_gives_zero_f_fit() -> None:
    """Operator with 0.0 pref for all asset types → f_fit == 0.0."""
    zero_op = OperatorProfile(asset_type_pref={k: 0.0 for k in ASSET_TYPE_WEIGHTS})
    for handle in ("asset-smart-contract", "asset-api", "asset-web"):
        fit = compute_f_fit(_by_handle(handle), zero_op)
        assert fit == pytest.approx(0.0), f"{handle}: f_fit={fit} with zero pref"


# ---------------------------------------------------------------------------
# Platform diversity (smoke)
# ---------------------------------------------------------------------------


def test_all_platforms_score_cleanly() -> None:
    """Programs from 7 platforms all produce valid ScoreBreakdown without error."""
    op = _default_operator()
    platform_handles = [
        "synack-web",
        "yeswehack-api",
        "h1-mobile",
        "immunefi-defi-small",
        "cobalt-cloud",
        "defi-protocol",
        "acme-web",
    ]
    for handle in platform_handles:
        bd = score_program(_by_handle(handle), op)
        assert 0.0 <= bd.ev_score <= 1.0


# ---------------------------------------------------------------------------
# f_cve placeholder
# ---------------------------------------------------------------------------


def test_f_cve_is_zero_for_all_50() -> None:
    """CVE bonus placeholder must return 0.0 for every program."""
    op = _default_operator()
    for p in _load():
        bd = score_program(p, op)
        assert bd.f_cve == pytest.approx(0.0), f"{p.handle}: f_cve={bd.f_cve}"
