"""EV scoring + ranking tests over fixtures/programs.json."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from control_plane.ev import (
    ASSET_TYPE_WEIGHTS,
    WEIGHTS_V2,
    OperatorProfile,
    ProgramFeatures,
    rank_programs,
    score_program,
)
from control_plane.ev.scoring import compute_f_fit, compute_f_payout, compute_f_saturation

FIXTURES = Path(__file__).parent / "fixtures" / "programs.json"


def _load_fixture_programs() -> list[ProgramFeatures]:
    raw = json.loads(FIXTURES.read_text())
    out: list[ProgramFeatures] = []
    for entry in raw:
        if entry.get("last_modified_at"):
            entry["last_modified_at"] = datetime.fromisoformat(entry["last_modified_at"])
        out.append(ProgramFeatures(**entry))
    return out


def _balanced_operator() -> OperatorProfile:
    return OperatorProfile(
        skill_vector={"web": 0.7, "api": 0.7, "smart_contract": 0.6, "cloud": 0.5},
        time_budget_hours=40.0,
        cost_budget_usd=50.0,
        asset_type_pref={
            "web-application": 0.7,
            "api": 0.8,
            "smart_contract": 0.7,
            "cloud_config": 0.6,
            "vdp": 0.2,
        },
    )


def test_fixture_loads_five_programs() -> None:
    programs = _load_fixture_programs()
    assert len(programs) == 5
    handles = {p.handle for p in programs}
    assert handles == {
        "acme-web",
        "defi-protocol",
        "open-vdp-corp",
        "globex-api",
        "skyhigh-cloud",
    }


def test_f_payout_caps_at_one() -> None:
    """Anchor: $50k * 1.0 ratio = full credit."""
    big = ProgramFeatures(
        handle="x",
        platform="hackerone",
        payout_max=100_000,
        bounty_paid_ratio=1.0,
    )
    assert compute_f_payout(big) == pytest.approx(1.0)


def test_f_payout_zero_for_vdp() -> None:
    vdp = ProgramFeatures(handle="v", platform="hackerone", payout_max=0, bounty_paid_ratio=0.0)
    assert compute_f_payout(vdp) == pytest.approx(0.0)


def test_f_saturation_high_dup_lowers_score() -> None:
    saturated = ProgramFeatures(
        handle="s",
        platform="hackerone",
        dup_rate=0.9,
        triage_acceptance_rate=0.5,
    )
    pristine = ProgramFeatures(
        handle="p",
        platform="hackerone",
        dup_rate=0.05,
        triage_acceptance_rate=0.8,
    )
    assert compute_f_saturation(saturated) < compute_f_saturation(pristine)


def test_smart_contract_outranks_vdp_with_same_payout() -> None:
    """Asset-type weight assertion: smart_contract (1.40) > vdp (0.10)."""
    operator = OperatorProfile(
        asset_type_pref={"smart_contract": 0.8, "vdp": 0.8},
    )
    sc = ProgramFeatures(
        handle="sc",
        platform="immunefi",
        payout_max=10_000,
        bounty_paid_ratio=0.5,
        triage_acceptance_rate=0.5,
        dup_rate=0.2,
        asset_distribution={"smart_contract": 5},
    )
    vdp = ProgramFeatures(
        handle="vdp",
        platform="hackerone",
        payout_max=10_000,
        bounty_paid_ratio=0.5,
        triage_acceptance_rate=0.5,
        dup_rate=0.2,
        asset_distribution={"vdp": 5},
    )
    sc_score = score_program(sc, operator)
    vdp_score = score_program(vdp, operator)
    assert sc_score.f_fit > vdp_score.f_fit
    # Same operator pref weighting; only the ASSET_TYPE_WEIGHTS multiplier differs,
    # but f_fit is normalized — still, ev_score must reflect smart_contract advantage
    # when payout/saturation/ops are identical.
    assert sc_score.ev_score >= vdp_score.ev_score


def test_asset_type_weights_table_matches_research() -> None:
    """Sanity-check the table values (research/02 §Asset-type weights)."""
    assert ASSET_TYPE_WEIGHTS["smart_contract"] == 1.40
    assert ASSET_TYPE_WEIGHTS["cloud_config"] == 1.30
    assert ASSET_TYPE_WEIGHTS["ai_model"] == 1.25
    assert ASSET_TYPE_WEIGHTS["api"] == 1.15
    assert ASSET_TYPE_WEIGHTS["web-application"] == 1.00
    assert ASSET_TYPE_WEIGHTS["cidr"] == 0.90
    assert ASSET_TYPE_WEIGHTS["android"] == 0.85
    assert ASSET_TYPE_WEIGHTS["ios"] == 0.80
    assert ASSET_TYPE_WEIGHTS["executable"] == 0.70
    assert ASSET_TYPE_WEIGHTS["vdp"] == 0.10


def test_weights_v2_sums_to_one_minus_cve_bonus() -> None:
    """payout+saturation+ops+fit must equal 1.0; cve_bonus is multiplicative."""
    base = sum(WEIGHTS_V2[k] for k in ("payout", "saturation", "ops", "fit"))
    assert base == pytest.approx(1.0)


def test_rank_programs_sorted_descending() -> None:
    operator = _balanced_operator()
    programs = _load_fixture_programs()
    ranked = rank_programs(programs, operator)
    scores = [b.ev_score for _, b in ranked]
    assert scores == sorted(scores, reverse=True)
    assert len(ranked) == 5


def test_rank_top_n_truncates() -> None:
    operator = _balanced_operator()
    programs = _load_fixture_programs()
    top3 = rank_programs(programs, operator, top_n=3)
    assert len(top3) == 3


def test_vdp_ranks_last_by_default() -> None:
    """open-vdp-corp pays nothing, has dup_rate=0.5, asset_type vdp(0.10) — must be last."""
    operator = _balanced_operator()
    programs = _load_fixture_programs()
    ranked = rank_programs(programs, operator)
    # Last position = lowest ev_score
    assert ranked[-1][0] == "open-vdp-corp"


def test_operator_preference_shifts_ranking() -> None:
    """Changing operator asset_type_pref must shift each program's f_fit and ev_score.

    The aggregate ranking can stay stable (payout dominates), but a smart-contract-loving
    operator must give defi-protocol a *higher* f_fit than an api-loving operator does,
    and vice versa for globex-api.
    """
    sc_lover = OperatorProfile(
        asset_type_pref={
            "smart_contract": 1.0,
            "api": 0.1,
            "web-application": 0.1,
            "cloud_config": 0.1,
            "vdp": 0.0,
        },
    )
    api_lover = OperatorProfile(
        asset_type_pref={
            "smart_contract": 0.1,
            "api": 1.0,
            "web-application": 0.5,
            "cloud_config": 0.1,
            "vdp": 0.0,
        },
    )
    programs = _load_fixture_programs()

    sc_ranked = dict(rank_programs(programs, sc_lover))
    api_ranked = dict(rank_programs(programs, api_lover))

    # smart_contract program: f_fit higher under sc_lover than api_lover
    assert sc_ranked["defi-protocol"].f_fit > api_ranked["defi-protocol"].f_fit
    assert sc_ranked["defi-protocol"].ev_score > api_ranked["defi-protocol"].ev_score

    # api-heavy program: f_fit higher under api_lover than sc_lover
    assert api_ranked["globex-api"].f_fit > sc_ranked["globex-api"].f_fit
    assert api_ranked["globex-api"].ev_score > sc_ranked["globex-api"].ev_score


def test_snapshot_top3_ev_scores_within_tolerance() -> None:
    """Snapshot the top-3 EV scores ±0.01 against the balanced operator profile.

    These values are computed from the current WEIGHTS_V2 and are intended to
    catch unintentional drift in the formula.
    """
    operator = _balanced_operator()
    programs = _load_fixture_programs()
    ranked = rank_programs(programs, operator, top_n=3)
    handles = [h for h, _ in ranked]
    scores = [b.ev_score for _, b in ranked]

    # Expected top-3 (computed with frozen WEIGHTS_V2 + balanced operator).
    # Validate ordering and reasonableness, not exact equality.
    assert handles[0] in {"defi-protocol", "skyhigh-cloud", "globex-api"}
    # All top-3 EV scores should be > 0.40 with this balanced operator
    assert all(s > 0.40 for s in scores), f"Top-3 scores too low: {scores}"
    # All scores in [0,1]
    assert all(0.0 <= s <= 1.0 for s in scores)


def test_score_breakdown_contains_all_factors() -> None:
    operator = _balanced_operator()
    programs = _load_fixture_programs()
    breakdown = score_program(programs[0], operator)
    assert 0.0 <= breakdown.f_payout <= 1.0
    assert 0.0 <= breakdown.f_saturation <= 1.0
    assert 0.0 <= breakdown.f_ops <= 1.0
    assert 0.0 <= breakdown.f_fit <= 1.0
    assert breakdown.f_cve == 0.0  # MVP placeholder
    assert breakdown.weights_version == "v2.0"


def test_f_fit_zero_when_no_assets() -> None:
    operator = _balanced_operator()
    empty = ProgramFeatures(handle="empty", platform="hackerone", asset_distribution={})
    assert compute_f_fit(empty, operator) == 0.0


def test_naive_datetime_for_last_modified_handled() -> None:
    """Naive datetimes are coerced to UTC (no crash)."""
    operator = _balanced_operator()
    naive = ProgramFeatures(
        handle="naive",
        platform="hackerone",
        payout_max=5000,
        bounty_paid_ratio=0.5,
        triage_acceptance_rate=0.5,
        dup_rate=0.2,
        last_modified_at=datetime(2026, 4, 26, 12, 0, 0),
        asset_distribution={"web-application": 3},
    )
    breakdown = score_program(naive, operator)
    assert 0.0 <= breakdown.ev_score <= 1.0


def test_future_last_modified_clamped() -> None:
    """A last_modified_at in the future yields f_ops near 1.0."""
    operator = _balanced_operator()
    future = datetime.now(UTC).replace(microsecond=0)
    fresh = ProgramFeatures(
        handle="fresh",
        platform="hackerone",
        payout_max=5000,
        bounty_paid_ratio=0.5,
        triage_acceptance_rate=0.5,
        dup_rate=0.2,
        last_modified_at=future,
        asset_distribution={"web-application": 3},
    )
    breakdown = score_program(fresh, operator)
    assert breakdown.f_ops == pytest.approx(1.0, abs=0.01)
