# SPDX-License-Identifier: AGPL-3.0-or-later

"""Domain events emitted by the scope_management bounded context."""

from __future__ import annotations

from .scope_events import (
    PayoutChangedEvent,
    ProgramPausedEvent,
    ScopeAddedEvent,
    ScopeChangedEvent,
    ScopeRemovedEvent,
    event_type_for,
)

__all__ = [
    "PayoutChangedEvent",
    "ProgramPausedEvent",
    "ScopeAddedEvent",
    "ScopeChangedEvent",
    "ScopeRemovedEvent",
    "event_type_for",
]
