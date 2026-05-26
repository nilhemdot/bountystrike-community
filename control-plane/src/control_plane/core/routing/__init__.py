"""Model routing system for cost-optimized task execution.

Maps 16 task types to 4 cost tiers (frontier/mid/fast/minimal) to balance
quality and cost. Enables sub-$5 cost per bug and sub-$0.20 per target.
"""

from control_plane.core.routing.cost_tiers import (
    FAST_MODELS,
    FRONTIER_MODELS,
    MID_MODELS,
    MINIMAL_MODELS,
    CostTier,
    ModelDefinition,
    get_model_by_tier,
)
from control_plane.core.routing.model_router import ModelRouter

__all__ = [
    "CostTier",
    "ModelDefinition",
    "ModelRouter",
    "get_model_by_tier",
    "FRONTIER_MODELS",
    "MID_MODELS",
    "FAST_MODELS",
    "MINIMAL_MODELS",
]
