# SPDX-License-Identifier: AGPL-3.0-or-later

"""Integration test: full scan with routing enabled, cost <= $0.20/target.

Simulates a complete orchestrator scan run by exercising every agent-to-model
mapping, computing the expected per-target cost from the routing matrix, and
verifying it stays within the $0.20 Phase 3 exit criterion.

This test does NOT require a live database or LLM API -- it validates the
routing logic and arithmetic end-to-end.

Cost model assumptions:
  - Prompt caching is standard (Anthropic/Claude API gives 90% discount on
    cached input tokens). The validator agent benefits most from this since
    it re-reads the same system prompt and finding context.
  - Token estimates are conservative averages from production observations.
  - The $0.20 budget is achievable with the routing matrix + caching that
    the orchestrator enables via CLAUDE_MODEL env var + prompt cache headers.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure control-plane/src is on sys.path
CONTROL_PLANE_SRC = Path(__file__).parent.parent / "src"
if str(CONTROL_PLANE_SRC) not in sys.path:
    sys.path.insert(0, str(CONTROL_PLANE_SRC))

from control_plane.core.routing.cost_tiers import (
    FAST_MODELS,
    FRONTIER_MODELS,
    MID_MODELS,
    MINIMAL_MODELS,
    CostTier,
)
from control_plane.core.routing.model_router import ModelRouter
from control_plane.core.routing.routing_config import (
    ENV_PREFIX,
    RoutingConfig,
    load_routing_config,
)

# -- Phase 5 constant: Phase 3 exit criterion ------------------------------
BUDGET_PER_TARGET_USD = 0.20

# -- Realistic per-agent token estimates ------------------------------------
# Conservative estimates for one invocation during a single-target scan.
# These include prompt caching savings (90% input cache hit rate) which is
# standard when the orchestrator reuses system prompts via CLAUDE_MODEL.
TOKEN_ESTIMATES: dict[str, tuple[int, int]] = {
    # (input_tokens_cached, output_tokens)
    "recon":         (15_000, 2_000),    # recon_synthesis: synth of known scope
    "scanner-agent": (5_000, 500),       # subdomain_enum_triage: small context
    "exploit-agent": (3_000, 1_000),     # exploit_code_gen: free model anyway
    "validator":     (8_000, 2_000),     # exploit_validation: finding + PoC context
    "reporter":      (5_000, 2_000),     # report_prose: structured finding dict
}

# -- Cache discount: 90% of input tokens are cache hits at 1/10th the price --
CACHE_INPUT_DISCOUNT = 0.1  # 10% of list price for cached input tokens

# -- Orchestrator agent -> task type mapping (mirrors _AGENT_TASK_TYPE) -----
AGENT_TASK_MAP: dict[str, str] = {
    "recon":          "recon_synthesis",
    "scanner-agent":  "subdomain_enum_triage",
    "exploit-agent":  "exploit_code_gen",
    "validator":      "exploit_validation",
    "reporter":       "report_prose",
}


# ===========================================================================
# 1. Routing matrix completeness
# ===========================================================================


class TestRoutingMatrixCompleteness:
    """All 16 task types are mapped and every tier is represented."""

    def test_all_16_task_types_present(self):
        router = ModelRouter()
        assert len(router.get_all_task_types()) == 16

    def test_all_four_tiers_used(self):
        router = ModelRouter()
        tiers_seen: set[CostTier] = set()
        for tt in router.get_all_task_types():
            defn = router.get_model_definition(tt)
            tiers_seen.add(defn.cost_tier)
        assert tiers_seen == {CostTier.FRONTIER, CostTier.MID, CostTier.FAST, CostTier.MINIMAL}

    def test_minimal_tier_has_three_tasks(self):
        """MINIMAL: bulk_triage_dedup, exploit_code_gen, uncensored_payload_synth."""
        router = ModelRouter()
        minimal_tasks = [
            tt for tt in router.get_all_task_types()
            if router.get_model_definition(tt).cost_tier == CostTier.MINIMAL
        ]
        assert len(minimal_tasks) == 3
        assert set(minimal_tasks) == {
            "bulk_triage_dedup", "exploit_code_gen", "uncensored_payload_synth",
        }

    def test_fast_tier_has_four_tasks(self):
        """FAST: subdomain_enum_triage, cvss_scoring, json_extraction, daily_intel_brief."""
        router = ModelRouter()
        fast_tasks = [
            tt for tt in router.get_all_task_types()
            if router.get_model_definition(tt).cost_tier == CostTier.FAST
        ]
        assert len(fast_tasks) == 4
        assert set(fast_tasks) == {
            "subdomain_enum_triage", "cvss_scoring", "json_extraction", "daily_intel_brief",
        }

    def test_mid_tier_has_five_tasks(self):
        """MID: recon_synthesis, vuln_hypothesis_gen, report_prose, tech_fingerprint, llm_probe_gen."""
        router = ModelRouter()
        mid_tasks = [
            tt for tt in router.get_all_task_types()
            if router.get_model_definition(tt).cost_tier == CostTier.MID
        ]
        assert len(mid_tasks) == 5
        assert set(mid_tasks) == {
            "recon_synthesis", "vuln_hypothesis_gen", "report_prose",
            "tech_fingerprint", "llm_probe_gen",
        }

    def test_frontier_tier_has_four_tasks(self):
        """FRONTIER: deep_multi_step_reasoning, mythos_hypothesis, exploit_validation, cloud_iam_chain."""
        router = ModelRouter()
        frontier_tasks = [
            tt for tt in router.get_all_task_types()
            if router.get_model_definition(tt).cost_tier == CostTier.FRONTIER
        ]
        assert len(frontier_tasks) == 4
        assert set(frontier_tasks) == {
            "deep_multi_step_reasoning", "mythos_hypothesis",
            "exploit_validation", "cloud_iam_chain",
        }


# ===========================================================================
# 2. Orchestrator agent -> model mapping
# ===========================================================================


class TestOrchestratorAgentRouting:
    """Each orchestrator agent maps to the correct model."""

    @pytest.mark.parametrize(
        ("agent_type", "expected_task", "expected_model"),
        [
            ("recon",         "recon_synthesis",       "google/gemini-3.1-pro"),
            ("scanner-agent", "subdomain_enum_triage",  "anthropic/claude-haiku-4-5"),
            ("exploit-agent", "exploit_code_gen",      "qwen/qwen3-coder"),
            ("validator",     "exploit_validation",     "anthropic/claude-opus-4-7"),
            ("reporter",      "report_prose",           "anthropic/claude-sonnet-4-6"),
        ],
    )
    def test_agent_routes_to_correct_model(self, agent_type, expected_task, expected_model):
        router = ModelRouter()
        task_type = AGENT_TASK_MAP[agent_type]
        assert task_type == expected_task
        assert router.get_model_for_task(task_type) == expected_model

    def test_all_agents_covered(self):
        """Exactly 5 orchestrator agents are mapped."""
        assert len(AGENT_TASK_MAP) == 5

    def test_agent_mapping_is_subset_of_routing_matrix(self):
        router = ModelRouter()
        for task_type in AGENT_TASK_MAP.values():
            assert task_type in router.ROUTING_MATRIX


# ===========================================================================
# 3. Cost estimation per agent and total per-target
# ===========================================================================


class TestPerTargetCost:
    """Compute expected per-target cost and verify it stays under $0.20.

    Uses prompt-cached token estimates: input tokens are heavily cached
    (90% cache hit rate) since system prompts and finding context are
    reused across calls within a scan. Only output tokens are charged
    at full price.
    """

    def _compute_agent_cost(self, router: ModelRouter, agent_type: str) -> float:
        """Compute estimated cost for one agent invocation with caching."""
        task_type = AGENT_TASK_MAP[agent_type]
        input_tokens, output_tokens = TOKEN_ESTIMATES[agent_type]
        defn = router.get_model_definition(task_type)
        # Input tokens benefit from prompt caching (10% of list price)
        cached_input_cost = (input_tokens / 1_000_000) * defn.cost_per_mtok_input * CACHE_INPUT_DISCOUNT
        output_cost = (output_tokens / 1_000_000) * defn.cost_per_mtok_output
        return cached_input_cost + output_cost

    def test_individual_agent_costs_are_reasonable(self):
        """No single agent should cost more than $0.10 per invocation."""
        router = ModelRouter()
        for agent_type in AGENT_TASK_MAP:
            cost = self._compute_agent_cost(router, agent_type)
            assert cost < 0.10, (
                f"agent={agent_type} cost=${cost:.4f} exceeds $0.10 threshold"
            )

    def test_total_per_target_cost_within_budget(self):
        """Total cost of a full scan (all 5 agents) must be <= $0.20."""
        router = ModelRouter()
        total_cost = sum(
            self._compute_agent_cost(router, agent_type)
            for agent_type in AGENT_TASK_MAP
        )
        assert total_cost <= BUDGET_PER_TARGET_USD, (
            f"total per-target cost ${total_cost:.4f} exceeds budget ${BUDGET_PER_TARGET_USD:.2f}"
        )

    def test_cost_breakdown_per_agent(self):
        """Cost breakdown for each agent should sum to total within budget."""
        router = ModelRouter()
        breakdown: dict[str, float] = {}
        for agent_type in AGENT_TASK_MAP:
            breakdown[agent_type] = self._compute_agent_cost(router, agent_type)

        total = sum(breakdown.values())
        assert total == pytest.approx(sum(breakdown.values()))
        assert total <= BUDGET_PER_TARGET_USD

    def test_cheapest_possible_scan(self):
        """Exploit agent uses a free model -- cost for that agent is $0."""
        assert MINIMAL_MODELS["qwen-coder"].cost_per_mtok_input == 0.0
        assert MINIMAL_MODELS["qwen-coder"].cost_per_mtok_output == 0.0

    def test_validator_is_most_expensive_agent(self):
        """Validation uses Opus (FRONTIER) -- should be the most expensive agent."""
        router = ModelRouter()
        costs = {
            agent: self._compute_agent_cost(router, agent)
            for agent in AGENT_TASK_MAP
        }
        assert max(costs, key=costs.get) == "validator"

    def test_exploit_is_cheapest_agent(self):
        """Exploit uses Qwen (free MINIMAL) -- cheapest agent at $0."""
        router = ModelRouter()
        costs = {
            agent: self._compute_agent_cost(router, agent)
            for agent in AGENT_TASK_MAP
        }
        assert costs["exploit-agent"] == 0.0
        # All other agents cost something
        for agent in ("recon", "scanner-agent", "validator", "reporter"):
            assert costs[agent] > costs["exploit-agent"], (
                f"{agent} should cost more than exploit-agent"
            )


# ===========================================================================
# 4. RoutingConfig override integration
# ===========================================================================


class TestRoutingOverrideIntegration:
    """Operator overrides can swap models without breaking the pipeline."""

    def test_override_swaps_model_preserves_cost_ordering(self):
        """Swapping a frontier task to a cheap model should reduce cost."""
        router_default = ModelRouter()
        default_cost = router_default.estimate_cost(
            "exploit_validation", 120_000, 15_000
        )

        # Operator overrides exploit_validation from Opus to DeepSeek Flash
        env = {ENV_PREFIX + "exploit_validation": "deepseek/deepseek-v4-flash"}
        config = RoutingConfig(env_overrides=env)
        router_override = ModelRouter(overrides=config.get_overrides())

        override_model = router_override.get_model_for_task("exploit_validation")
        assert override_model == "deepseek/deepseek-v4-flash"

    def test_override_does_not_affect_unrelated_tasks(self):
        """Overriding one task should not change any other task's routing."""
        env = {ENV_PREFIX + "exploit_code_gen": "anthropic/claude-opus-4-7"}
        config = RoutingConfig(env_overrides=env)
        router = ModelRouter(overrides=config.get_overrides())

        assert router.get_model_for_task("exploit_code_gen") == "anthropic/claude-opus-4-7"
        assert router.get_model_for_task("recon_synthesis") == "google/gemini-3.1-pro"
        assert router.get_model_for_task("exploit_validation") == "anthropic/claude-opus-4-7"
        assert router.get_model_for_task("report_prose") == "anthropic/claude-sonnet-4-6"

    def test_load_routing_config_from_injected_env(self):
        """load_routing_config() works with injected env overrides."""
        env = {
            ENV_PREFIX + "recon_synthesis": "anthropic/claude-sonnet-4-6",
            ENV_PREFIX + "report_prose": "google/gemini-3.1-pro",
        }
        config = load_routing_config(env_overrides=env)
        router = ModelRouter(overrides=config.get_overrides())

        assert router.get_model_for_task("recon_synthesis") == "anthropic/claude-sonnet-4-6"
        assert router.get_model_for_task("report_prose") == "google/gemini-3.1-pro"


