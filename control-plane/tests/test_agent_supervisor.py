"""Layer-3 kill-switch enforcer tests — :class:`AgentSupervisor`.

Build-plan §10.4 exit criterion: kill switch must halt all running
agents within 5 seconds. The SLA test at the bottom of this module is
the regression guard for that promise.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from control_plane.domains.safety import (
    AgentSupervisor,
    InMemoryKillSwitchStore,
    KillSwitchService,
    KillSwitchState,
    WorkerScope,
)
from control_plane.domains.safety.services.agent_supervisor import (
    DEFAULT_POLL_INTERVAL_SECONDS,
    MAX_POLL_INTERVAL_SECONDS,
    MIN_POLL_INTERVAL_SECONDS,
    _scope_blocked,
)


# Match the supervisor's own poll cadence in tests so we don't add
# accidental wall-clock dependence; tests that need faster reactivity
# pass an explicit override.
FAST_POLL = 0.01


def _make_service() -> tuple[KillSwitchService, InMemoryKillSwitchStore]:
    store = InMemoryKillSwitchStore()
    return KillSwitchService(store), store


async def _await_long_running() -> None:
    """A worker body that runs until cancelled."""
    await asyncio.sleep(3600)


# ---------------------------------------------------------------------------
# 1. _scope_blocked — escalation matrix matches KillSwitchState semantics
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "state,scope,expected",
    [
        (KillSwitchState.INACTIVE, WorkerScope.SUBMIT, False),
        (KillSwitchState.INACTIVE, WorkerScope.SCAN, False),
        (KillSwitchState.INACTIVE, WorkerScope.OTHER, False),
        (KillSwitchState.HALT_SUBMISSIONS, WorkerScope.SUBMIT, True),
        (KillSwitchState.HALT_SUBMISSIONS, WorkerScope.SCAN, False),
        (KillSwitchState.HALT_SUBMISSIONS, WorkerScope.OTHER, False),
        (KillSwitchState.HALT_SCANS, WorkerScope.SUBMIT, True),
        (KillSwitchState.HALT_SCANS, WorkerScope.SCAN, True),
        (KillSwitchState.HALT_SCANS, WorkerScope.OTHER, False),
        (KillSwitchState.HALT_ALL, WorkerScope.SUBMIT, True),
        (KillSwitchState.HALT_ALL, WorkerScope.SCAN, True),
        (KillSwitchState.HALT_ALL, WorkerScope.OTHER, True),
    ],
)
def test_scope_blocked_matches_kill_switch_tier(
    state: KillSwitchState, scope: WorkerScope, expected: bool
) -> None:
    assert _scope_blocked(state, scope) is expected


# ---------------------------------------------------------------------------
# 2. Constructor — poll-interval validation
# ---------------------------------------------------------------------------


def test_init_rejects_below_min_poll_interval() -> None:
    service, _ = _make_service()
    with pytest.raises(ValueError, match="poll_interval_seconds"):
        AgentSupervisor(service, poll_interval_seconds=MIN_POLL_INTERVAL_SECONDS / 2)


def test_init_rejects_above_max_poll_interval() -> None:
    service, _ = _make_service()
    with pytest.raises(ValueError, match="poll_interval_seconds"):
        AgentSupervisor(service, poll_interval_seconds=MAX_POLL_INTERVAL_SECONDS + 0.1)


def test_init_accepts_default_poll_interval() -> None:
    service, _ = _make_service()
    sup = AgentSupervisor(service)
    assert sup.is_running is False
    assert sup.last_observed_state == KillSwitchState.INACTIVE
    assert sup.registered_worker_ids == ()
    # Sanity: the documented default lies in the allowed band.
    assert MIN_POLL_INTERVAL_SECONDS <= DEFAULT_POLL_INTERVAL_SECONDS <= MAX_POLL_INTERVAL_SECONDS


# ---------------------------------------------------------------------------
# 3. Lifecycle — start / stop idempotency
# ---------------------------------------------------------------------------


async def test_start_then_stop_runs_and_halts_poll_loop() -> None:
    service, _ = _make_service()
    sup = AgentSupervisor(service, poll_interval_seconds=FAST_POLL)
    assert sup.is_running is False
    await sup.start()
    assert sup.is_running is True
    await sup.stop()
    assert sup.is_running is False


async def test_start_is_idempotent() -> None:
    service, _ = _make_service()
    sup = AgentSupervisor(service, poll_interval_seconds=FAST_POLL)
    await sup.start()
    first_task = sup._poll_task  # type: ignore[attr-defined]
    await sup.start()
    second_task = sup._poll_task  # type: ignore[attr-defined]
    assert first_task is second_task  # same task, no double-start
    await sup.stop()


async def test_stop_without_start_is_noop() -> None:
    service, _ = _make_service()
    sup = AgentSupervisor(service, poll_interval_seconds=FAST_POLL)
    await sup.stop()  # must not raise


# ---------------------------------------------------------------------------
# 4. register / unregister — argument hygiene
# ---------------------------------------------------------------------------


async def test_register_rejects_empty_worker_id() -> None:
    service, _ = _make_service()
    sup = AgentSupervisor(service, poll_interval_seconds=FAST_POLL)
    task = asyncio.create_task(_await_long_running())
    try:
        with pytest.raises(ValueError, match="worker_id"):
            sup.register("", WorkerScope.SCAN, task)
        with pytest.raises(ValueError, match="worker_id"):
            sup.register("   ", WorkerScope.SCAN, task)
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def test_register_rejects_duplicate_worker_id() -> None:
    service, _ = _make_service()
    sup = AgentSupervisor(service, poll_interval_seconds=FAST_POLL)
    t1 = asyncio.create_task(_await_long_running())
    t2 = asyncio.create_task(_await_long_running())
    try:
        sup.register("w1", WorkerScope.SCAN, t1)
        with pytest.raises(ValueError, match="already registered"):
            sup.register("w1", WorkerScope.SCAN, t2)
    finally:
        for t in (t1, t2):
            t.cancel()
        await asyncio.gather(t1, t2, return_exceptions=True)


async def test_unregister_unknown_worker_is_noop() -> None:
    service, _ = _make_service()
    sup = AgentSupervisor(service, poll_interval_seconds=FAST_POLL)
    sup.unregister("never-registered")  # must not raise


async def test_unregister_removes_from_registered_ids() -> None:
    service, _ = _make_service()
    sup = AgentSupervisor(service, poll_interval_seconds=FAST_POLL)
    task = asyncio.create_task(_await_long_running())
    try:
        sup.register("w1", WorkerScope.OTHER, task)
        assert "w1" in sup.registered_worker_ids
        sup.unregister("w1")
        assert "w1" not in sup.registered_worker_ids
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


# ---------------------------------------------------------------------------
# 5. Cancellation by tier — SUBMIT < SCAN < OTHER
# ---------------------------------------------------------------------------


async def test_halt_submissions_cancels_only_submit_workers() -> None:
    service, store = _make_service()
    sup = AgentSupervisor(service, poll_interval_seconds=FAST_POLL)
    await sup.start()
    submit_task = asyncio.create_task(_await_long_running())
    scan_task = asyncio.create_task(_await_long_running())
    other_task = asyncio.create_task(_await_long_running())
    try:
        sup.register("submit-1", WorkerScope.SUBMIT, submit_task)
        sup.register("scan-1", WorkerScope.SCAN, scan_task)
        sup.register("other-1", WorkerScope.OTHER, other_task)

        await store.set_state(KillSwitchState.HALT_SUBMISSIONS, ttl_seconds=300)

        # Wait up to 1s for the poll to cancel — well above FAST_POLL.
        for _ in range(100):
            if submit_task.done():
                break
            await asyncio.sleep(0.01)

        assert submit_task.done()
        assert submit_task.cancelled() or isinstance(
            submit_task.exception(), asyncio.CancelledError
        )
        assert not scan_task.done()
        assert not other_task.done()
    finally:
        for t in (submit_task, scan_task, other_task):
            t.cancel()
        await asyncio.gather(
            submit_task, scan_task, other_task, return_exceptions=True
        )
        await sup.stop()


async def test_halt_scans_cancels_submit_and_scan_workers() -> None:
    service, store = _make_service()
    sup = AgentSupervisor(service, poll_interval_seconds=FAST_POLL)
    await sup.start()
    submit_task = asyncio.create_task(_await_long_running())
    scan_task = asyncio.create_task(_await_long_running())
    other_task = asyncio.create_task(_await_long_running())
    try:
        sup.register("submit-1", WorkerScope.SUBMIT, submit_task)
        sup.register("scan-1", WorkerScope.SCAN, scan_task)
        sup.register("other-1", WorkerScope.OTHER, other_task)

        await store.set_state(KillSwitchState.HALT_SCANS, ttl_seconds=300)

        for _ in range(200):
            if submit_task.done() and scan_task.done():
                break
            await asyncio.sleep(0.01)

        assert submit_task.done()
        assert scan_task.done()
        assert not other_task.done()
    finally:
        for t in (submit_task, scan_task, other_task):
            t.cancel()
        await asyncio.gather(
            submit_task, scan_task, other_task, return_exceptions=True
        )
        await sup.stop()


async def test_halt_all_cancels_every_scope() -> None:
    service, store = _make_service()
    sup = AgentSupervisor(service, poll_interval_seconds=FAST_POLL)
    await sup.start()
    submit_task = asyncio.create_task(_await_long_running())
    scan_task = asyncio.create_task(_await_long_running())
    other_task = asyncio.create_task(_await_long_running())
    try:
        sup.register("submit-1", WorkerScope.SUBMIT, submit_task)
        sup.register("scan-1", WorkerScope.SCAN, scan_task)
        sup.register("other-1", WorkerScope.OTHER, other_task)

        await store.set_state(KillSwitchState.HALT_ALL, ttl_seconds=300)

        assert await sup.wait_until_quiesced(timeout=2.0)
        assert submit_task.done()
        assert scan_task.done()
        assert other_task.done()
    finally:
        for t in (submit_task, scan_task, other_task):
            t.cancel()
        await asyncio.gather(
            submit_task, scan_task, other_task, return_exceptions=True
        )
        await sup.stop()


async def test_cancelled_workers_are_unregistered() -> None:
    """After a halt cancels a worker, its id leaves the registry."""
    service, store = _make_service()
    sup = AgentSupervisor(service, poll_interval_seconds=FAST_POLL)
    await sup.start()
    task = asyncio.create_task(_await_long_running())
    try:
        sup.register("w1", WorkerScope.OTHER, task)
        assert sup.registered_worker_ids == ("w1",)

        await store.set_state(KillSwitchState.HALT_ALL, ttl_seconds=300)
        assert await sup.wait_until_quiesced(timeout=2.0)
        assert sup.registered_worker_ids == ()
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await sup.stop()


# ---------------------------------------------------------------------------
# 6. Reaping naturally completed workers (no halt)
# ---------------------------------------------------------------------------


async def test_finished_workers_are_reaped_under_inactive_state() -> None:
    """If a worker completes naturally, supervisor reaps it on next poll."""
    service, _ = _make_service()
    sup = AgentSupervisor(service, poll_interval_seconds=FAST_POLL)
    await sup.start()
    try:
        async def _quick() -> None:
            return None

        task = asyncio.create_task(_quick())
        sup.register("done-soon", WorkerScope.SCAN, task)
        await task  # let it finish
        # Wait for at least one poll iteration to reap.
        for _ in range(100):
            if sup.registered_worker_ids == ():
                break
            await asyncio.sleep(0.01)
        assert sup.registered_worker_ids == ()
    finally:
        await sup.stop()


# ---------------------------------------------------------------------------
# 7. wait_until_quiesced — semantics
# ---------------------------------------------------------------------------


async def test_wait_until_quiesced_returns_true_with_no_workers() -> None:
    service, _ = _make_service()
    sup = AgentSupervisor(service, poll_interval_seconds=FAST_POLL)
    # Initial state — nothing registered. Must already be quiesced.
    assert await sup.wait_until_quiesced(timeout=0.1)


async def test_wait_until_quiesced_returns_false_on_timeout() -> None:
    service, _ = _make_service()
    sup = AgentSupervisor(service, poll_interval_seconds=FAST_POLL)
    await sup.start()
    task = asyncio.create_task(_await_long_running())
    try:
        sup.register("w1", WorkerScope.OTHER, task)
        # No halt — worker stays alive past timeout.
        result = await sup.wait_until_quiesced(timeout=0.1)
        assert result is False
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await sup.stop()


# ---------------------------------------------------------------------------
# 8. Polling resilience — service errors must not kill the loop
# ---------------------------------------------------------------------------


class _FlakyService:
    """Service that raises on the first N polls then returns INACTIVE."""

    def __init__(self, error_count: int) -> None:
        self._remaining = error_count
        self.calls = 0

    async def current_state(self) -> KillSwitchState:
        self.calls += 1
        if self._remaining > 0:
            self._remaining -= 1
            raise RuntimeError("transient backend failure")
        return KillSwitchState.INACTIVE


async def test_poll_loop_swallows_service_errors() -> None:
    """Layer-3 supervisor must never die — a backend hiccup must not
    silently disable cancellation enforcement."""
    flaky = _FlakyService(error_count=3)
    sup = AgentSupervisor(flaky, poll_interval_seconds=FAST_POLL)  # type: ignore[arg-type]
    await sup.start()
    try:
        # Wait for the supervisor to outlast the error burst.
        for _ in range(200):
            if flaky.calls > 5:
                break
            await asyncio.sleep(0.01)
        assert sup.is_running is True
        assert sup.last_observed_state == KillSwitchState.INACTIVE
    finally:
        await sup.stop()


# ---------------------------------------------------------------------------
# 9. Build-plan §10.4 SLA — kill switch halts all agents within 5 seconds
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("worker_count", [50])
async def test_kill_switch_halts_all_workers_within_5_seconds_sla(
    worker_count: int,
) -> None:
    """SLA regression: §10.4 requires <5s end-to-end halt latency for
    every running agent. We simulate ``worker_count`` long-running tasks
    spread across all three scope tiers, flip the kill switch to
    HALT_ALL, and assert the supervisor quiesces inside the budget.
    """
    service, store = _make_service()
    sup = AgentSupervisor(service, poll_interval_seconds=DEFAULT_POLL_INTERVAL_SECONDS)
    await sup.start()
    tasks: list[asyncio.Task[None]] = []
    try:
        scopes = [WorkerScope.SUBMIT, WorkerScope.SCAN, WorkerScope.OTHER]
        for i in range(worker_count):
            task = asyncio.create_task(_await_long_running())
            tasks.append(task)
            sup.register(f"worker-{i}", scopes[i % 3], task)

        # The clock starts when the operator pulls the lever.
        start = time.monotonic()
        await store.set_state(KillSwitchState.HALT_ALL, ttl_seconds=300)
        quiesced = await sup.wait_until_quiesced(timeout=5.0)
        elapsed = time.monotonic() - start

        assert quiesced, (
            f"kill switch missed §10.4 5s SLA: still running after 5s "
            f"({worker_count} workers)"
        )
        assert elapsed < 5.0, (
            f"kill switch elapsed {elapsed:.3f}s, breaches §10.4 budget"
        )
        assert all(t.done() for t in tasks)
        assert sup.registered_worker_ids == ()
    finally:
        for t in tasks:
            if not t.done():
                t.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        await sup.stop()
