"""Kill switch state-transition monitor tests — :class:`KillSwitchMonitor`.

Build-plan §10.4 observability requirement: monitoring alert must fire
within 1 second of kill-switch activation. The latency tests in this
module verify that promise.
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import MagicMock

import pytest
import structlog
from control_plane.domains.safety import (
    InMemoryKillSwitchStore,
    KillSwitchService,
    KillSwitchState,
)
from control_plane.domains.safety.monitoring import KillSwitchMonitor
from control_plane.domains.safety.monitoring.kill_switch_monitor import (
    DEFAULT_POLL_INTERVAL_SECONDS,
    MAX_POLL_INTERVAL_SECONDS,
    MIN_POLL_INTERVAL_SECONDS,
)

# Fast poll for tests to minimize wall-clock time
FAST_POLL = 0.01


def _make_service() -> tuple[KillSwitchService, InMemoryKillSwitchStore]:
    store = InMemoryKillSwitchStore()
    return KillSwitchService(store), store


# ---------------------------------------------------------------------------
# 1. Constructor — poll-interval validation
# ---------------------------------------------------------------------------


def test_init_rejects_below_min_poll_interval() -> None:
    service, _ = _make_service()
    with pytest.raises(ValueError, match="poll_interval_seconds"):
        KillSwitchMonitor(service, poll_interval_seconds=MIN_POLL_INTERVAL_SECONDS / 2)


def test_init_rejects_above_max_poll_interval() -> None:
    service, _ = _make_service()
    with pytest.raises(ValueError, match="poll_interval_seconds"):
        KillSwitchMonitor(service, poll_interval_seconds=MAX_POLL_INTERVAL_SECONDS + 0.1)


def test_init_accepts_default_poll_interval() -> None:
    service, _ = _make_service()
    monitor = KillSwitchMonitor(service)
    assert monitor.is_running is False
    assert monitor.last_observed_state == KillSwitchState.INACTIVE
    # Sanity: the documented default lies in the allowed band.
    assert MIN_POLL_INTERVAL_SECONDS <= DEFAULT_POLL_INTERVAL_SECONDS <= MAX_POLL_INTERVAL_SECONDS


# ---------------------------------------------------------------------------
# 2. Lifecycle — start / stop idempotency
# ---------------------------------------------------------------------------


async def test_start_then_stop_runs_and_halts_poll_loop() -> None:
    service, _ = _make_service()
    monitor = KillSwitchMonitor(service, poll_interval_seconds=FAST_POLL)
    assert monitor.is_running is False
    await monitor.start()
    assert monitor.is_running is True
    await monitor.stop()
    assert monitor.is_running is False


async def test_start_is_idempotent() -> None:
    service, _ = _make_service()
    monitor = KillSwitchMonitor(service, poll_interval_seconds=FAST_POLL)
    await monitor.start()
    first_task = monitor._poll_task  # type: ignore[attr-defined]
    await monitor.start()
    second_task = monitor._poll_task  # type: ignore[attr-defined]
    assert first_task is second_task  # same task, no double-start
    await monitor.stop()


async def test_stop_without_start_is_noop() -> None:
    service, _ = _make_service()
    monitor = KillSwitchMonitor(service, poll_interval_seconds=FAST_POLL)
    await monitor.stop()  # must not raise


# ---------------------------------------------------------------------------
# 3. State-transition detection — INACTIVE → ACTIVE
# ---------------------------------------------------------------------------


async def test_monitor_tracks_state_changes() -> None:
    """Monitor's last_observed_state reflects poll results."""
    service, _ = _make_service()
    monitor = KillSwitchMonitor(service, poll_interval_seconds=FAST_POLL)
    await monitor.start()
    try:
        # Give monitor time to poll INACTIVE
        await asyncio.sleep(0.05)
        assert monitor.last_observed_state == KillSwitchState.INACTIVE

        await service.activate(
            KillSwitchState.HALT_ALL,
            reason="test",
            actor="test_monitor",
        )
        # Give monitor time to detect the transition
        await asyncio.sleep(0.05)
        assert monitor.last_observed_state == KillSwitchState.HALT_ALL

        await service.deactivate(reason="test done", actor="test_monitor")
        # Give monitor time to detect the deactivation
        await asyncio.sleep(0.05)
        assert monitor.last_observed_state == KillSwitchState.INACTIVE
    finally:
        await monitor.stop()