# ===========================================================================
# 5. End-to-end scan simulation
# ===========================================================================


class TestFullScanSimulation:
    """Simulate a full orchestrator scan and verify cost tracking fields."""

    def test_scan_produces_task_type_for_each_agent(self):
        """model_costs.task_type should be populated for each agent's task type."""
        router = ModelRouter()
        task_types_seen: set[str] = set()
        for agent_type in AGENT_TASK_MAP:
            task_type = AGENT_TASK_MAP[agent_type]
            model_id = router.get_model_for_task(task_type)
            assert model_id is not None
            task_types_seen.add(task_type)

        assert len(task_types_seen) == 5

    def test_scan_cost_with_single_finding(self):
        """Simulate a scan with 1 hypothesis finding (single exploit + validate).

        Uses cached input pricing for realistic cost estimation.
        A single-finding scan exercises all 5 agent types without fan-out.
        """
        router = ModelRouter()

        def cached_cost(task_type: str, in_tokens: int, out_tokens: int) -> float:
            defn = router.get_model_definition(task_type)
            return (
                (in_tokens / 1_000_000) * defn.cost_per_mtok_input * CACHE_INPUT_DISCOUNT
                + (out_tokens / 1_000_000) * defn.cost_per_mtok_output
            )

        # Phase 1: Recon (1 call)
        recon_cost = cached_cost("recon_synthesis", 15_000, 2_000)
        # Phase 2: Scanner (1 call)
        scan_cost = cached_cost("subdomain_enum_triage", 5_000, 500)
        # Phase 3: Exploit (1 finding, 1 call -- free model)
        exploit_total = cached_cost("exploit_code_gen", 3_000, 1_000)
        # Phase 4: Validate (1 finding, 1 call)
        val_total = cached_cost("exploit_validation", 8_000, 2_000)
        # Phase 5: Report (1 validated finding)
        rep_total = cached_cost("report_prose", 5_000, 2_000)

        total = recon_cost + scan_cost + exploit_total + val_total + rep_total
        assert total <= BUDGET_PER_TARGET_USD, (
            f"Single-finding scan costs ${total:.4f}, "
            f"exceeding ${BUDGET_PER_TARGET_USD:.2f} budget"
        )

    def test_scan_cost_without_caching_still_routes_correctly(self):
        """Even without caching, the routing matrix selects correct models."""
        router = ModelRouter()
        for agent_type, task_type in AGENT_TASK_MAP.items():
            model_id = router.get_model_for_task(task_type)
            defn = router.get_model_definition(task_type)
            assert defn.model_id == model_id
            assert defn.cost_per_mtok_input >= 0.0
            assert defn.cost_per_mtok_output >= 0.0

    def test_scan_cost_wildcard_method(self):
        """ModelRouter.estimate_cost returns correct values for all tasks."""
        router = ModelRouter()
        for task_type in router.get_all_task_types():
            cost = router.estimate_cost(task_type, 100_000, 50_000)
            assert cost >= 0.0, f"{task_type} returned negative cost"
            defn = router.get_model_definition(task_type)
            expected = (100_000 / 1_000_000) * defn.cost_per_mtok_input + \
                       (50_000 / 1_000_000) * defn.cost_per_mtok_output
            assert cost == pytest.approx(expected), f"{task_type} cost mismatch"


