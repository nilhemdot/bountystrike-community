"""EV scoring engine (research/02-routing-ev.md §EV Formula + Weights).

Public surface — re-exports only. All math lives in scoring.py + freshness.py;
DB I/O lives exclusively in writer.py.
"""

from __future__ import annotations

from .freshness import (
    compute_kev_freshness,
    compute_scope_freshness,
    cve_opportunity_score,
)
from .scoring import (
    OperatorProfile,
    ProgramFeatures,
    ScoreBreakdown,
    compute_f_cve,
    compute_f_fit,
    compute_f_ops,
    compute_f_payout,
    compute_f_saturation,
    rank_programs,
    score_program,
)
from .weights import (
    ASSET_TYPE_WEIGHTS,
    LAMBDA_SCOPE,
    MU_KEV,
    WEIGHTS_V2,
    WEIGHTS_VERSION,
)


def compute_freshness(delta_hours: float) -> float:
    """Default freshness = scope freshness (research/02 §Freshness decay)."""
    return compute_scope_freshness(delta_hours)


__all__ = [
    "ASSET_TYPE_WEIGHTS",
    "LAMBDA_SCOPE",
    "MU_KEV",
    "WEIGHTS_V2",
    "WEIGHTS_VERSION",
    "OperatorProfile",
    "ProgramFeatures",
    "ScoreBreakdown",
    "compute_f_cve",
    "compute_f_fit",
    "compute_f_ops",
    "compute_f_payout",
    "compute_f_saturation",
    "compute_freshness",
    "compute_kev_freshness",
    "compute_scope_freshness",
    "cve_opportunity_score",
    "rank_programs",
    "score_program",
]
