# SPDX-License-Identifier: AGPL-3.0-or-later

"""Repositories for the safety bounded context."""

from __future__ import annotations

from .factory import make_kill_switch_store
from .kill_switch_store import (
    InMemoryKillSwitchStore,
    KillSwitchStore,
    RedisKillSwitchStore,
)

__all__ = [
    "InMemoryKillSwitchStore",
    "KillSwitchStore",
    "RedisKillSwitchStore",
    "make_kill_switch_store",
]
