"""Program ranking bounded context — EV scoring engine.

Public API:
    Value objects   : OperatorProfile, ProgramFeatures, ScoreBreakdown
    Domain math     : compute_scope_freshness, compute_kev_freshness,
                      compute_freshness, cve_opportunity_score
    Services        : score_program, rank_programs,
                      compute_f_payout, compute_f_saturation, compute_f_ops,
                      compute_f_fit, compute_f_cve
    Constants       : WEIGHTS_V2, WEIGHTS_VERSION, ASSET_TYPE_WEIGHTS,
                      LAMBDA_SCOPE, MU_KEV
    Repository      : write_ev_score, get_latest_ev, ev_score_history, metadata

(research/02-routing-ev.md §EV Formula + Weights)
"""

from __future__ import annotations

from .domain.freshness import (
    compute_freshness,
    compute_kev_freshness,
    compute_scope_freshness,
    cve_opportunity_score,
)
from .repositories.ev_history_repository import (
    ev_score_history,
    get_latest_ev,
    metadata,
    write_ev_score,
)
from .services.scoring_service import (
    breakdown_to_db_row,
    compute_f_cve,
    compute_f_fit,
    compute_f_ops,
    compute_f_payout,
    compute_f_saturation,
    rank_programs,
    score_program,
)
from .value_objects.operator import OperatorProfile
from .value_objects.program_features import ProgramFeatures
from .value_objects.score import ScoreBreakdown
from .value_objects.weights import (
    ASSET_TYPE_WEIGHTS,
    LAMBDA_SCOPE,
    MU_KEV,
    WEIGHTS_V2,
    WEIGHTS_VERSION,
)

__all__ = [
    "ASSET_TYPE_WEIGHTS",
    "LAMBDA_SCOPE",
    "MU_KEV",
    "WEIGHTS_V2",
    "WEIGHTS_VERSION",
    "OperatorProfile",
    "ProgramFeatures",
    "ScoreBreakdown",
    "breakdown_to_db_row",
    "compute_f_cve",
    "compute_f_fit",
    "compute_f_ops",
    "compute_f_payout",
    "compute_f_saturation",
    "compute_freshness",
    "compute_kev_freshness",
    "compute_scope_freshness",
    "cve_opportunity_score",
    "ev_score_history",
    "get_latest_ev",
    "metadata",
    "rank_programs",
    "score_program",
    "write_ev_score",
]
