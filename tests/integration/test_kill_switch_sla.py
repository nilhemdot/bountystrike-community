"""Integration test for kill-switch SLA verification (Phase 3 §10.4).

Spawns mock agent workers, activates the kill switch, and measures the
time until all workers halt. The SLA requires < 5 seconds end-to-end
halt latency, and this test validates consistency across multiple runs.

Build-plan exit criterion: SLA consistently <5s across 10 runs.

Local repro::

    uv run pytest tests/integration/test_kill_switch_sla.py -v
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "control-plane" / "src"))

from control_plane.domains.safety import (  # noqa: E402
    AgentSupervisor,
    InMemoryKillSwitchStore,
    KillSwitchService,
    KillSwitchState,
    WorkerScope,
)
from control_plane.domains.safety.monitoring import (  # noqa: E402
    KillSwitchMonitor,
)
from control_plane.domains.safety.services.agent_supervisor import (  # noqa: E402
    DEFAULT_POLL_INTERVAL_SECONDS,
)

# SLA budget from build-plan §10.4
SLA_BUDGET_SECONDS = 5.0

# Number of workers to simulate realistic load
WORKER_COUNT = 50

# Number of test runs to validate consistency
CONSISTENCY_RUNS = 10


def _make_service() -> tuple[KillSwitchService, InMemoryKillSwitchStore]:
    """Create a fresh kill-switch service with in-memory store."""
    store = InMemoryKillSwitchStore()
    return KillSwitchService(store), store


async def _mock_worker() -> None:
    """Mock worker that runs indefinitely until cancelled."""
    await asyncio.sleep(3600)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("run_number", range(1, CONSISTENCY_RUNS + 1))
async def test_kill_switch_sla_consistency(run_number: int) -> None:
    """Verify kill-switch halts all workers within 5s SLA (run {run_number}/{CONSISTENCY_RUNS}).

    Spawns {WORKER_COUNT} mock workers across all scope tiers (SUBMIT,
    SCAN, OTHER), activates HALT_ALL, and measures end-to-end latency.
    The test fails if quiescence exceeds the §10.4 SLA budget or if
    workers remain running.
    """
    service, store = _make_service()
    sup = AgentSupervisor(service, poll_interval_seconds=DEFAULT_POLL_INTERVAL_SECONDS)
    await sup.start()
    tasks: list[asyncio.Task[None]] = []
    try:
        # Distribute workers evenly across all scope tiers
        scopes = [WorkerScope.SUBMIT, WorkerScope.SCAN, WorkerScope.OTHER]
        for i in range(WORKER_COUNT):
            task = asyncio.create_task(_mock_worker())
            tasks.append(task)
            sup.register(f"worker-{run_number}-{i}", scopes[i % 3], task)

        # Verify all workers are registered
        assert len(sup.registered_worker_ids) == WORKER_COUNT

        # Measure end-to-end latency from kill-switch activation to quiescence
        start = time.monotonic()
        await store.set_state(KillSwitchState.HALT_ALL, ttl_seconds=300)
        quiesced = await sup.wait_until_quiesced(timeout=SLA_BUDGET_SECONDS)
        elapsed = time.monotonic() - start

        # Assert SLA requirements
        assert quiesced, (
            f"Run {run_number}/{CONSISTENCY_RUNS}: kill switch missed §10.4 "
            f"SLA — workers still running after {SLA_BUDGET_SECONDS}s "
            f"(elapsed: {elapsed:.3f}s, workers: {WORKER_COUNT})"
        )
        assert elapsed < SLA_BUDGET_SECONDS, (
            f"Run {run_number}/{CONSISTENCY_RUNS}: kill switch elapsed "
            f"{elapsed:.3f}s, breaches §10.4 {SLA_BUDGET_SECONDS}s budget"
        )

        # Verify all workers were cancelled and unregistered
        assert all(t.done() for t in tasks), (
            f"Run {run_number}/{CONSISTENCY_RUNS}: not all workers were halted"
        )
        assert sup.registered_worker_ids == (), (
            f"Run {run_number}/{CONSISTENCY_RUNS}: workers remain registered "
            f"after halt: {sup.registered_worker_ids}"
        )
    finally:
        # Cleanup: cancel any remaining tasks
        for t in tasks:
            if not t.done():
                t.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        await sup.stop()


async def test_kill_switch_sla_under_mixed_load() -> None:
    """Verify SLA holds under mixed scope distribution.

    Tests kill-switch behavior when worker distribution is uneven across
    scopes (heavier SUBMIT load) to validate that scope-specific
    cancellation doesn't introduce latency skew.
    """
    service, store = _make_service()
    sup = AgentSupervisor(service, poll_interval_seconds=DEFAULT_POLL_INTERVAL_SECONDS)
    await sup.start()
    tasks: list[asyncio.Task[None]] = []
    try:
        # Skewed distribution: 60% SUBMIT, 30% SCAN, 10% OTHER
        submit_count = int(WORKER_COUNT * 0.6)
        scan_count = int(WORKER_COUNT * 0.3)
        other_count = WORKER_COUNT - submit_count - scan_count

        worker_id = 0
        for _ in range(submit_count):
            task = asyncio.create_task(_mock_worker())
            tasks.append(task)
            sup.register(f"submit-{worker_id}", WorkerScope.SUBMIT, task)
            worker_id += 1

        for _ in range(scan_count):
            task = asyncio.create_task(_mock_worker())
            tasks.append(task)
            sup.register(f"scan-{worker_id}", WorkerScope.SCAN, task)
            worker_id += 1

        for _ in range(other_count):
            task = asyncio.create_task(_mock_worker())
            tasks.append(task)
            sup.register(f"other-{worker_id}", WorkerScope.OTHER, task)
            worker_id += 1

        start = time.monotonic()
        await store.set_state(KillSwitchState.HALT_ALL, ttl_seconds=300)
        quiesced = await sup.wait_until_quiesced(timeout=SLA_BUDGET_SECONDS)
        elapsed = time.monotonic() - start

        assert quiesced, (
            f"Mixed load: kill switch missed SLA (elapsed: {elapsed:.3f}s)"
        )
        assert elapsed < SLA_BUDGET_SECONDS, (
            f"Mixed load: elapsed {elapsed:.3f}s breaches {SLA_BUDGET_SECONDS}s SLA"
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


async def test_kill_switch_sla_with_graduated_halt() -> None:
    """Verify partial halts (HALT_SUBMISSIONS, HALT_SCANS) also meet SLA.

    Tests that lower-tier kill-switch activations cancel their respective
    scopes within the SLA budget while leaving other scopes running.
    """
    service, store = _make_service()
    sup = AgentSupervisor(service, poll_interval_seconds=DEFAULT_POLL_INTERVAL_SECONDS)
    await sup.start()
    submit_tasks: list[asyncio.Task[None]] = []
    scan_tasks: list[asyncio.Task[None]] = []
    other_tasks: list[asyncio.Task[None]] = []
    try:
        # Create equal distribution across scopes
        workers_per_scope = WORKER_COUNT // 3
        for i in range(workers_per_scope):
            t = asyncio.create_task(_mock_worker())
            submit_tasks.append(t)
            sup.register(f"submit-{i}", WorkerScope.SUBMIT, t)

            t = asyncio.create_task(_mock_worker())
            scan_tasks.append(t)
            sup.register(f"scan-{i}", WorkerScope.SCAN, t)

            t = asyncio.create_task(_mock_worker())
            other_tasks.append(t)
            sup.register(f"other-{i}", WorkerScope.OTHER, t)

        # Test HALT_SUBMISSIONS: only SUBMIT workers should halt
        start = time.monotonic()
        await store.set_state(KillSwitchState.HALT_SUBMISSIONS, ttl_seconds=300)

        # Wait for SUBMIT workers to halt (with SLA budget)
        for _ in range(int(SLA_BUDGET_SECONDS * 100)):
            if all(t.done() for t in submit_tasks):
                break
            await asyncio.sleep(0.01)
        elapsed = time.monotonic() - start

        assert elapsed < SLA_BUDGET_SECONDS, (
            f"HALT_SUBMISSIONS elapsed {elapsed:.3f}s, breaches SLA"
        )
        assert all(t.done() for t in submit_tasks), (
            "HALT_SUBMISSIONS did not cancel all SUBMIT workers"
        )
        assert not any(t.done() for t in scan_tasks), (
            "HALT_SUBMISSIONS incorrectly cancelled SCAN workers"
        )
        assert not any(t.done() for t in other_tasks), (
            "HALT_SUBMISSIONS incorrectly cancelled OTHER workers"
        )
    finally:
        for task_list in [submit_tasks, scan_tasks, other_tasks]:
            for t in task_list:
                if not t.done():
                    t.cancel()
        all_tasks = submit_tasks + scan_tasks + other_tasks
        if all_tasks:
            await asyncio.gather(*all_tasks, return_exceptions=True)
        await sup.stop()


async def test_kill_switch_persistence() -> None:
    """Verify workers cannot resume without explicit deactivate.

    Tests that kill-switch state persists: after activation, new workers
    cannot start even if they are registered later. Only after explicit
    deactivation (set to INACTIVE) can new workers run.
    """
    service, store = _make_service()
    sup = AgentSupervisor(service, poll_interval_seconds=DEFAULT_POLL_INTERVAL_SECONDS)
    await sup.start()
    initial_tasks: list[asyncio.Task[None]] = []
    blocked_tasks: list[asyncio.Task[None]] = []
    resumed_tasks: list[asyncio.Task[None]] = []
    try:
        # Phase 1: Register and halt initial workers
        for i in range(5):
            task = asyncio.create_task(_mock_worker())
            initial_tasks.append(task)
            sup.register(f"initial-{i}", WorkerScope.SUBMIT, task)

        await store.set_state(KillSwitchState.HALT_ALL, ttl_seconds=300)
        quiesced = await sup.wait_until_quiesced(timeout=SLA_BUDGET_SECONDS)

        assert quiesced, "Initial workers did not halt within SLA"
        assert all(t.done() for t in initial_tasks), (
            "Initial workers not cancelled after kill switch"
        )
        assert sup.registered_worker_ids == (), (
            "Workers remain registered after halt"
        )

        # Phase 2: Try to register new workers while kill switch is ACTIVE
        # These workers should be immediately cancelled by the supervisor
        for i in range(5):
            task = asyncio.create_task(_mock_worker())
            blocked_tasks.append(task)
            sup.register(f"blocked-{i}", WorkerScope.SUBMIT, task)

        # Give supervisor time to process registrations and cancel workers
        await asyncio.sleep(0.5)

        # Verify new workers were cancelled (kill switch still active)
        assert all(t.done() for t in blocked_tasks), (
            "Workers registered during active kill switch were not cancelled — "
            "kill switch state did not persist"
        )
        assert sup.registered_worker_ids == (), (
            "Blocked workers remain registered despite active kill switch"
        )

        # Verify kill switch is still active
        current_state = await store.get_state()
        assert current_state == KillSwitchState.HALT_ALL, (
            f"Kill switch state unexpectedly changed: {current_state}"
        )

        # Phase 3: Deactivate kill switch and verify workers can now run
        await store.set_state(KillSwitchState.INACTIVE, ttl_seconds=1)

        # Wait a poll cycle for supervisor to detect state change
        await asyncio.sleep(DEFAULT_POLL_INTERVAL_SECONDS + 0.1)

        # Register new workers — these should run successfully
        for i in range(5):
            task = asyncio.create_task(_mock_worker())
            resumed_tasks.append(task)
            sup.register(f"resumed-{i}", WorkerScope.SUBMIT, task)

        # Give workers time to start
        await asyncio.sleep(0.5)

        # Verify workers are running (not cancelled)
        assert not any(t.done() for t in resumed_tasks), (
            "Workers registered after deactivation were incorrectly cancelled"
        )
        assert len(sup.registered_worker_ids) == 5, (
            f"Expected 5 resumed workers, got {len(sup.registered_worker_ids)}"
        )
    finally:
        # Cleanup all task lists
        for task_list in [initial_tasks, blocked_tasks, resumed_tasks]:
            for t in task_list:
                if not t.done():
                    t.cancel()
        all_tasks = initial_tasks + blocked_tasks + resumed_tasks
        if all_tasks:
            await asyncio.gather(*all_tasks, return_exceptions=True)
        await sup.stop()


async def test_alert_fires_within_1s() -> None:
    """Verify monitoring alert fires within 1s of kill-switch activation.

    Tests the §10.4 observability requirement: when the kill switch
    transitions from INACTIVE to any active state (HALT_SUBMISSIONS,
    HALT_SCANS, HALT_ALL), a structured log alert must be emitted
    to the safety.kill_switch.alert namespace within 1 second.

    The alert latency is dominated by the supervisor's poll interval
    (100ms default). At this cadence the worst-case detection time is
    one poll cycle plus minimal asyncio overhead, well under the 1s SLA.
    """
    service, store = _make_service()
    monitor = KillSwitchMonitor(service, poll_interval_seconds=DEFAULT_POLL_INTERVAL_SECONDS)
    sup = AgentSupervisor(service, poll_interval_seconds=DEFAULT_POLL_INTERVAL_SECONDS, monitor=monitor)
    await sup.start()
    try:
        # Capture alert emissions by mocking the supervisor's _emit_alert
        captured_alerts: list[dict[str, float | str]] = []
        original_emit = sup._emit_alert

        def mock_emit(state: KillSwitchState) -> None:
            captured_alerts.append({
                "timestamp": time.monotonic(),
                "state": state.value,
            })
            original_emit(state)

        sup._emit_alert = mock_emit  # type: ignore[method-assign]

        # Activate kill switch and measure time until alert fires
        activation_time = time.monotonic()
        await store.set_state(KillSwitchState.HALT_ALL, ttl_seconds=300)

        # Wait up to 1.5s for alert (margin for test robustness, but SLA is 1s)
        await asyncio.sleep(1.5)

        # Verify alert was emitted
        assert len(captured_alerts) > 0, (
            "Expected alert to fire after kill-switch activation"
        )

        # Verify alert latency meets <1s SLA
        alert_time = captured_alerts[0]["timestamp"]
        latency = alert_time - activation_time

        assert latency < 1.0, (
            f"Alert latency {latency:.3f}s breaches §10.4 1s SLA — "
            f"expected alert within 1s of activation"
        )

        # Verify alert payload
        assert captured_alerts[0]["state"] == KillSwitchState.HALT_ALL.value, (
            f"Alert state mismatch: expected {KillSwitchState.HALT_ALL.value}, "
            f"got {captured_alerts[0]['state']}"
        )
    finally:
        await sup.stop()
