"""Composition root for the kill switch store.

Picks an implementation from environment variables. Call once at
application startup and inject into :class:`KillSwitchService`.

Env contract::

    KILL_SWITCH_BACKEND     "redis" (default in prod) | "memory"
    KILL_SWITCH_KEY         Redis key (default: bountystrike:killswitch:global)
    REDIS_HOST              default "127.0.0.1"
    REDIS_PORT              default 6379
    REDIS_PASSWORD          required by docker-compose; pass-through to client
    REDIS_DB                default 0
"""

from __future__ import annotations

import os

from .kill_switch_store import (
    InMemoryKillSwitchStore,
    KillSwitchStore,
    RedisKillSwitchStore,
)


def make_kill_switch_store(env: dict[str, str] | None = None) -> KillSwitchStore:
    """Return the concrete kill switch store selected by env.

    Args:
        env: Optional env mapping (defaults to ``os.environ``).

    Raises:
        ValueError: when ``KILL_SWITCH_BACKEND`` is set to an unknown
            value, or ``redis`` is requested but the ``redis`` package
            is not installed.
    """
    e = dict(env if env is not None else os.environ)
    backend = (e.get("KILL_SWITCH_BACKEND") or "redis").strip().lower()

    if backend == "memory":
        return InMemoryKillSwitchStore()

    if backend == "redis":
        try:
            from redis.asyncio import Redis as AsyncRedis
        except ImportError as exc:
            raise ValueError(
                "KILL_SWITCH_BACKEND=redis requires the 'redis' package "
                "(pip install redis>=5.0)"
            ) from exc

        client = AsyncRedis(
            host=e.get("REDIS_HOST", "127.0.0.1"),
            port=int(e.get("REDIS_PORT", "6379")),
            password=e.get("REDIS_PASSWORD") or None,
            db=int(e.get("REDIS_DB", "0")),
            decode_responses=False,  # store binary; we decode in get_state
        )
        return RedisKillSwitchStore(
            client=client,
            key=e.get("KILL_SWITCH_KEY", "bountystrike:killswitch:global"),
        )

    raise ValueError(
        f"KILL_SWITCH_BACKEND must be 'redis' or 'memory', got {backend!r}"
    )


__all__ = ["make_kill_switch_store"]
