"""Kill switch state-transition monitor.

Polls :class:`KillSwitchService` and emits structured log alerts when
the state transitions from ``INACTIVE`` to any active tier
(``HALT_SUBMISSIONS`` / ``HALT_SCANS`` / ``HALT_ALL``). The alert
latency target is <1s — at the default 100ms poll interval the
worst-case detection latency is one polling cycle, meeting the
build-plan §10.4 observability requirement.

The monitor logs to the ``safety.kill_switch.alert`` namespace at
WARNING level, matching the severity of the kill-switch activation
events in :class:`KillSwitchService`. These logs are the primary signal
for downstream alerting (PagerDuty, Slack, etc.).

The monitor never raises out of its polling loop; poll failures are
logged and the loop continues, because terminating the monitor would
silently disable kill-switch observability. This fail-safe pattern
mirrors :class:`AgentSupervisor`'s polling behavior.
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime

import structlog

from control_plane.domains.safety.services.kill_switch_service import (
    KillSwitchService,
)
from control_plane.domains.safety.value_objects import KillSwitchState

log = structlog.get_logger("safety.kill_switch.alert")

# Match supervisor's 100ms poll for consistent Layer-3 observability.
DEFAULT_POLL_INTERVAL_SECONDS = 0.1
MIN_POLL_INTERVAL_SECONDS = 0.01
MAX_POLL_INTERVAL_SECONDS = 1.0


class KillSwitchMonitor:
    """State-transition monitor for kill-switch alerting.

    Usage::

        monitor = KillSwitchMonitor(service)
        await monitor.start()
        try:
            # Monitor runs in background, emitting alerts on transitions
            ...
        finally:
            await monitor.stop()
    """

    def __init__(
        self,
        service: KillSwitchService,
        poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
    ) -> None:
        if not (
            MIN_POLL_INTERVAL_SECONDS
            <= poll_interval_seconds
            <= MAX_POLL_INTERVAL_SECONDS
        ):
            raise ValueError(
                f"poll_interval_seconds must be in "
                f"[{MIN_POLL_INTERVAL_SECONDS}, {MAX_POLL_INTERVAL_SECONDS}], "
                f"got {poll_interval_seconds}"
            )
        self._service = service
        self._poll_interval = poll_interval_seconds
        self._poll_task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()
        self._last_observed_state: KillSwitchState = KillSwitchState.INACTIVE

    # ---- Lifecycle -------------------------------------------------

    @property
    def is_running(self) -> bool:
        return self._poll_task is not None and not self._poll_task.done()

    @property
    def last_observed_state(self) -> KillSwitchState:
        return self._last_observed_state

    async def start(self) -> None:
        if self.is_running:
            return
        self._stop_event.clear()
        self._poll_task = asyncio.create_task(
            self._poll_loop(), name="kill-switch-monitor"
        )

    async def stop(self) -> None:
        if self._poll_task is None:
            return
        self._stop_event.set()
        timeout = max(2 * self._poll_interval + 1.0, 1.0)
        try:
            await asyncio.wait_for(self._poll_task, timeout=timeout)
        except TimeoutError:
            self._poll_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._poll_task
        self._poll_task = None

    # ---- Polling loop ---------------------------------------------

    async def _poll_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                state = await self._service.current_state()
            except Exception as exc:  # noqa: BLE001 — fail-safe per monitor pattern
                log.error("kill_switch.monitor_poll_failed", error=str(exc))
                # Don't update last_observed_state on error — we want to
                # detect the transition when the next successful poll
                # reveals an active state.
                state = self._last_observed_state

            # Detect INACTIVE → ACTIVE transition
            if (
                self._last_observed_state == KillSwitchState.INACTIVE
                and state != KillSwitchState.INACTIVE
            ):
                self._emit_alert(state)

            self._last_observed_state = state

            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self._poll_interval,
                )

    def _emit_alert(self, state: KillSwitchState) -> None:
        """Emit structured log alert for kill-switch activation."""
        log.warning(
            "kill_switch.alert",
            state=state.value,
            timestamp=datetime.now(UTC).isoformat(),
            severity="critical",
        )


__all__ = [
    "DEFAULT_POLL_INTERVAL_SECONDS",
    "MAX_POLL_INTERVAL_SECONDS",
    "MIN_POLL_INTERVAL_SECONDS",
    "KillSwitchMonitor",
]
