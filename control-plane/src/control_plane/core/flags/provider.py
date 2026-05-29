# SPDX-License-Identifier: AGPL-3.0-or-later

"""Custom OpenFeature provider backed by Unleash.

No official OpenFeature -> Unleash Python provider exists (Unleash/unleash#3912),
so we implement AbstractProvider directly. Boolean resolution is the load-bearing
path (tier gating); other types return defaults.

Integrity (per 00-03 audit):
- Reject non-https Unleash URLs unless allow_insecure=True (dev only).
- Token comes from the caller (read from env/secrets upstream), never hardcoded.
- A malformed / unexpected / errored response FAILS CLOSED (returns default).
"""

from __future__ import annotations

from typing import Any

import structlog
from openfeature.evaluation_context import EvaluationContext
from openfeature.flag_evaluation import FlagResolutionDetails, Reason
from openfeature.provider import AbstractProvider, Metadata

log = structlog.get_logger(__name__)


class UnleashProvider(AbstractProvider):
    """OpenFeature provider delegating boolean flags to an Unleash client."""

    def __init__(
        self,
        unleash_url: str,
        app_name: str,
        token: str,
        *,
        allow_insecure: bool = False,
    ) -> None:
        if not unleash_url.startswith("https://") and not allow_insecure:
            raise ValueError(
                "UnleashProvider requires an https:// URL. "
                "Pass allow_insecure=True only in local dev."
            )
        if not token:
            raise ValueError("UnleashProvider requires a token (read from env/secrets).")
        self._url = unleash_url
        self._app_name = app_name
        self._token = token
        self._client: Any | None = None

    def get_metadata(self) -> Metadata:
        return Metadata(name="UnleashProvider")

    def _ensure_client(self) -> Any:
        if self._client is None:
            from UnleashClient import UnleashClient  # lazy: optional dep

            self._client = UnleashClient(
                url=self._url,
                app_name=self._app_name,
                custom_headers={"Authorization": self._token},
            )
            self._client.initialize_client()
        return self._client

    def resolve_boolean_details(
        self,
        flag_key: str,
        default_value: bool,
        evaluation_context: EvaluationContext | None = None,
    ) -> FlagResolutionDetails[bool]:
        try:
            client = self._ensure_client()
            ctx = self._map_context(evaluation_context)
            value = client.is_enabled(flag_key, context=ctx, fallback_function=None)
            if not isinstance(value, bool):
                # Malformed / unexpected response — fail closed, do NOT trust it.
                log.warning(
                    "unleash.malformed_response",
                    flag=flag_key,
                    got_type=type(value).__name__,
                )
                return FlagResolutionDetails(value=default_value, reason=Reason.ERROR)
            return FlagResolutionDetails(value=value, reason=Reason.TARGETING_MATCH)
        except Exception as exc:  # fail closed on ANY provider error
            log.warning("unleash.resolve_error", flag=flag_key, error=str(exc))
            return FlagResolutionDetails(value=default_value, reason=Reason.ERROR)

    @staticmethod
    def _map_context(evaluation_context: EvaluationContext | None) -> dict[str, Any]:
        if evaluation_context is None:
            return {}
        ctx: dict[str, Any] = dict(evaluation_context.attributes or {})
        if evaluation_context.targeting_key:
            ctx["userId"] = evaluation_context.targeting_key
        return ctx

    # Non-boolean resolutions: default-returning stubs (boolean is load-bearing).
    def resolve_string_details(
        self, flag_key: str, default_value: str, evaluation_context=None
    ) -> FlagResolutionDetails[str]:
        return FlagResolutionDetails(value=default_value, reason=Reason.DEFAULT)

    def resolve_integer_details(
        self, flag_key: str, default_value: int, evaluation_context=None
    ) -> FlagResolutionDetails[int]:
        return FlagResolutionDetails(value=default_value, reason=Reason.DEFAULT)

    def resolve_float_details(
        self, flag_key: str, default_value: float, evaluation_context=None
    ) -> FlagResolutionDetails[float]:
        return FlagResolutionDetails(value=default_value, reason=Reason.DEFAULT)

    def resolve_object_details(
        self, flag_key: str, default_value, evaluation_context=None
    ) -> FlagResolutionDetails:
        return FlagResolutionDetails(value=default_value, reason=Reason.DEFAULT)
