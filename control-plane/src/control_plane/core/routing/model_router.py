"""Model router mapping task types to optimal models.

Maps 16 task types to specific models based on complexity and cost optimization.
Based on routing matrix from docs/research/02-routing-ev.md.
"""

from __future__ import annotations

from typing import ClassVar

from control_plane.core.routing.cost_tiers import (
    FAST_MODELS,
    FRONTIER_MODELS,
    MID_MODELS,
    MINIMAL_MODELS,
    ModelDefinition,
)


class ModelRouter:
    """Routes task types to optimal models based on cost/capability trade-offs.

    The routing matrix optimizes for:
    - Sub-$5 cost per confirmed bug
    - Sub-$0.20 cost per target
    - Quality gates on validation and hypothesis generation
    - Free/minimal cost for bulk processing and exploit generation
    """

    # Task type -> model mapping from routing-ev.md
    ROUTING_MATRIX: ClassVar[dict[str, ModelDefinition]] = {
        # MINIMAL tier: Bulk processing, free models
        "bulk_triage_dedup": MINIMAL_MODELS["deepseek-flash"],
        "exploit_code_gen": MINIMAL_MODELS["qwen-coder"],
        "uncensored_payload_synth": MINIMAL_MODELS["venice-dolphin"],
        # FAST tier: Quick classification, scoring
        "subdomain_enum_triage": FAST_MODELS["haiku"],
        "cvss_scoring": FAST_MODELS["deepseek-r1"],
        "json_extraction": FAST_MODELS["mistral-small"],
        "daily_intel_brief": FAST_MODELS["haiku"],
        # MID tier: Hypothesis gen, reports, synthesis
        "recon_synthesis": MID_MODELS["gemini-pro"],
        "vuln_hypothesis_gen": MID_MODELS["sonnet"],
        "report_prose": MID_MODELS["sonnet"],
        "tech_fingerprint": MID_MODELS["gemini-pro"],
        "llm_probe_gen": MID_MODELS["sonnet"],
        # FRONTIER tier: Multi-step reasoning, validation
        "deep_multi_step_reasoning": FRONTIER_MODELS["opus"],
        "mythos_hypothesis": FRONTIER_MODELS["mythos"],
        "exploit_validation": FRONTIER_MODELS["opus"],
        "cloud_iam_chain": FRONTIER_MODELS["opus"],
    }

    def __init__(self, overrides: dict[str, str] | None = None):
        """Initialize router with optional task-specific overrides.

        Args:
            overrides: Optional dict mapping task types to model IDs for operator overrides
        """
        self._overrides = overrides or {}

    def get_model_for_task(self, task_type: str) -> str:
        """Get the optimal model ID for a given task type.

        Args:
            task_type: Task type identifier (e.g., "bulk_triage_dedup")

        Returns:
            OpenRouter model ID (e.g., "deepseek/deepseek-v4-flash")

        Raises:
            ValueError: If task_type is not in routing matrix
        """
        # Check for operator override first
        if task_type in self._overrides:
            return self._overrides[task_type]

        # Look up in routing matrix
        if task_type not in self.ROUTING_MATRIX:
            raise ValueError(
                f"Unknown task type: {task_type}. "
                f"Valid types: {', '.join(sorted(self.ROUTING_MATRIX.keys()))}"
            )

        return self.ROUTING_MATRIX[task_type].model_id

    def get_model_definition(self, task_type: str) -> ModelDefinition:
        """Get the full model definition for a task type.

        Args:
            task_type: Task type identifier

        Returns:
            ModelDefinition with pricing, fallback, context window

        Raises:
            ValueError: If task_type is not in routing matrix
        """
        if task_type not in self.ROUTING_MATRIX:
            raise ValueError(
                f"Unknown task type: {task_type}. "
                f"Valid types: {', '.join(sorted(self.ROUTING_MATRIX.keys()))}"
            )

        return self.ROUTING_MATRIX[task_type]

    def get_all_task_types(self) -> list[str]:
        """Get list of all supported task types.

        Returns:
            Sorted list of task type identifiers
        """
        return sorted(self.ROUTING_MATRIX.keys())

    def estimate_cost(
        self, task_type: str, input_tokens: int, output_tokens: int
    ) -> float:
        """Estimate cost for a task given token counts.

        Args:
            task_type: Task type identifier
            input_tokens: Estimated input token count
            output_tokens: Estimated output token count

        Returns:
            Estimated cost in USD

        Raises:
            ValueError: If task_type is not in routing matrix
        """
        model_def = self.get_model_definition(task_type)
        cost_input = (input_tokens / 1_000_000) * model_def.cost_per_mtok_input
        cost_output = (output_tokens / 1_000_000) * model_def.cost_per_mtok_output
        return cost_input + cost_output
