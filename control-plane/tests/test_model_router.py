"""Tests for model routing cost optimization matrix.

Covers the full routing matrix (16 task types x 4 cost tiers), model
selection with overrides, cost estimation, and RoutingConfig loading.
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
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
from control_plane.core.routing.routing_config import (
    ENV_PREFIX,
    RoutingConfig,
    load_routing_config,
)


# ---------------------------------------------------------------------------
# 1. CostTier enum and tier ordering
# ---------------------------------------------------------------------------


def test_cost_tier_values():
    """CostTier enum has exactly four members with expected string values."""
    assert CostTier.FRONTIER == "frontier"
    assert CostTier.MID == "mid"
    assert CostTier.FAST == "fast"
    assert CostTier.MINIMAL == "minimal"


def test_cost_tier_ordering_by_cost():
    """CostTier values reflect a descending cost ordering."""
    tiers = list(CostTier)
    assert tiers == [CostTier.FRONTIER, CostTier.MID, CostTier.FAST, CostTier.MINIMAL]


# ---------------------------------------------------------------------------
# 2. ModelDefinition is a frozen (immutable) ValueObject
# ---------------------------------------------------------------------------


def test_model_definition_immutable():
    """ModelDefinition instances are frozen and hashable."""
    model = ModelDefinition(
        model_id="test/model",
        cost_tier=CostTier.FAST,
        cost_per_mtok_input=1.0,
        cost_per_mtok_output=5.0,
    )
    with pytest.raises(Exception):
        model.model_id = "other/model"


def test_model_definition_hashable():
    """ModelDefinition can be used in sets and as dict keys."""
    m1 = ModelDefinition(
        model_id="anthropic/claude-opus-4-7",
        cost_tier=CostTier.FRONTIER,
        cost_per_mtok_input=5.0,
        cost_per_mtok_output=25.0,
    )
    m2 = ModelDefinition(
        model_id="anthropic/claude-opus-4-7",
        cost_tier=CostTier.FRONTIER,
        cost_per_mtok_input=5.0,
        cost_per_mtok_output=25.0,
    )
    assert hash(m1) == hash(m2)
    assert m1 == m2


# ---------------------------------------------------------------------------
# 3. Tier-level model registries are populated
# ---------------------------------------------------------------------------


def test_frontier_models_populated():
    assert "opus" in FRONTIER_MODELS
    assert "mythos" in FRONTIER_MODELS
    assert FRONTIER_MODELS["opus"].cost_tier == CostTier.FRONTIER
    assert FRONTIER_MODELS["mythos"].cost_tier == CostTier.FRONTIER


def test_mid_models_populated():
    assert "sonnet" in MID_MODELS
    assert "gemini-pro" in MID_MODELS
    assert MID_MODELS["sonnet"].cost_tier == CostTier.MID
    assert MID_MODELS["gemini-pro"].cost_tier == CostTier.MID


def test_fast_models_populated():
    assert "haiku" in FAST_MODELS
    assert "deepseek-r1" in FAST_MODELS
    assert "mistral-small" in FAST_MODELS
    for m in FAST_MODELS.values():
        assert m.cost_tier == CostTier.FAST


def test_minimal_models_populated():
    assert "deepseek-flash" in MINIMAL_MODELS
    assert "qwen-coder" in MINIMAL_MODELS
    assert "venice-dolphin" in MINIMAL_MODELS
    for m in MINIMAL_MODELS.values():
        assert m.cost_tier == CostTier.MINIMAL


# ---------------------------------------------------------------------------
# 4. get_model_by_tier returns primary model for each tier
# ---------------------------------------------------------------------------


def test_get_model_by_tier_frontier():
    m = get_model_by_tier(CostTier.FRONTIER)
    assert m.model_id == "anthropic/claude-opus-4-7"


def test_get_model_by_tier_mid():
    m = get_model_by_tier(CostTier.MID)
    assert m.model_id == "anthropic/claude-sonnet-4-6"


def test_get_model_by_tier_fast():
    m = get_model_by_tier(CostTier.FAST)
    assert m.model_id == "anthropic/claude-haiku-4-5"


def test_get_model_by_tier_minimal():
    m = get_model_by_tier(CostTier.MINIMAL)
    assert m.model_id == "deepseek/deepseek-v4-flash"


def test_get_model_by_tier_invalid():
    with pytest.raises(ValueError, match="Invalid cost tier"):
        get_model_by_tier("unknown")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 5. ModelRouter — get_model_for_task covers all 16 task types
# ---------------------------------------------------------------------------


def test_router_returns_correct_model_for_each_task():
    """Each of the 16 task types maps to the expected model ID."""
    router = ModelRouter()
    expected = {
        # MINIMAL tier
        "bulk_triage_dedup": "deepseek/deepseek-v4-flash",
        "exploit_code_gen": "qwen/qwen3-coder",
        "uncensored_payload_synth": "venice/dolphin",
        # FAST tier
        "subdomain_enum_triage": "anthropic/claude-haiku-4-5",
        "cvss_scoring": "deepseek/deepseek-r1-0528",
        "json_extraction": "mistralai/mistral-small-3.2-24b",
        "daily_intel_brief": "anthropic/claude-haiku-4-5",
        # MID tier
        "recon_synthesis": "google/gemini-3.1-pro",
        "vuln_hypothesis_gen": "anthropic/claude-sonnet-4-6",
        "report_prose": "anthropic/claude-sonnet-4-6",
        "tech_fingerprint": "google/gemini-3.1-pro",
        "llm_probe_gen": "anthropic/claude-sonnet-4-6",
        # FRONTIER tier
        "deep_multi_step_reasoning": "anthropic/claude-opus-4-7",
        "mythos_hypothesis": "anthropic/claude-mythos-preview",
        "exploit_validation": "anthropic/claude-opus-4-7",
        "cloud_iam_chain": "anthropic/claude-opus-4-7",
    }
    for task_type, model_id in expected.items():
        assert router.get_model_for_task(task_type) == model_id, (
            f"{task_type} should route to {model_id}"
        )


def test_router_all_16_task_types_registered():
    router = ModelRouter()
    task_types = router.get_all_task_types()
    assert len(task_types) == 16
    assert sorted(task_types) == task_types  # already sorted


def test_router_unknown_task_raises():
    router = ModelRouter()
    with pytest.raises(ValueError, match="Unknown task type"):
        router.get_model_for_task("nonexistent_task")


# ---------------------------------------------------------------------------
# 6. ModelRouter — overrides
# ---------------------------------------------------------------------------


def test_router_override_changes_model():
    router = ModelRouter(overrides={"bulk_triage_dedup": "anthropic/claude-opus-4-7"})
    assert router.get_model_for_task("bulk_triage_dedup") == "anthropic/claude-opus-4-7"


def test_router_override_does_not_affect_other_tasks():
    router = ModelRouter(overrides={"bulk_triage_dedup": "anthropic/claude-opus-4-7"})
    assert router.get_model_for_task("deep_multi_step_reasoning") == "anthropic/claude-opus-4-7"


def test_router_empty_overrides_is_noop():
    router = ModelRouter(overrides={})
    assert router.get_model_for_task("cvss_scoring") == "deepseek/deepseek-r1-0528"


def test_router_none_overrides_is_noop():
    router = ModelRouter(overrides=None)
    assert router.get_model_for_task("json_extraction") == "mistralai/mistral-small-3.2-24b"


def test_router_override_unknown_task_still_raises():
    """Override keys bypass the routing matrix; unknown tasks without overrides raise."""
    router = ModelRouter(overrides={"some_random_task": "foo/model"})
    # Override task works
    assert router.get_model_for_task("some_random_task") == "foo/model"
    # Tasks not in overrides AND not in matrix raise
    with pytest.raises(ValueError, match="Unknown task type"):
        router.get_model_for_task("totally_unknown")


# ---------------------------------------------------------------------------
# 7. ModelRouter — get_model_definition
# ---------------------------------------------------------------------------


def test_get_model_definition_returns_full_definition():
    router = ModelRouter()
    defn = router.get_model_definition("exploit_validation")
    assert isinstance(defn, ModelDefinition)
    assert defn.model_id == "anthropic/claude-opus-4-7"
    assert defn.cost_tier == CostTier.FRONTIER
    assert defn.cost_per_mtok_input == 5.00
    assert defn.cost_per_mtok_output == 25.00
    assert defn.fallback_model_id == "openai/gpt-5.5-pro"


def test_get_model_definition_unknown_task_raises():
    router = ModelRouter()
    with pytest.raises(ValueError, match="Unknown task type"):
        router.get_model_definition("nope_task")


# ---------------------------------------------------------------------------
# 8. ModelRouter — estimate_cost
# ---------------------------------------------------------------------------


def test_estimate_cost_zero_tokens():
    router = ModelRouter()
    cost = router.estimate_cost("deep_multi_step_reasoning", 0, 0)
    assert cost == 0.0


def test_estimate_cost_opus_frontier():
    """Opus: $5/Mtok input, $25/Mtok output. 1M in + 500K out."""
    router = ModelRouter()
    cost = router.estimate_cost("exploit_validation", 1_000_000, 500_000)
    expected = (1_000_000 / 1_000_000) * 5.00 + (500_000 / 1_000_000) * 25.00
    assert cost == pytest.approx(expected)


def test_estimate_cost_free_model():
    """Qwen coder is free: $0/Mtok."""
    router = ModelRouter()
    cost = router.estimate_cost("exploit_code_gen", 10_000_000, 5_000_000)
    assert cost == 0.0


def test_estimate_cost_fast_tier():
    """Haiku: $1/Mtok input, $5/Mtok output."""
    router = ModelRouter()
    cost = router.estimate_cost("cvss_scoring", 500_000, 200_000)
    expected = (500_000 / 1_000_000) * 0.50 + (200_000 / 1_000_000) * 2.15
    assert cost == pytest.approx(expected)


def test_estimate_cost_unknown_task_raises():
    router = ModelRouter()
    with pytest.raises(ValueError, match="Unknown task type"):
        router.estimate_cost("nonexistent", 1000, 500)


# ---------------------------------------------------------------------------
# 9. RoutingConfig — environment variable loading
# ---------------------------------------------------------------------------


def test_routing_config_no_overrides():
    config = RoutingConfig(env_overrides={})
    assert config.get_overrides() == {}
    assert not config.has_overrides()


def test_routing_config_loads_valid_override():
    env = {ENV_PREFIX + "recon_synthesis": "anthropic/claude-opus-4-7"}
    config = RoutingConfig(env_overrides=env)
    assert config.get_overrides() == {"recon_synthesis": "anthropic/claude-opus-4-7"}
    assert config.has_overrides()


def test_routing_config_multiple_overrides():
    env = {
        ENV_PREFIX + "recon_synthesis": "anthropic/claude-opus-4-7",
        ENV_PREFIX + "cvss_scoring": "anthropic/claude-opus-4-7",
    }
    config = RoutingConfig(env_overrides=env)
    overrides = config.get_overrides()
    assert len(overrides) == 2
    assert overrides["recon_synthesis"] == "anthropic/claude-opus-4-7"
    assert overrides["cvss_scoring"] == "anthropic/claude-opus-4-7"


def test_rejects_invalid_task_type():
    env = {ENV_PREFIX + "fake_task": "some/model"}
    with pytest.raises(ValueError, match="Invalid override"):
        RoutingConfig(env_overrides=env)


def test_rejects_empty_model_id():
    env = {ENV_PREFIX + "recon_synthesis": "  "}
    with pytest.raises(ValueError, match="cannot be empty"):
        RoutingConfig(env_overrides=env)


def test_rejects_missing_model_value():
    env = {ENV_PREFIX + "recon_synthesis": ""}
    with pytest.raises(ValueError, match="cannot be empty"):
        RoutingConfig(env_overrides=env)


def test_ignores_non_override_env_vars():
    env = {
        "HOME": "/root",
        "PATH": "/usr/bin",
        ENV_PREFIX + "report_prose": "openai/gpt-5.4",
    }
    config = RoutingConfig(env_overrides=env)
    assert config.get_overrides() == {"report_prose": "openai/gpt-5.4"}


# ---------------------------------------------------------------------------
# 10. RoutingConfig — query helpers
# ---------------------------------------------------------------------------


def test_get_override_for_task_existing():
    env = {ENV_PREFIX + "report_prose": "openai/gpt-5.4"}
    config = RoutingConfig(env_overrides=env)
    assert config.get_override_for_task("report_prose") == "openai/gpt-5.4"


def test_get_override_for_task_missing():
    config = RoutingConfig(env_overrides={})
    assert config.get_override_for_task("report_prose") is None


def test_to_dict_serialization():
    env = {
        ENV_PREFIX + "recon_synthesis": "anthropic/claude-opus-4-7",
        ENV_PREFIX + "cvss_scoring": "anthropic/claude-opus-4-7",
    }
    config = RoutingConfig(env_overrides=env)
    d = config.to_dict()
    assert d["count"] == 2
    assert sorted(d["task_types"]) == ["cvss_scoring", "recon_synthesis"]
    assert d["overrides"]["recon_synthesis"] == "anthropic/claude-opus-4-7"


# ---------------------------------------------------------------------------
# 11. RoutingConfig — load_routing_config factory
# ---------------------------------------------------------------------------


def test_load_routing_config_factory():
    env = {ENV_PREFIX + "bulk_triage_dedup": "anthropic/claude-opus-4-7"}
    config = load_routing_config(env_overrides=env)
    assert isinstance(config, RoutingConfig)
    assert config.get_override_for_task("bulk_triage_dedup") == "anthropic/claude-opus-4-7"


# ---------------------------------------------------------------------------
# 12. RoutingConfig — strips whitespace from model IDs
# ---------------------------------------------------------------------------


def test_override_strips_whitespace():
    env = {ENV_PREFIX + "exploit_validation": "  anthropic/claude-opus-4-7  "}
    config = RoutingConfig(env_overrides=env)
    assert config.get_override_for_task("exploit_validation") == "anthropic/claude-opus-4-7"


# ---------------------------------------------------------------------------
# 13. RoutingConfig — get_overrides returns a copy
# ---------------------------------------------------------------------------


def test_get_overrides_returns_copy():
    env = {ENV_PREFIX + "report_prose": "anthropic/claude-sonnet-4-6"}
    config = RoutingConfig(env_overrides=env)
    overrides = config.get_overrides()
    overrides["report_prose"] = "modified"
    # Internal state should not be affected
    assert config.get_override_for_task("report_prose") == "anthropic/claude-sonnet-4-6"


# ---------------------------------------------------------------------------
# 14. ENV_PREFIX constant
# ---------------------------------------------------------------------------


def test_env_prefix_value():
    assert ENV_PREFIX == "MODEL_OVERRIDE_"


# ---------------------------------------------------------------------------
# 15. Integration: ModelRouter initialized from RoutingConfig
# ---------------------------------------------------------------------------


def test_router_with_routing_config_overrides():
    """End-to-end: load config from env, pass to router, verify override applied."""
    env = {ENV_PREFIX + "exploit_validation": "deepseek/deepseek-v4-flash"}
    config = RoutingConfig(env_overrides=env)
    router = ModelRouter(overrides=config.get_overrides())

    # Override should switch exploit_validation from opus to deepseek-flash
    assert router.get_model_for_task("exploit_validation") == "deepseek/deepseek-v4-flash"
    # Other tasks should remain unchanged
    assert router.get_model_for_task("cloud_iam_chain") == "anthropic/claude-opus-4-7"


# ---------------------------------------------------------------------------
# 16. Tier coverage: every tier has tasks routed to it
# ---------------------------------------------------------------------------


def test_covered_task_types_by_tier():
    """Verify that all 4 cost tiers have at least one task type assigned."""
    router = ModelRouter()
    tier_counts: dict[CostTier, int] = {}
    for task_type in router.get_all_task_types():
        defn = router.get_model_definition(task_type)
        tier_counts[defn.cost_tier] = tier_counts.get(defn.cost_tier, 0) + 1

    assert CostTier.FRONTIER in tier_counts
    assert CostTier.MID in tier_counts
    assert CostTier.FAST in tier_counts
    assert CostTier.MINIMAL in tier_counts
    assert sum(tier_counts.values()) == 16


# ---------------------------------------------------------------------------
# 17. Fallback models are set for frontier and mid tiers
# ---------------------------------------------------------------------------


def test_frontier_models_have_fallbacks():
    for m in FRONTIER_MODELS.values():
        assert m.fallback_model_id is not None


def test_mid_models_have_fallbacks():
    for m in MID_MODELS.values():
        assert m.fallback_model_id is not None


# ---------------------------------------------------------------------------
# 18. Free models have zero cost
# ---------------------------------------------------------------------------


def test_free_models_zero_cost():
    """Qwen coder and Venice dolphin are free."""
    assert MINIMAL_MODELS["qwen-coder"].cost_per_mtok_input == 0.0
    assert MINIMAL_MODELS["qwen-coder"].cost_per_mtok_output == 0.0
    assert MINIMAL_MODELS["venice-dolphin"].cost_per_mtok_input == 0.0
    assert MINIMAL_MODELS["venice-dolphin"].cost_per_mtok_output == 0.0


# ---------------------------------------------------------------------------
# 19. Model router ROUTING_MATRIX is a class variable
# ---------------------------------------------------------------------------


def test_routing_matrix_is_classvar():
    """ROUTING_MATRIX is shared across instances and not duplicated."""
    r1 = ModelRouter()
    r2 = ModelRouter(overrides={"bulk_triage_dedup": "foo/bar"})
    assert r1.ROUTING_MATRIX is r2.ROUTING_MATRIX


# ---------------------------------------------------------------------------
# 20. get_all_task_types returns sorted list
# ---------------------------------------------------------------------------


def test_get_all_task_types_sorted():
    router = ModelRouter()
    types = router.get_all_task_types()
    assert types == sorted(types)