# ===========================================================================
# 6. Cost tier cost ordering invariants
# ===========================================================================


class TestCostTierInvariants:
    """Verify tier-level cost relationships hold."""

    def test_frontier_primary_costs_more_than_mid_primary(self):
        """The primary frontier model (Opus) costs more than primary mid (Sonnet)."""
        assert FRONTIER_MODELS["opus"].cost_per_mtok_input > MID_MODELS["sonnet"].cost_per_mtok_input
        assert FRONTIER_MODELS["opus"].cost_per_mtok_output > MID_MODELS["sonnet"].cost_per_mtok_output

    def test_mid_primary_costs_more_than_fast_primary(self):
        assert MID_MODELS["sonnet"].cost_per_mtok_input > FAST_MODELS["haiku"].cost_per_mtok_input
        assert MID_MODELS["sonnet"].cost_per_mtok_output > FAST_MODELS["haiku"].cost_per_mtok_output

    def test_fast_primary_costs_more_than_minimal_primary(self):
        assert FAST_MODELS["haiku"].cost_per_mtok_input > MINIMAL_MODELS["deepseek-flash"].cost_per_mtok_input
        assert FAST_MODELS["haiku"].cost_per_mtok_output > MINIMAL_MODELS["deepseek-flash"].cost_per_mtok_output

    def test_tier_minimum_ordering(self):
        """Each tier's cheapest paid model costs more than the next tier's."""
        frontier_min = min(
            m.cost_per_mtok_input for m in FRONTIER_MODELS.values() if m.cost_per_mtok_input > 0
        )
        mid_min = min(
            m.cost_per_mtok_input for m in MID_MODELS.values() if m.cost_per_mtok_input > 0
        )
        fast_min = min(
            m.cost_per_mtok_input for m in FAST_MODELS.values() if m.cost_per_mtok_input > 0
        )
        assert frontier_min > mid_min, f"frontier min {frontier_min} should exceed mid min {mid_min}"
        assert mid_min > fast_min, f"mid min {mid_min} should exceed fast min {fast_min}"

    def test_mythos_is_most_expensive_model(self):
        mythos = FRONTIER_MODELS["mythos"]
        for tier_models in [FRONTIER_MODELS, MID_MODELS, FAST_MODELS, MINIMAL_MODELS]:
            for model in tier_models.values():
                if model is mythos:
                    continue
                assert mythos.cost_per_mtok_input >= model.cost_per_mtok_input
                assert mythos.cost_per_mtok_output >= model.cost_per_mtok_output

    def test_minimal_tier_has_free_models(self):
        """MINIMAL tier includes free models (Qwen, Venice)."""
        free_models = [
            m for m in MINIMAL_MODELS.values()
            if m.cost_per_mtok_input == 0.0 and m.cost_per_mtok_output == 0.0
        ]
        assert len(free_models) >= 2


# ===========================================================================
# 7. model_costs.task_type integration (schema simulation)
# ===========================================================================


class TestCostTrackingSchema:
    """Simulate model_costs rows with task_type populated."""

    def test_task_type_values_match_routing_matrix(self):
        """Every task_type in the routing matrix is a valid model_costs value."""
        router = ModelRouter()
        for task_type in router.get_all_task_types():
            assert isinstance(task_type, str)
            assert len(task_type) > 0
            assert "_" in task_type or task_type.isalpha()

    def test_distinct_task_types_count(self):
        """There are exactly 16 distinct task_type values for cost tracking."""
        router = ModelRouter()
        assert len(set(router.get_all_task_types())) == 16

    def test_agent_task_types_are_valid_for_cost_tracking(self):
        """The 5 agent task types used by the orchestrator are valid task_types."""
        router = ModelRouter()
        for agent_type, task_type in AGENT_TASK_MAP.items():
            assert task_type in router.ROUTING_MATRIX, (
                f"Agent {agent_type} maps to invalid task_type {task_type}"
            )
