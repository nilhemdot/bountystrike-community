"""EV scoring weights and constants (research/02 §EV Formula + Weights).

WEIGHTS_V2     -- relative importance of payout/saturation/ops/fit/cve_bonus
ASSET_TYPE_WEIGHTS -- per-asset multipliers (smart_contract through vdp)
LAMBDA_SCOPE   -- scope freshness decay rate (per hour)
MU_KEV         -- KEV freshness decay rate (per hour)
"""

from __future__ import annotations

from typing import Final

# v2.0 weights — payout 0.35 | saturation 0.25 | ops 0.25 | fit 0.15 | cve_bonus +20%
WEIGHTS_V2: Final[dict[str, float]] = {
    "payout": 0.35,
    "saturation": 0.25,
    "ops": 0.25,
    "fit": 0.15,
    "cve_bonus": 0.20,
}

WEIGHTS_VERSION: Final[str] = "v2.0"

# Asset-type multipliers (research/02 §Asset-type weights table)
ASSET_TYPE_WEIGHTS: Final[dict[str, float]] = {
    "smart_contract": 1.40,
    "cloud_config": 1.30,
    "ai_model": 1.25,
    "api": 1.15,
    "web-application": 1.00,
    "cidr": 0.90,
    "android": 0.85,
    "ios": 0.80,
    "executable": 0.70,
    "vdp": 0.10,
}

# Freshness decay constants
LAMBDA_SCOPE: Final[float] = 0.00065  # exp(-0.00065*Δt) → ~0.97 @ 48h, 0.63 @ 720h
MU_KEV: Final[float] = 0.00963  # exp(-0.00963*Δt) → halves in ~72h
