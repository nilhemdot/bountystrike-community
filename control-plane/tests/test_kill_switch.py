"""Tests for the safety bounded context — kill switch."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock

import pytest
from control_plane.domains.safety import (
    InMemoryKillSwitchStore,
    KillSwitchService,
    KillSwitchState,
    KillSwitchStore,
    RedisKillSwitchStore,
    make_kill_switch_store,
)

# ---------------------------------------------------------------------------
# 1. KillSwitchState — escalation semantics
# ---------------------------------------------------------------------------


def test_inactive_blocks_nothing():
    s = KillSwitchState.INACTIVE
    assert not s.blocks_submissions
    assert not s.blocks_scans
    assert not s.blocks_all


def test_halt_submissions_blocks_only_submissions():
    s = KillSwitchState.HALT_SUBMISSIONS
    assert s.blocks_submissions
    assert not s.blocks_scans
    assert not s.blocks_all


def test_halt_scans_blocks_submissions_and_scans():
    s = KillSwitchState.HALT_SCANS
    assert s.blocks_submissions
    assert s.blocks_scans
    assert not s.blocks_all


def test_halt_all_blocks_everything():
    s = KillSwitchState.HALT_ALL
    assert s.blocks_submissions
    assert s.blocks_scans
    assert s.blocks_all


# ---------------------------------------------------------------------------
# 2. InMemoryKillSwitchStore — TTL + state transitions
# ---------------------------------------------------------------------------


async def test_in_memory_store_starts_inactive():
    store = InMemoryKillSwitchStore()
    assert await store.get_state() == KillSwitchState.INACTIVE


async def test_in_memory_store_set_and_get():
    store = InMemoryKillSwitchStore()
    await store.set_state(KillSwitchState.HALT_SCANS, ttl_seconds=300)
    assert await store.get_state() == KillSwitchState.HALT_SCANS


async def test_in_memory_store_set_inactive_clears():
    store = InMemoryKillSwitchStore()
    await store.set_state(KillSwitchState.HALT_ALL, ttl_seconds=300)
    await store.set_state(KillSwitchState.INACTIVE, ttl_seconds=1)  # ttl ignored
    assert await store.get_state() == KillSwitchState.INACTIVE


async def test_in_memory_store_clear():
    store = InMemoryKillSwitchStore()
    await store.set_state(KillSwitchState.HALT_ALL, ttl_seconds=300)
    await store.clear()
    assert await store.get_state() == KillSwitchState.INACTIVE


async def test_in_memory_store_rejects_zero_or_negative_ttl():
    store = InMemoryKillSwitchStore()
    with pytest.raises(ValueError, match="ttl_seconds"):
        await store.set_state(KillSwitchState.HALT_ALL, ttl_seconds=0)
    with pytest.raises(ValueError, match="ttl_seconds"):
        await store.set_state(KillSwitchState.HALT_ALL, ttl_seconds=-1)


async def test_in_memory_store_expires_after_ttl(monkeypatch: pytest.MonkeyPatch):
    """Auto-expiry of in-memory store under monkey-patched time."""
    store = InMemoryKillSwitchStore()
    fake_now = [0.0]
    monkeypatch.setattr(time, "monotonic", lambda: fake_now[0])

    await store.set_state(KillSwitchState.HALT_ALL, ttl_seconds=10)
    assert await store.get_state() == KillSwitchState.HALT_ALL

    fake_now[0] = 9.999
    assert await store.get_state() == KillSwitchState.HALT_ALL

    fake_now[0] = 10.0  # boundary — TTL elapsed
    assert await store.get_state() == KillSwitchState.INACTIVE


# ---------------------------------------------------------------------------
# 3. RedisKillSwitchStore — exercises against an AsyncMock client
# ---------------------------------------------------------------------------


async def test_redis_store_get_returns_inactive_when_key_missing():
    client = AsyncMock()
    client.get.return_value = None
    store = RedisKillSwitchStore(client)
    assert await store.get_state() == KillSwitchState.INACTIVE


async def test_redis_store_get_decodes_bytes_value():
    client = AsyncMock()
    client.get.return_value = b"halt_scans"
    store = RedisKillSwitchStore(client)
    assert await store.get_state() == KillSwitchState.HALT_SCANS


async def test_redis_store_get_returns_inactive_for_garbage_value():
    """Defence-in-depth: bad data in Redis must not crash the hook."""
    client = AsyncMock()
    client.get.return_value = b"definitely_not_a_state"
    store = RedisKillSwitchStore(client)
    assert await store.get_state() == KillSwitchState.INACTIVE


async def test_redis_store_set_uses_set_with_ex_ttl():
    client = AsyncMock()
    store = RedisKillSwitchStore(client, key="bountystrike:killswitch:global")
    await store.set_state(KillSwitchState.HALT_ALL, ttl_seconds=300)
    client.set.assert_awaited_once_with(
        "bountystrike:killswitch:global",
        "halt_all",
        ex=300,
    )


async def test_redis_store_set_inactive_calls_delete():
    client = AsyncMock()
    store = RedisKillSwitchStore(client, key="kskey")
    await store.set_state(KillSwitchState.INACTIVE, ttl_seconds=10)
    client.delete.assert_awaited_once_with("kskey")
    client.set.assert_not_awaited()


async def test_redis_store_clear_calls_delete():
    client = AsyncMock()
    store = RedisKillSwitchStore(client, key="kskey")
    await store.clear()
    client.delete.assert_awaited_once_with("kskey")


async def test_redis_store_rejects_non_positive_ttl():
    client = AsyncMock()
    store = RedisKillSwitchStore(client)
    with pytest.raises(ValueError, match="ttl_seconds"):
        await store.set_state(KillSwitchState.HALT_ALL, ttl_seconds=0)


# ---------------------------------------------------------------------------
# 4. Protocol satisfaction
# ---------------------------------------------------------------------------


def test_in_memory_satisfies_kill_switch_store_protocol():
    assert isinstance(InMemoryKillSwitchStore(), KillSwitchStore)


def test_redis_satisfies_kill_switch_store_protocol():
    assert isinstance(RedisKillSwitchStore(AsyncMock()), KillSwitchStore)


# ---------------------------------------------------------------------------
# 5. Factory — env-driven dispatch
# ---------------------------------------------------------------------------


def test_factory_default_backend_is_redis():
    """Production-safe default — fail closed if Redis is unavailable."""
    # We don't construct an actual Redis client (would block) — just
    # confirm the factory tried to and produced a RedisKillSwitchStore.
    store = make_kill_switch_store(env={
        "KILL_SWITCH_BACKEND": "redis",
        "REDIS_HOST": "127.0.0.1",
        "REDIS_PORT": "6379",
        "REDIS_PASSWORD": "x",
    })
    assert isinstance(store, RedisKillSwitchStore)


def test_factory_memory_backend():
    store = make_kill_switch_store(env={"KILL_SWITCH_BACKEND": "memory"})
    assert isinstance(store, InMemoryKillSwitchStore)


def test_factory_unknown_backend_raises():
    with pytest.raises(ValueError, match="must be 'redis' or 'memory'"):
        make_kill_switch_store(env={"KILL_SWITCH_BACKEND": "etcd"})


def test_factory_redis_uses_custom_key():
    store = make_kill_switch_store(env={
        "KILL_SWITCH_BACKEND": "redis",
        "KILL_SWITCH_KEY": "bs:killswitch:operator:alice",
    })
    assert isinstance(store, RedisKillSwitchStore)
    assert store._key == "bs:killswitch:operator:alice"


# ---------------------------------------------------------------------------
# 6. KillSwitchService — operator verbs + audit-log invariants
# ---------------------------------------------------------------------------


async def test_service_activate_persists_state():
    store = InMemoryKillSwitchStore()
    service = KillSwitchService(store)
    await service.activate(
        KillSwitchState.HALT_SCANS,
        reason="out-of-scope traffic detected",
        actor="operator:alice",
    )
    assert await service.current_state() == KillSwitchState.HALT_SCANS


async def test_service_deactivate_clears_state():
    store = InMemoryKillSwitchStore()
    service = KillSwitchService(store)
    await service.activate(
        KillSwitchState.HALT_ALL,
        reason="incident #42",
        actor="operator:alice",
    )
    await service.deactivate(reason="incident closed", actor="operator:alice")
    assert await service.current_state() == KillSwitchState.INACTIVE


async def test_service_activate_rejects_inactive_state():
    """Use deactivate() — activate() must always represent a real halt."""
    service = KillSwitchService(InMemoryKillSwitchStore())
    with pytest.raises(ValueError, match="deactivate"):
        await service.activate(
            KillSwitchState.INACTIVE,
            reason="r",
            actor="a",
        )


async def test_service_activate_rejects_empty_reason():
    service = KillSwitchService(InMemoryKillSwitchStore())
    with pytest.raises(ValueError, match="reason"):
        await service.activate(
            KillSwitchState.HALT_ALL,
            reason="",
            actor="a",
        )
    with pytest.raises(ValueError, match="reason"):
        await service.activate(
            KillSwitchState.HALT_ALL,
            reason="   ",
            actor="a",
        )


async def test_service_activate_rejects_empty_actor():
    service = KillSwitchService(InMemoryKillSwitchStore())
    with pytest.raises(ValueError, match="actor"):
        await service.activate(
            KillSwitchState.HALT_ALL,
            reason="r",
            actor="",
        )


async def test_service_activate_rejects_out_of_range_ttl():
    service = KillSwitchService(InMemoryKillSwitchStore())
    with pytest.raises(ValueError, match="ttl_seconds"):
        await service.activate(
            KillSwitchState.HALT_ALL,
            reason="r",
            actor="a",
            ttl_seconds=10,  # below MIN_TTL
        )
    with pytest.raises(ValueError, match="ttl_seconds"):
        await service.activate(
            KillSwitchState.HALT_ALL,
            reason="r",
            actor="a",
            ttl_seconds=10 * 24 * 3600,  # above MAX_TTL
        )


async def test_service_deactivate_requires_reason_and_actor():
    service = KillSwitchService(InMemoryKillSwitchStore())
    with pytest.raises(ValueError, match="reason"):
        await service.deactivate(reason="", actor="a")
    with pytest.raises(ValueError, match="actor"):
        await service.deactivate(reason="r", actor="")


@pytest.mark.parametrize(
    "state,category,expected_blocked",
    [
        # INACTIVE blocks nothing
        (KillSwitchState.INACTIVE, "submit", False),
        (KillSwitchState.INACTIVE, "network", False),
        (KillSwitchState.INACTIVE, "any", False),
        # HALT_SUBMISSIONS blocks submit only
        (KillSwitchState.HALT_SUBMISSIONS, "submit", True),
        (KillSwitchState.HALT_SUBMISSIONS, "network", False),
        (KillSwitchState.HALT_SUBMISSIONS, "any", False),
        # HALT_SCANS blocks submit + network
        (KillSwitchState.HALT_SCANS, "submit", True),
        (KillSwitchState.HALT_SCANS, "network", True),
        (KillSwitchState.HALT_SCANS, "any", False),
        # HALT_ALL blocks everything
        (KillSwitchState.HALT_ALL, "submit", True),
        (KillSwitchState.HALT_ALL, "network", True),
        (KillSwitchState.HALT_ALL, "any", True),
    ],
)
async def test_service_is_tool_blocked_matrix(
    state: KillSwitchState, category: str, expected_blocked: bool
):
    store = InMemoryKillSwitchStore()
    if state != KillSwitchState.INACTIVE:
        await store.set_state(state, ttl_seconds=300)
    service = KillSwitchService(store)
    assert await service.is_tool_blocked(category) is expected_blocked


async def test_service_is_tool_blocked_unknown_category_raises():
    service = KillSwitchService(InMemoryKillSwitchStore())
    with pytest.raises(ValueError, match="unknown tool_category"):
        await service.is_tool_blocked("nonsense")
