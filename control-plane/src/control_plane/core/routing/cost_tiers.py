# SPDX-License-Identifier: AGPL-3.0-or-later

"""Cost tier definitions for model routing.

Four-tier system maps task types to models by cost/capability:
- FRONTIER: Most expensive, highest capability (Opus, Mythos)
- MID: Balanced cost/quality (Sonnet, Gemini Pro)
- FAST: Quick/cheap but capable (Haiku, DeepSeek)
- MINIMAL: Free or ultra-cheap (DeepSeek Flash, Qwen, Venice)
"""

from __future__ import annotations

from enum import Enum
from typing import ClassVar

from control_plane.core.shared.value_object import ValueObject


class CostTier(str, Enum):
    """Cost tier for model selection.

    Ordered from most to least expensive. Used to map task types
    to appropriate model capabilities while respecting budget constraints.
    """

    FRONTIER = "frontier"  # $5-25/Mtok — multi-step reasoning, validation
    MID = "mid"  # $2-3/Mtok — hypothesis gen, report prose
    FAST = "fast"  # $0.50-1.00/Mtok — triage, scoring
    MINIMAL = "minimal"  # $0.00-0.14/Mtok — bulk processing, free models


class ModelDefinition(ValueObject):
    """Immutable model configuration with pricing and fallback.

    Attributes:
        model_id: OpenRouter model identifier (e.g., "anthropic/claude-opus-4-7")
        cost_tier: Which tier this model belongs to
        cost_per_mtok_input: Cost per million input tokens (USD)
        cost_per_mtok_output: Cost per million output tokens (USD)
        fallback_model_id: Alternative model if primary unavailable
        context_window: Maximum context length in tokens
    """

    model_id: str
    cost_tier: CostTier
    cost_per_mtok_input: float
    cost_per_mtok_output: float
    fallback_model_id: str | None = None
    context_window: int = 200_000


# Model definitions by tier — canonical mapping from routing-ev.md
FRONTIER_MODELS: ClassVar[dict[str, ModelDefinition]] = {
    "opus": ModelDefinition(
        model_id="anthropic/claude-opus-4-7",
        cost_tier=CostTier.FRONTIER,
        cost_per_mtok_input=5.00,
        cost_per_mtok_output=25.00,
        fallback_model_id="openai/gpt-5.5-pro",
        context_window=200_000,
    ),
    "mythos": ModelDefinition(
        model_id="anthropic/claude-mythos-preview",
        cost_tier=CostTier.FRONTIER,
        cost_per_mtok_input=25.00,
        cost_per_mtok_output=125.00,
        fallback_model_id="anthropic/claude-opus-4-7",
        context_window=200_000,
    ),
}

MID_MODELS: ClassVar[dict[str, ModelDefinition]] = {
    "sonnet": ModelDefinition(
        model_id="anthropic/claude-sonnet-4-6",
        cost_tier=CostTier.MID,
        cost_per_mtok_input=3.00,
        cost_per_mtok_output=15.00,
        fallback_model_id="openai/gpt-5.4",
        context_window=200_000,
    ),
    "gemini-pro": ModelDefinition(
        model_id="google/gemini-3.1-pro",
        cost_tier=CostTier.MID,
        cost_per_mtok_input=2.00,
        cost_per_mtok_output=12.00,
        fallback_model_id="anthropic/claude-haiku-4-5",
        context_window=2_000_000,
    ),
}

FAST_MODELS: ClassVar[dict[str, ModelDefinition]] = {
    "haiku": ModelDefinition(
        model_id="anthropic/claude-haiku-4-5",
        cost_tier=CostTier.FAST,
        cost_per_mtok_input=1.00,
        cost_per_mtok_output=5.00,
        fallback_model_id="deepseek/deepseek-v4-flash",
        context_window=200_000,
    ),
    "deepseek-r1": ModelDefinition(
        model_id="deepseek/deepseek-r1-0528",
        cost_tier=CostTier.FAST,
        cost_per_mtok_input=0.50,
        cost_per_mtok_output=2.15,
        fallback_model_id="deepseek/deepseek-v4-flash",
        context_window=128_000,
    ),
    "mistral-small": ModelDefinition(
        model_id="mistralai/mistral-small-3.2-24b",
        cost_tier=CostTier.FAST,
        cost_per_mtok_input=0.09,
        cost_per_mtok_output=0.25,
        fallback_model_id="deepseek/deepseek-v4-flash",
        context_window=128_000,
    ),
}

MINIMAL_MODELS: ClassVar[dict[str, ModelDefinition]] = {
    "deepseek-flash": ModelDefinition(
        model_id="deepseek/deepseek-v4-flash",
        cost_tier=CostTier.MINIMAL,
        cost_per_mtok_input=0.14,
        cost_per_mtok_output=0.28,
        fallback_model_id="qwen/qwen3-coder-30b",
        context_window=128_000,
    ),
    "qwen-coder": ModelDefinition(
        model_id="qwen/qwen3-coder",
        cost_tier=CostTier.MINIMAL,
        cost_per_mtok_input=0.00,
        cost_per_mtok_output=0.00,
        fallback_model_id="mistralai/devstral",
        context_window=1_000_000,
    ),
    "venice-dolphin": ModelDefinition(
        model_id="venice/dolphin",
        cost_tier=CostTier.MINIMAL,
        cost_per_mtok_input=0.00,
        cost_per_mtok_output=0.00,
        fallback_model_id="cognitivecomputations/hermes-4-70b",
        context_window=128_000,
    ),
}


def get_model_by_tier(tier: CostTier, task_type: str | None = None) -> ModelDefinition:
    """Get the primary model for a given cost tier.

    Args:
        tier: Cost tier to select from
        task_type: Optional task type hint for specialized routing within tier

    Returns:
        ModelDefinition for the tier's primary model

    Raises:
        ValueError: If tier is invalid
    """
    match tier:
        case CostTier.FRONTIER:
            return FRONTIER_MODELS["opus"]
        case CostTier.MID:
            return MID_MODELS["sonnet"]
        case CostTier.FAST:
            return FAST_MODELS["haiku"]
        case CostTier.MINIMAL:
            return MINIMAL_MODELS["deepseek-flash"]
        case _:
            raise ValueError(f"Invalid cost tier: {tier}")
