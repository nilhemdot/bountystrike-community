"""OpenFeature client wrapper with a fail-closed tier gate.

Default provider is in-memory (offline) so solo/CI need no Unleash server. When
UNLEASH_URL is set, the custom UnleashProvider is used.

`is_enabled` ALWAYS fails closed: any error returns the supplied default and logs.
The `tier-enterprise` gate defaults to False. See the package docstring: this flag
is a config/rollout gate, NOT an authorization boundary.
"""

from __future__ import annotations

import os

import structlog
from openfeature import api
from openfeature.contrib.provider.in_memory import InMemoryFlag, InMemoryProvider
from openfeature.evaluation_context import EvaluationContext

from control_plane.core.flags.provider import UnleashProvider

log = structlog.get_logger(__name__)

# Community/solo defaults — tier-enterprise MUST be False here. In-memory
# enterprise-true is dev-only and must never ship in the community edition.
_COMMUNITY_DEFAULT_FLAGS: dict[str, bool] = {
    "tier-enterprise": False,
}


def _in_memory_provider(flags: dict[str, bool] | None = None) -> InMemoryProvider:
    source = flags if flags is not None else _COMMUNITY_DEFAULT_FLAGS
    return InMemoryProvider(
        {key: InMemoryFlag(str(val), {"on": True, "off": False}) for key, val in source.items()}
    )


def configure_flags(in_memory_flags: dict[str, bool] | None = None) -> None:
    """Wire the OpenFeature provider.

    UnleashProvider when UNLEASH_URL is set (token from UNLEASH_TOKEN); otherwise
    the in-memory community-default provider. Falls back to in-memory if Unleash
    construction fails (fail closed — never leave the platform ungated).
    """
    unleash_url = os.environ.get("UNLEASH_URL")
    if unleash_url:
        try:
            provider = UnleashProvider(
                unleash_url=unleash_url,
                app_name=os.environ.get("UNLEASH_APP_NAME", "bountystrike"),
                token=os.environ.get("UNLEASH_TOKEN", ""),
                allow_insecure=os.environ.get("UNLEASH_ALLOW_INSECURE") == "1",
            )
            api.set_provider(provider)
            return
        except Exception as exc:
            log.warning("flags.unleash_init_failed_fallback_inmemory", error=str(exc))

    api.set_provider(_in_memory_provider(in_memory_flags))


def get_client():
    """Return the configured OpenFeature client."""
    return api.get_client()


def is_enabled(
    flag_key: str,
    default: bool = False,
    context: dict | None = None,
) -> bool:
    """Evaluate a boolean flag, FAIL CLOSED.

    Returns `default` (False for tier gates) on any error. Never raises into the
    caller. NOT an authorization check — see the package docstring.
    """
    try:
        eval_ctx = EvaluationContext(attributes=context) if context else None
        return get_client().get_boolean_value(flag_key, default, eval_ctx)
    except Exception as exc:
        log.warning("flags.is_enabled_failed_closed", flag=flag_key, error=str(exc))
        return default