async def test_monitor_emits_alert_on_inactive_to_active_transition(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Alert fires when kill switch goes INACTIVE → HALT_*."""
    # Configure structlog to emit to caplog for testing
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
    )

    service, _ = _make_service()
    monitor = KillSwitchMonitor(service, poll_interval_seconds=FAST_POLL)
    await monitor.start()
    try:
        caplog.clear()
        with caplog.at_level("WARNING"):
            await service.activate(
                KillSwitchState.HALT_SUBMISSIONS,
                reason="test alert",
                actor="test_monitor",
            )
            # Wait for monitor to detect and log
            await asyncio.sleep(0.1)

        # Verify alert was logged
        alert_records = [
            r for r in caplog.records
            if "kill_switch.alert" in r.message
        ]
        assert len(alert_records) > 0, "Expected alert log record"
        assert any("halt_submissions" in r.message for r in alert_records)
    finally:
        await monitor.stop()


async def test_monitor_alert_latency_under_1_second() -> None:
    """SLA test: alert fires within 1s of activation (§10.4 requirement)."""
    service, _ = _make_service()
    # Use default poll interval (100ms) for realistic SLA measurement
    monitor = KillSwitchMonitor(service, poll_interval_seconds=0.1)

    # Capture logs
    captured_logs: list[dict] = []
    original_emit = monitor._emit_alert

    def mock_emit(state: KillSwitchState) -> None:
        captured_logs.append({"timestamp": time.monotonic(), "state": state})
        original_emit(state)

    monitor._emit_alert = mock_emit  # type: ignore[method-assign]

    await monitor.start()
    try:
        activation_time = time.monotonic()
        await service.activate(
            KillSwitchState.HALT_ALL,
            reason="SLA test",
            actor="test_monitor",
        )

        # Wait up to 1.5s for alert (gives margin but still tests <1s SLA)
        await asyncio.sleep(1.5)

        assert len(captured_logs) > 0, "Expected alert to fire"
        alert_time = captured_logs[0]["timestamp"]
        latency = alert_time - activation_time

        # SLA: must be under 1 second
        assert latency < 1.0, f"Alert latency {latency:.3f}s exceeds 1s SLA"
    finally:
        await monitor.stop()


async def test_monitor_does_not_alert_on_deactivation() -> None:
    """Alert only fires on INACTIVE → ACTIVE, not ACTIVE → INACTIVE."""
    service, _ = _make_service()
    monitor = KillSwitchMonitor(service, poll_interval_seconds=FAST_POLL)

    alert_count = 0

    def count_alerts(_: KillSwitchState) -> None:
        nonlocal alert_count
        alert_count += 1

    monitor._emit_alert = count_alerts  # type: ignore[method-assign]

    await monitor.start()
    try:
        # Activate
        await service.activate(
            KillSwitchState.HALT_SCANS,
            reason="test",
            actor="test_monitor",
        )
        await asyncio.sleep(0.05)
        assert alert_count == 1  # One alert on activation

        # Deactivate
        await service.deactivate(reason="test done", actor="test_monitor")
        await asyncio.sleep(0.05)
        assert alert_count == 1  # No additional alert on deactivation
    finally:
        await monitor.stop()


async def test_monitor_does_not_alert_on_active_to_active_transition() -> None:
    """No alert when transitioning between active states (e.g., HALT_SUBMISSIONS → HALT_ALL)."""
    service, _ = _make_service()
    monitor = KillSwitchMonitor(service, poll_interval_seconds=FAST_POLL)

    alert_count = 0

    def count_alerts(_: KillSwitchState) -> None:
        nonlocal alert_count
        alert_count += 1

    monitor._emit_alert = count_alerts  # type: ignore[method-assign]

    await monitor.start()
    try:
        # First activation
        await service.activate(
            KillSwitchState.HALT_SUBMISSIONS,
            reason="test",
            actor="test_monitor",
        )
        await asyncio.sleep(0.05)
        assert alert_count == 1

        # Escalate to HALT_ALL (still active, different tier)
        await service.activate(
            KillSwitchState.HALT_ALL,
            reason="escalate",
            actor="test_monitor",
        )
        await asyncio.sleep(0.05)
        assert alert_count == 1  # No new alert, state was already active
    finally:
        await monitor.stop()


async def test_monitor_resumes_alerting_after_deactivate_reactivate() -> None:
    """After INACTIVE → ACTIVE → INACTIVE cycle, the next INACTIVE → ACTIVE fires a new alert."""
    service, _ = _make_service()
    monitor = KillSwitchMonitor(service, poll_interval_seconds=FAST_POLL)

    alert_count = 0

    def count_alerts(_: KillSwitchState) -> None:
        nonlocal alert_count
        alert_count += 1

    monitor._emit_alert = count_alerts  # type: ignore[method-assign]

    await monitor.start()
    try:
        # First activation
        await service.activate(
            KillSwitchState.HALT_ALL,
            reason="incident 1",
            actor="test_monitor",
        )
        await asyncio.sleep(0.05)
        assert alert_count == 1

        # Deactivate
        await service.deactivate(reason="resolved", actor="test_monitor")
        await asyncio.sleep(0.05)
        assert alert_count == 1

        # Second activation (new incident)
        await service.activate(
            KillSwitchState.HALT_ALL,
            reason="incident 2",
            actor="test_monitor",
        )
        await asyncio.sleep(0.05)
        assert alert_count == 2  # New alert for new activation
    finally:
        await monitor.stop()


# ---------------------------------------------------------------------------
# 4. Error handling — fail-safe behavior
# ---------------------------------------------------------------------------


async def test_monitor_continues_on_poll_error() -> None:
    """If current_state() raises, monitor logs error and continues polling."""
    service, _ = _make_service()
    monitor = KillSwitchMonitor(service, poll_interval_seconds=FAST_POLL)

    # Mock service.current_state to raise once, then succeed
    call_count = 0
    original_current_state = service.current_state

    async def failing_current_state() -> KillSwitchState:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("simulated Redis failure")
        return await original_current_state()

    service.current_state = failing_current_state  # type: ignore[method-assign]

    await monitor.start()
    try:
        # Give monitor time to hit the error and then recover
        await asyncio.sleep(0.1)
        # Verify it's still running
        assert monitor.is_running is True
        # Verify it recovered and polled successfully
        assert call_count > 1, "Monitor should have retried after failure"
    finally:
        await monitor.stop()
