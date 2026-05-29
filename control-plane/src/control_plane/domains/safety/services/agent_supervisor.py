# SPDX-License-Identifier: AGPL-3.0-or-later

"""Layer-3 kill-switch enforcer — :class:`AgentSupervisor`.

Polls :class:`KillSwitchService` and cancels registered worker tasks
when a halt is observed, mirroring ``KillSwitchState.blocks_*``
semantics. The poll interval is the dominant component of the
kill-switch SLA: at the default 100ms cadence the worst-case detection
latency is one interval plus asyncio cancellation propagation
(typically <1ms), well inside the build-plan §10.4 5-second exit
criterion ("kill switch halts all running agents within 5 seconds").

The supervisor mirrors ``pretool_killswitch.py``'s scope categories:

* :attr:`WorkerScope.SUBMIT` — platform submission tasks; cancelled on
  :attr:`KillSwitchState.HALT_SUBMISSIONS` and above.
* :attr:`WorkerScope.SCAN` — network-touching scan or validation tasks;
  cancelled on :attr:`KillSwitchState.HALT_SCANS` and above.
* :attr:`WorkerScope.OTHER` — orchestration / non-network work;
  cancelled only on :attr:`KillSwitchState.HALT_ALL`.

The supervisor never raises out of its polling loop; failures inside
the loop are logged and the loop continues, because terminating the
supervisor would silently disable Layer 3 of the kill switch. The hook
layer (Layer 2, ``pretool_killswitch.py``) and the OpenRouter Bridge
guard (Layer 1) remain in force regardless.

When a :class:`KillSwitchMonitor` is provided, the supervisor emits
structured log alerts (to the ``safety.kill_switch.alert`` namespace)
on state transitions from ``INACTIVE`` to any active tier, meeting the
build-plan §10.4 <1s alert-latency requirement.
"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from control_plane.domains.safety.monitoring.kill_switch_monitor import (
        KillSwitchMonitor,
    )

from control_plane.domains.safety.services.kill_switch_service import (
    KillSwitchService,
)
from control_plane.domains.safety.value_objects import KillSwitchState

log = structlog.get_logger("safety.agent_supervisor")
alert_log = structlog.get_logger("safety.kill_switch.alert")

# Build-plan §6.6: 100ms poll cadence keeps Layer-3 latency well below
# the 5-second exit criterion while staying cheap on Redis.
DEFAULT_POLL_INTERVAL_SECONDS = 0.1
MIN_POLL_INTERVAL_SECONDS = 0.01
MAX_POLL_INTERVAL_SECONDS = 1.0


class WorkerScope(StrEnum):
    """Scope tag determining which kill-switch tier cancels the worker."""

    SUBMIT = "submit"
    SCAN = "scan"
    OTHER = "other"


def _scope_blocked(state: KillSwitchState, scope: WorkerScope) -> bool:
    """Return True iff *scope* must be cancelled under *state*."""
    if scope is WorkerScope.SUBMIT:
        return state.blocks_submissions
    if scope is WorkerScope.SCAN:
        return state.blocks_scans
    return state.blocks_all


@dataclass
class _Worker:
    worker_id: str
    scope: WorkerScope
    task: asyncio.Task[Any]


class AgentSupervisor:
    """Layer-3 kill-switch enforcer.

    Usage::

        supervisor = AgentSupervisor(service)
        await supervisor.start()
        try:
            supervisor.register("recon-1", WorkerScope.SCAN, task)
            ...
        finally:
            await supervisor.stop()

    With monitoring enabled::

        monitor = KillSwitchMonitor(service)
        supervisor = AgentSupervisor(service, monitor=monitor)
        await supervisor.start()
        # Alerts fire automatically on state transitions
    """

    def __init__(
        self,
        service: KillSwitchService,
        poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
        *,
        monitor: KillSwitchMonitor | None = None,
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
        self._monitor = monitor
        self._workers: dict[str, _Worker] = {}
        self._poll_task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()
        self._quiesced_event = asyncio.Event()
        self._quiesced_event.set()  # initially nothing to quiesce
        self._last_observed_state: KillSwitchState = KillSwitchState.INACTIVE

    # ---- Lifecycle -------------------------------------------------

    @property
    def is_running(self) -> bool:
        return self._poll_task is not None and not self._poll_task.done()

    @property
    def last_observed_state(self) -> KillSwitchState:
        return self._last_observed_state

    @property
    def registered_worker_ids(self) -> tuple[str, ...]:
        return tuple(self._workers.keys())

    async def start(self) -> None:
        if self.is_running:
            return
        self._stop_event.clear()
        self._poll_task = asyncio.create_task(
            self._poll_loop(), name="kill-switch-supervisor"
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

    # ---- Worker registration --------------------------------------

    def register(
        self,
        worker_id: str,
        scope: WorkerScope,
        task: asyncio.Task[Any],
    ) -> None:
        if not worker_id or not worker_id.strip():
            raise ValueError("worker_id must be non-empty")
        if worker_id in self._workers:
            raise ValueError(f"worker_id {worker_id!r} already registered")
        self._workers[worker_id] = _Worker(
            worker_id=worker_id, scope=scope, task=task
        )
        if not task.done():
            self._quiesced_event.clear()

    def unregister(self, worker_id: str) -> None:
        self._workers.pop(worker_id, None)
        self._update_quiescence()

    # ---- Quiescence wait ------------------------------------------

    async def wait_until_quiesced(self, timeout: float | None = None) -> bool:  # noqa: ASYNC109 — public API mirrors asyncio.wait_for timeout semantics
        """Return True iff every registered worker has stopped within *timeout*.

        "Quiesced" means no live registered tasks: either they finished
        naturally, were cancelled by the supervisor under a halt
        observation, or were unregistered. Used by SLA tests and the
        orchestrator's shutdown path.
        """
        try:
            await asyncio.wait_for(
                self._quiesced_event.wait(), timeout=timeout
            )
            return True
        except TimeoutError:
            return False

    # ---- Polling loop ---------------------------------------------

    async def _poll_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                state = await self._service.current_state()
            except Exception as exc:  # noqa: BLE001 — fail-open per §6.6
                log.error("kill_switch.poll_failed", error=str(exc))
                state = KillSwitchState.INACTIVE

            # Emit monitoring alert on INACTIVE → ACTIVE transition
            if (
                self._monitor is not None
                and self._last_observed_state == KillSwitchState.INACTIVE
                and state != KillSwitchState.INACTIVE
            ):
                self._emit_alert(state)

            self._last_observed_state = state

            if state != KillSwitchState.INACTIVE:
                await self._enforce(state)
            else:
                self._reap_finished()

            self._update_quiescence()

            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self._poll_interval,
                )

    async def _enforce(self, state: KillSwitchState) -> None:
        # Reap anything that completed naturally regardless of state.
        self._reap_finished()
        to_cancel = [
            w
            for w in list(self._workers.values())
            if not w.task.done() and _scope_blocked(state, w.scope)
        ]
        if not to_cancel:
            return
        log.warning(
            "kill_switch.cancelling_workers",
            state=state.value,
            count=len(to_cancel),
            worker_ids=[w.worker_id for w in to_cancel],
        )
        for w in to_cancel:
            w.task.cancel()
        await asyncio.gather(
            *(w.task for w in to_cancel), return_exceptions=True
        )
        for w in to_cancel:
            self._workers.pop(w.worker_id, None)

    def _reap_finished(self) -> None:
        finished_ids = [
            wid for wid, w in self._workers.items() if w.task.done()
        ]
        for wid in finished_ids:
            self._workers.pop(wid, None)

    def _update_quiescence(self) -> None:
        if any(not w.task.done() for w in self._workers.values()):
            self._quiesced_event.clear()
        else:
            self._quiesced_event.set()

    def _emit_alert(self, state: KillSwitchState) -> None:
        """Emit structured log alert for kill-switch activation.

        Mirrors :meth:`KillSwitchMonitor._emit_alert` to provide
        integrated alerting when a monitor is attached to the supervisor.
        """
        alert_log.warning(
            "kill_switch.alert",
            state=state.value,
            timestamp=datetime.now(UTC).isoformat(),
            severity="critical",
        )


__all__ = [
    "DEFAULT_POLL_INTERVAL_SECONDS",
    "MAX_POLL_INTERVAL_SECONDS",
    "MIN_POLL_INTERVAL_SECONDS",
    "AgentSupervisor",
    "WorkerScope",
]
