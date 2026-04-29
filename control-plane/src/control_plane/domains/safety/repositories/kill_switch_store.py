"""Persistence layer for the kill switch flag.

Layer 1 of the build-plan §6.6 design. The Protocol decouples the
service from the concrete backend — :class:`RedisKillSwitchStore` for
production (with 24h auto-expiring TTL so the flag is forced through a
human renewal), :class:`InMemoryKillSwitchStore` for tests.

The Redis key namespace follows build-plan §9.1.5:
``bountystrike:killswitch:{scope}`` with ``scope = global`` for solo mode
and ``scope = operator:{operator_id}`` for multi-tenant deployments.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from control_plane.domains.safety.value_objects import KillSwitchState

if TYPE_CHECKING:
    # Avoid hard import-time dependency on redis when only the in-memory
    # store is used (tests, dev, single-process tools).
    from redis.asyncio import Redis as AsyncRedis


_VALID_VALUES = {state.value for state in KillSwitchState if state != KillSwitchState.INACTIVE}


@runtime_checkable
class KillSwitchStore(Protocol):
    """Async store for the kill switch flag."""

    async def get_state(self) -> KillSwitchState: ...
    async def set_state(self, state: KillSwitchState, ttl_seconds: int) -> None: ...
    async def clear(self) -> None: ...


class InMemoryKillSwitchStore:
    """In-memory store — deterministic for tests, ephemeral for dev.

    NOT for production: state vanishes on process restart, and
    intentionally never leaves the address space.
    """

    def __init__(self) -> None:
        self._state: KillSwitchState = KillSwitchState.INACTIVE
        self._expires_at: float | None = None

    async def get_state(self) -> KillSwitchState:
        if (
            self._expires_at is not None
            and time.monotonic() >= self._expires_at
        ):
            self._state = KillSwitchState.INACTIVE
            self._expires_at = None
        return self._state

    async def set_state(self, state: KillSwitchState, ttl_seconds: int) -> None:
        if state == KillSwitchState.INACTIVE:
            await self.clear()
            return
        if ttl_seconds <= 0:
            raise ValueError(
                "ttl_seconds must be positive (kill switch must auto-expire)"
            )
        self._state = state
        self._expires_at = time.monotonic() + ttl_seconds

    async def clear(self) -> None:
        self._state = KillSwitchState.INACTIVE
        self._expires_at = None


class RedisKillSwitchStore:
    """Redis-backed store. Uses a single string key with EXPIRE.

    Args:
        client: An ``redis.asyncio.Redis`` client.
        key: Full Redis key. Defaults to ``bountystrike:killswitch:global``
            per build-plan §9.1.5.
    """

    def __init__(
        self,
        client: AsyncRedis,
        key: str = "bountystrike:killswitch:global",
    ) -> None:
        self._client = client
        self._key = key

    async def get_state(self) -> KillSwitchState:
        raw = await self._client.get(self._key)
        if raw is None:
            return KillSwitchState.INACTIVE
        value = raw.decode() if isinstance(raw, (bytes, bytearray)) else str(raw)
        if value not in _VALID_VALUES:
            # Garbage in Redis is treated as INACTIVE — fail safe in the
            # "fewer halts" direction. The supervisor's separate health
            # check should flag the malformed value.
            return KillSwitchState.INACTIVE
        return KillSwitchState(value)

    async def set_state(self, state: KillSwitchState, ttl_seconds: int) -> None:
        if state == KillSwitchState.INACTIVE:
            await self.clear()
            return
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        await self._client.set(self._key, state.value, ex=ttl_seconds)

    async def clear(self) -> None:
        await self._client.delete(self._key)


__all__ = [
    "InMemoryKillSwitchStore",
    "KillSwitchStore",
    "RedisKillSwitchStore",
]
