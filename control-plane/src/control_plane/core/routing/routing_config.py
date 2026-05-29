# SPDX-License-Identifier: AGPL-3.0-or-later

"""Routing configuration with operator-specific model overrides.

Per spec §6: Operators can override model selection for specific task types
via environment variables (``MODEL_OVERRIDE_<task_type>=<model_id>``) or
configuration objects. Overrides are validated against the routing matrix's
known task types but accept any model ID for operator flexibility.

The :class:`RoutingConfig` class loads overrides from environment variables
and provides a validated dict suitable for :class:`ModelRouter` initialization.
"""

from __future__ import annotations

import os
from typing import Any

from control_plane.core.routing.model_router import ModelRouter

# Environment variable prefix for model overrides
ENV_PREFIX = "MODEL_OVERRIDE_"


class RoutingConfig:
    """Loads and validates operator-specific model routing overrides.

    Supports environment variable-based overrides using the pattern:
    ``MODEL_OVERRIDE_<task_type>=<model_id>``

    Example:
        >>> os.environ["MODEL_OVERRIDE_recon_synthesis"] = "anthropic/claude-opus-4-7"
        >>> config = RoutingConfig()
        >>> config.get_overrides()
        {'recon_synthesis': 'anthropic/claude-opus-4-7'}
    """

    def __init__(self, env_overrides: dict[str, str] | None = None) -> None:
        """Initialize routing config with optional environment overrides.

        Args:
            env_overrides: Optional dict of environment variables to use instead
                          of os.environ (useful for testing)
        """
        self._env = env_overrides if env_overrides is not None else dict(os.environ)
        self._overrides: dict[str, str] = {}
        self._load_overrides()

    def _load_overrides(self) -> None:
        """Load model overrides from environment variables.

        Scans for variables matching MODEL_OVERRIDE_<task_type> pattern
        and validates task types against the routing matrix.
        """
        # Get all valid task types from routing matrix
        valid_task_types = set(ModelRouter.ROUTING_MATRIX.keys())

        for key, value in self._env.items():
            if not key.startswith(ENV_PREFIX):
                continue

            # Extract task type from env var name
            task_type = key[len(ENV_PREFIX) :]

            # Validate task type exists in routing matrix
            if task_type not in valid_task_types:
                raise ValueError(
                    f"Invalid override: {key}={value}. "
                    f"Task type '{task_type}' not in routing matrix. "
                    f"Valid types: {', '.join(sorted(valid_task_types))}"
                )

            # Validate model_id is non-empty
            if not value or not value.strip():
                raise ValueError(
                    f"Invalid override: {key}={value}. "
                    f"Model ID cannot be empty"
                )

            self._overrides[task_type] = value.strip()

    def get_overrides(self) -> dict[str, str]:
        """Get the loaded operator overrides.

        Returns:
            Dict mapping task types to model IDs for overridden tasks
        """
        return self._overrides.copy()

    def get_override_for_task(self, task_type: str) -> str | None:
        """Get the override model ID for a specific task type.

        Args:
            task_type: Task type identifier

        Returns:
            Override model ID if set, None otherwise
        """
        return self._overrides.get(task_type)

    def has_overrides(self) -> bool:
        """Check if any overrides are configured.

        Returns:
            True if at least one override is set
        """
        return len(self._overrides) > 0

    def to_dict(self) -> dict[str, Any]:
        """Export config as a dict for serialization.

        Returns:
            Dict with override mappings and metadata
        """
        return {
            "overrides": self._overrides.copy(),
            "count": len(self._overrides),
            "task_types": sorted(self._overrides.keys()),
        }


def load_routing_config(env_overrides: dict[str, str] | None = None) -> RoutingConfig:
    """Factory function to load routing configuration.

    Args:
        env_overrides: Optional environment override dict (for testing)

    Returns:
        Initialized RoutingConfig with loaded overrides

    Raises:
        ValueError: If any override references invalid task type or model ID
    """
    return RoutingConfig(env_overrides=env_overrides)


__all__ = [
    "ENV_PREFIX",
    "RoutingConfig",
    "load_routing_config",
]
