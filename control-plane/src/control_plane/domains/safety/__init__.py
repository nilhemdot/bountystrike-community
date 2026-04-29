"""Safety bounded context — kill switch + future emergency controls.

Public surface:

* :class:`KillSwitchState` — enum of allowed states.
* :class:`KillSwitchStore` — Protocol for persistence (Redis in prod,
  in-memory in tests).
* :func:`make_kill_switch_store` — composition root reading env.
* :class:`KillSwitchService` — activate / deactivate / check API used
  by hooks, the supervisor, and the orchestrator's pre-flight checks.
"""

from __future__ import annotations

from .repositories import (
    InMemoryKillSwitchStore,
    KillSwitchStore,
    RedisKillSwitchStore,
    make_kill_switch_store,
)
from .services import KillSwitchService
from .value_objects import KillSwitchState

__all__ = [
    "InMemoryKillSwitchStore",
    "KillSwitchService",
    "KillSwitchState",
    "KillSwitchStore",
    "RedisKillSwitchStore",
    "make_kill_switch_store",
]
