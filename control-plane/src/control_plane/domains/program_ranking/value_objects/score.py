"""ScoreBreakdown value object — per-program scoring decomposition.

Persisted (one column per field) to ev_score_history via the repository layer.
"""

from __future__ import annotations

from control_plane.core.shared import ValueObject

from .weights import WEIGHTS_VERSION


class ScoreBreakdown(ValueObject):
    """Per-program scoring decomposition (also persisted to ev_score_history).

    Frozen value object. ev_score is the post-CVE-bonus aggregate; the f_*
    fields are the pre-aggregation factor scores. All ∈ [0, 1] by construction
    (clamped inside the scoring service); we keep the type as float here so
    repository reads (which may surface DB rounding artefacts) remain robust.
    """

    ev_score: float
    f_payout: float
    f_saturation: float
    f_ops: float
    f_fit: float
    f_cve: float
    weights_version: str = WEIGHTS_VERSION
