"""High-level kill switch API.

Wraps the :class:`KillSwitchStore` Protocol with the operator-facing
verbs ``activate`` / ``deactivate`` / ``current_state`` plus structured
audit logging for every state change. Build-plan §6.6 requires every
activation to carry a *reason* — the audit log is the post-incident
trail and must never be empty.
"""

from __future__ import annotations

import structlog

from control_plane.domains.safety.repositories import KillSwitchStore
from control_plane.domains.safety.value_objects import KillSwitchState

log = structlog.get_logger("safety.kill_switch")

# Build-plan §6.6: 24-hour TTL forces a human renewal for extended halts.
DEFAULT_TTL_SECONDS = 24 * 3600
MIN_TTL_SECONDS = 60                    # 1 minute
MAX_TTL_SECONDS = 7 * 24 * 3600         # 7 days


class KillSwitchService:
    """Operator-facing kill switch verbs."""

    def __init__(self, store: KillSwitchStore) -> None:
        self._store = store

    async def current_state(self) -> KillSwitchState:
        """Return the live kill switch state. Cheap — safe to call often."""
        return await self._store.get_state()

    async def activate(
        self,
        state: KillSwitchState,
        reason: str,
        actor: str,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
    ) -> None:
        """Set the kill switch to *state*.

        Args:
            state: One of ``HALT_SUBMISSIONS`` / ``HALT_SCANS`` / ``HALT_ALL``.
                Pass ``INACTIVE`` to :meth:`deactivate` instead — this
                method rejects it so the audit log's ``activate`` events
                always represent a real halt.
            reason: Free-form description of why the halt is being
                applied. Must be non-empty — empty reasons are an
                operational antipattern that defeats post-incident review.
            actor: Identifier of who or what is activating (operator id,
                automated rule name, alert id, etc.).
            ttl_seconds: Auto-expiry. Defaults to 24h; clamped to
                [``MIN_TTL_SECONDS``, ``MAX_TTL_SECONDS``].
        """
        if state == KillSwitchState.INACTIVE:
            raise ValueError(
                "Use deactivate() to clear the kill switch; "
                "activate() requires a non-inactive state"
            )
        if not reason or not reason.strip():
            raise ValueError("activate() requires a non-empty reason")
        if not actor or not actor.strip():
            raise ValueError("activate() requires a non-empty actor")
        if not (MIN_TTL_SECONDS <= ttl_seconds <= MAX_TTL_SECONDS):
            raise ValueError(
                f"ttl_seconds must be in "
                f"[{MIN_TTL_SECONDS}, {MAX_TTL_SECONDS}], got {ttl_seconds}"
            )

        await self._store.set_state(state, ttl_seconds=ttl_seconds)
        log.warning(
            "kill_switch.activated",
            state=state.value,
            reason=reason,
            actor=actor,
            ttl_seconds=ttl_seconds,
        )

    async def deactivate(self, reason: str, actor: str) -> None:
        """Clear the kill switch. Reason + actor still required for audit."""
        if not reason or not reason.strip():
            raise ValueError("deactivate() requires a non-empty reason")
        if not actor or not actor.strip():
            raise ValueError("deactivate() requires a non-empty actor")

        await self._store.clear()
        log.warning(
            "kill_switch.deactivated",
            reason=reason,
            actor=actor,
        )

    async def is_tool_blocked(self, tool_category: str) -> bool:
        """Return True iff *tool_category* should be blocked right now.

        Categories used by the PreToolUse hook:
          * ``"submit"`` — blocked when state ≥ HALT_SUBMISSIONS
          * ``"network"`` — blocked when state ≥ HALT_SCANS
          * ``"any"`` — blocked when state == HALT_ALL
        """
        state = await self._store.get_state()
        if tool_category == "any":
            return state.blocks_all
        if tool_category == "network":
            return state.blocks_scans
        if tool_category == "submit":
            return state.blocks_submissions
        raise ValueError(
            f"unknown tool_category {tool_category!r}; "
            f"expected 'submit' | 'network' | 'any'"
        )


__all__ = ["DEFAULT_TTL_SECONDS", "MAX_TTL_SECONDS", "MIN_TTL_SECONDS", "KillSwitchService"]
