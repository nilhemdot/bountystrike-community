# SPDX-License-Identifier: AGPL-3.0-or-later

"""Safety bounded context — kill switch + future emergency controls.

Public surface:

* :class:`KillSwitchState` — enum of allowed states.
* :class:`KillSwitchStore` — Protocol for persistence (Redis in prod,
  in-memory in tests).
* :func:`make_kill_switch_store` — composition root reading env.
* :class:`KillSwitchService` — activate / deactivate / check API used
  by hooks, the supervisor, and the orchestrator's pre-flight checks.
* :class:`KillSwitchMonitor` — state-transition monitor for alerting.
"""

from __future__ import annotations

from .monitoring import KillSwitchMonitor
from .repositories import (
    InMemoryKillSwitchStore,
    KillSwitchStore,
    RedisKillSwitchStore,
    make_kill_switch_store,
)
from .services import (
    AgentSupervisor,
    KillSwitchService,
    WorkerScope,
)
from .value_objects import KillSwitchState

__all__ = [
    "AgentSupervisor",
    "InMemoryKillSwitchStore",
    "KillSwitchMonitor",
    "KillSwitchService",
    "KillSwitchState",
    "KillSwitchStore",
    "RedisKillSwitchStore",
    "WorkerScope",
    "make_kill_switch_store",
]
