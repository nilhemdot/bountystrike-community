"""EV scoring engine — pure functions over Pydantic-typed inputs.

Aggregate normalized score:
    S        = w1*f_payout + w2*f_sat + w3*f_ops + w4*f_fit
    EV_score = min(S * (1 + 0.20 * f_cve), 1.0)

(research/02 §EV Formula + Weights)
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from .freshness import compute_scope_freshness
from .weights import ASSET_TYPE_WEIGHTS, WEIGHTS_V2, WEIGHTS_VERSION

# Reference payout cap for normalizing f_payout. $50k = full score.
PAYOUT_NORM_CAP_USD: float = 50_000.0


class OperatorProfile(BaseModel):
    """Operator skill + budget profile feeding f_fit."""

    skill_vector: dict[str, float] = Field(default_factory=dict)
    time_budget_hours: float = 40.0
    cost_budget_usd: float = 50.0
    asset_type_pref: dict[str, float] = Field(default_factory=dict)


class ProgramFeatures(BaseModel):
    """Materialized program signals consumed by score_program()."""

    handle: str
    platform: str
    payout_min: float = 0.0
    payout_max: float = 0.0
    bounty_paid_ratio: float = 0.0
    triage_acceptance_rate: float = 0.0
    dup_rate: float = 0.0
    last_modified_at: datetime | None = None
    asset_distribution: dict[str, int] = Field(default_factory=dict)


class ScoreBreakdown(BaseModel):
    """Per-program scoring decomposition (also persisted to ev_score_history)."""

    ev_score: float
    f_payout: float
    f_saturation: float
    f_ops: float
    f_fit: float
    f_cve: float
    weights_version: str = WEIGHTS_VERSION


def _clamp01(x: float) -> float:
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x


def compute_f_payout(features: ProgramFeatures) -> float:
    """Normalized [0,1] from payout_max * bounty_paid_ratio.

    Anchored against PAYOUT_NORM_CAP_USD ($50k). Programs that pay more get full
    credit; programs that rarely pay (low bounty_paid_ratio) are discounted.
    """
    weighted_payout = max(features.payout_max, 0.0) * _clamp01(features.bounty_paid_ratio)
    return _clamp01(weighted_payout / PAYOUT_NORM_CAP_USD)


def compute_f_saturation(features: ProgramFeatures) -> float:
    """(1 - dup_rate) * triage_acceptance_rate ∈ [0,1].

    Higher dup_rate or lower triage_acceptance → more saturated → less attractive.
    """
    inv_dup = 1.0 - _clamp01(features.dup_rate)
    triage = _clamp01(features.triage_acceptance_rate)
    return _clamp01(inv_dup * triage)


def compute_f_ops(features: ProgramFeatures) -> float:
    """Operational freshness proxy from last_modified_at decay.

    Older scope updates → lower f_ops (program less actively triaging).
    """
    if features.last_modified_at is None:
        return 0.5
    now = datetime.now(UTC)
    last = features.last_modified_at
    if last.tzinfo is None:
        last = last.replace(tzinfo=UTC)
    delta_hours = max((now - last).total_seconds() / 3600.0, 0.0)
    return _clamp01(compute_scope_freshness(delta_hours))


def compute_f_fit(features: ProgramFeatures, operator: OperatorProfile) -> float:
    """Dot product asset_distribution × asset_type_pref × ASSET_TYPE_WEIGHTS, normalized.

    For each asset_type in the program: count * pref * type_weight, summed
    weighted-average style (divide by total count). Anchor against the global
    ceiling (max ASSET_TYPE_WEIGHTS = smart_contract 1.40) so high-value asset
    types (smart_contract, cloud_config) outrank low-value ones (vdp, executable)
    even at the same operator preference.
    """
    if not features.asset_distribution:
        return 0.0

    weighted_sum = 0.0
    total_count = 0
    for asset_type, count in features.asset_distribution.items():
        if count <= 0:
            continue
        type_weight = ASSET_TYPE_WEIGHTS.get(asset_type, 1.0)
        pref = operator.asset_type_pref.get(asset_type, 0.5)
        weighted_sum += count * pref * type_weight
        total_count += count

    if total_count <= 0:
        return 0.0

    # Per-asset average weighted score, normalized against the table's max weight (1.40).
    avg = weighted_sum / total_count
    ceiling = max(ASSET_TYPE_WEIGHTS.values())  # 1.40 (smart_contract)
    return _clamp01(avg / ceiling)


def compute_f_cve(features: ProgramFeatures) -> float:
    """Placeholder MVP — CVE bonus disabled until KEV/EPSS feed wired in.

    Phase 1+ will wire CVE-specific signals (active exploitation against the
    program's tech-fingerprint surface). Returns 0.0 for now so the (1 + 0.20*f_cve)
    multiplier collapses to identity.
    """
    _ = features  # explicit unused — placeholder by design
    return 0.0


def score_program(
    features: ProgramFeatures,
    operator: OperatorProfile,
    weights: dict[str, float] | None = None,
) -> ScoreBreakdown:
    """Compute full EV breakdown for a single program.

    S        = w_payout*f_payout + w_sat*f_sat + w_ops*f_ops + w_fit*f_fit
    EV_score = min(S * (1 + 0.20 * f_cve), 1.0)
    """
    w = weights or WEIGHTS_V2
    f_payout = compute_f_payout(features)
    f_saturation = compute_f_saturation(features)
    f_ops = compute_f_ops(features)
    f_fit = compute_f_fit(features, operator)
    f_cve = compute_f_cve(features)

    s = (
        w["payout"] * f_payout
        + w["saturation"] * f_saturation
        + w["ops"] * f_ops
        + w["fit"] * f_fit
    )
    cve_bonus_weight = w.get("cve_bonus", 0.20)
    ev_score = min(s * (1.0 + cve_bonus_weight * f_cve), 1.0)

    return ScoreBreakdown(
        ev_score=round(ev_score, 4),
        f_payout=round(f_payout, 4),
        f_saturation=round(f_saturation, 4),
        f_ops=round(f_ops, 4),
        f_fit=round(f_fit, 4),
        f_cve=round(f_cve, 4),
        weights_version=WEIGHTS_VERSION,
    )


def rank_programs(
    programs: list[ProgramFeatures],
    operator: OperatorProfile,
    top_n: int = 25,
    weights: dict[str, float] | None = None,
) -> list[tuple[str, ScoreBreakdown]]:
    """Score every program and return (handle, breakdown) tuples sorted desc by ev_score."""
    scored: list[tuple[str, ScoreBreakdown]] = [
        (p.handle, score_program(p, operator, weights=weights)) for p in programs
    ]
    scored.sort(key=lambda row: row[1].ev_score, reverse=True)
    return scored[:top_n]


def breakdown_to_db_row(
    breakdown: ScoreBreakdown,
    program_handle: str,
    operator_id: str | None,
) -> dict[str, Any]:
    """Render a breakdown as a dict matching `ev_score_history` columns."""
    return {
        "program_handle": program_handle,
        "ev_score": breakdown.ev_score,
        "f_payout": breakdown.f_payout,
        "f_saturation": breakdown.f_saturation,
        "f_ops": breakdown.f_ops,
        "f_fit": breakdown.f_fit,
        "f_cve": breakdown.f_cve,
        "weights_version": breakdown.weights_version,
        "computed_for_operator": operator_id,
    }
