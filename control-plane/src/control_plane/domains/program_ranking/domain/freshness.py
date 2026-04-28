"""Freshness decay + CVE opportunity score (research/02 §Freshness decay, §CVE opportunity score).

Pure functions — no I/O, no DB. All math via stdlib `math.exp`.
"""

from __future__ import annotations

import math

from ..value_objects.weights import LAMBDA_SCOPE, MU_KEV


def compute_scope_freshness(delta_hours: float) -> float:
    """Scope freshness decay: f_fresh(Δt) = exp(-LAMBDA_SCOPE * Δt).

    Reference points (research/02): 0.97 @ 48h, 0.89 @ 1wk, 0.63 @ 1mo (720h).
    """
    if delta_hours < 0:
        return 1.0
    return math.exp(-LAMBDA_SCOPE * delta_hours)


def compute_kev_freshness(delta_hours: float) -> float:
    """KEV freshness decay: f_kev(Δt) = exp(-MU_KEV * Δt).

    Halves in ~72h (KEV publication staleness penalty).
    """
    if delta_hours < 0:
        return 1.0
    return math.exp(-MU_KEV * delta_hours)


def compute_freshness(delta_hours: float) -> float:
    """Default freshness = scope freshness (research/02 §Freshness decay)."""
    return compute_scope_freshness(delta_hours)


def cve_opportunity_score(
    epss: float,
    kev_age_hours: float,
    has_nuclei_template: bool,
    cvss_exploitability: float = 0.5,
) -> float:
    """CVE opportunity score (research/02 verbatim).

    template_factor : 0.25 if a public Nuclei template already exists (saturated),
                      else 1.00.
    freshness       : exp(-MU * kev_age_hours)
    exploit_prob    : max(epss, cvss_exploitability * 0.3)
    return          : min(exploit_prob * freshness * template_factor, 1.0)
    """
    template_factor = 0.25 if has_nuclei_template else 1.00
    freshness = math.exp(-MU_KEV * max(kev_age_hours, 0.0))
    exploit_prob = max(epss, cvss_exploitability * 0.3)
    return min(exploit_prob * freshness * template_factor, 1.0)
