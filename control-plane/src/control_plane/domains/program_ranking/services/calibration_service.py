"""EV calibration service — Spearman ρ between predicted EV rank and actual find-rate.

Phase 3 build-plan §10.5 calibration activity #1:
    "After alpha hunters run 50+ scans, compare EV-ranked top-10 programs
     against actual find-rate. Adjust weights if top-EV programs are not
     producing better outcomes."

Phase 3 exit criterion: ρ ≥ 0.60 (Spearman rank correlation).

Strategy:
    1. Pull HuntOutcome rows from the repository (one per scan_job).
    2. Spearman ρ between (ev_rank ascending) and (find_rate descending).
       Negative correlation between rank and find_rate = positive
       correlation between predicted-good-program and actual-finds.
       We negate so the headline number is positive when calibration is
       working.
    3. If |ρ| < 0.60 AND n ≥ 50, emit per-component weight recommendations
       so the operator can update WEIGHTS_V2 in weights.py and bump to v2.1.

Pure functions: no I/O, no DB. Caller passes in a list[HuntOutcome] from
hunt_outcome_repository.get_outcomes_for_calibration.
"""

from __future__ import annotations

from typing import Any, cast

from scipy.stats import spearmanr

from ..value_objects.hunt_outcome import HuntOutcome
from ..value_objects.weights import WEIGHTS_V2

_MIN_N_FOR_CORRELATION = 3
_MIN_N_FOR_WEIGHT_REC = 50
_TARGET_RHO = 0.60


def compute_spearman_correlation(
    outcomes: list[HuntOutcome],
) -> tuple[float, float]:
    """Spearman ρ between ev_rank (asc) and find_rate (desc, negated).

    Returns (rho, p_value). Rho is positive when low ev_rank (top of EV
    list) correlates with high find_rate (good actual outcomes) — i.e.
    when the EV model is working as designed.

    Edge cases:
      * n < 3            → (0.0, 1.0)  (scipy needs ≥ 3 to compute)
      * all-equal ranks  → (0.0, 1.0)  (no variance)
      * NaN from scipy   → (0.0, 1.0)  (constant input)
    """
    if len(outcomes) < _MIN_N_FOR_CORRELATION:
        return (0.0, 1.0)

    ranks = [o.ev_rank for o in outcomes if o.ev_rank is not None]
    rates = [o.find_rate for o in outcomes if o.ev_rank is not None]

    if len(ranks) < _MIN_N_FOR_CORRELATION:
        return (0.0, 1.0)
    if len(set(ranks)) == 1 or len(set(rates)) == 1:
        return (0.0, 1.0)

    # spearmanr returns a SignificanceResult bunch in scipy ≥ 1.10. The
    # bunch is tuple-iterable, but Pyright's stubs type the iter result
    # opaquely, so we cast through Any to extract the two floats.
    result = cast(Any, spearmanr(ranks, rates))
    rho = float(result.statistic)
    p_value = float(result.pvalue)

    if rho != rho:  # NaN check (NaN != NaN by IEEE-754)
        return (0.0, 1.0)

    # Negate: ranks ascend (1=best) but find_rate descends-by-rank when
    # calibration works. Negation makes the headline number positive in
    # the well-calibrated case.
    return (-rho, p_value)


def calibration_report(outcomes: list[HuntOutcome]) -> dict[str, Any]:
    """Produce a Phase 3 calibration verdict + optional weight diff.

    Output shape::

        {
          "rho": float,                 # Spearman ρ, sign-corrected
          "p_value": float,
          "passes": bool,               # ρ ≥ 0.60
          "n_outcomes": int,
          "n_unique_programs": int,
          "weight_recommendations": dict | None,
        }

    weight_recommendations is non-None only when ρ < 0.60 AND we have
    ≥ 50 outcomes (otherwise the recommendation is statistically
    unreliable). The operator must review and apply the diff manually
    by editing weights.py — this service never mutates global state.
    """
    rho, p_value = compute_spearman_correlation(outcomes)
    n = len(outcomes)
    n_unique = len({o.program_handle for o in outcomes})
    passes = rho >= _TARGET_RHO

    recs: dict[str, float] | None = None
    if not passes and n >= _MIN_N_FOR_WEIGHT_REC:
        recs = _suggest_weight_adjustments(outcomes)

    return {
        "rho": rho,
        "p_value": p_value,
        "passes": passes,
        "n_outcomes": n,
        "n_unique_programs": n_unique,
        "weight_recommendations": recs,
    }


def _suggest_weight_adjustments(outcomes: list[HuntOutcome]) -> dict[str, float]:
    """Naive weight adjustment heuristic.

    Without per-component f_* values inside HuntOutcome (we'd need a
    fatter join into ev_score_history), we can't run a real per-component
    Spearman. As a conservative recommendation, we return WEIGHTS_V2
    unchanged with a flag — humans must inspect ev_score_history rows
    for the underperforming programs and adjust manually.

    Future: extend HuntOutcome to carry the f_* breakdown at scan time
    and compute per-component ρ here. Out of scope for Phase 3 W11-14.
    """
    _ = outcomes  # explicit unused — placeholder by design (see compute_f_cve)
    return dict(WEIGHTS_V2)
