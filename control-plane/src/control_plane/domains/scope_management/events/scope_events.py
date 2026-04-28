"""Scope-change domain events.

Replaces the magic-string ``event_type ∈ {scope_added, scope_removed,
payout_changed, program_paused}`` previously living in
``workers/scope_ingest.py``. Events are emitted *in memory* by the ingest
service and then translated into ``scope_changes`` ORM rows; the DB column
``event_type`` keeps its existing string values via :func:`event_type_for`.

All events extend :class:`~control_plane.core.shared.DomainEvent` so they
inherit ``event_id`` / ``occurred_on`` / ``event_version`` for free.
"""

from __future__ import annotations

from typing import Any, ClassVar, Literal

from control_plane.core.shared import DomainEvent

ScopeChangeKind = Literal[
    "scope_added", "scope_removed", "payout_changed", "program_paused"
]


class ScopeChangedEvent(DomainEvent):
    """Base class for any change to a program's scope set.

    The ``aggregate_id`` is the program handle. Subclasses set
    :attr:`event_kind` to the wire-level string the ``scope_changes`` table
    stores.
    """

    event_kind: ClassVar[ScopeChangeKind]

    program_handle: str
    platform: str
    asset_identifier: str
    source: str
    old_value: dict[str, Any] | None = None
    new_value: dict[str, Any] | None = None


class ScopeAddedEvent(ScopeChangedEvent):
    """A new asset entered scope for the program."""

    event_kind: ClassVar[ScopeChangeKind] = "scope_added"


class ScopeRemovedEvent(ScopeChangedEvent):
    """An asset disappeared from the program's scope feed."""

    event_kind: ClassVar[ScopeChangeKind] = "scope_removed"


class PayoutChangedEvent(ScopeChangedEvent):
    """Bounty range / max-payout tag changed for an asset."""

    event_kind: ClassVar[ScopeChangeKind] = "payout_changed"


class ProgramPausedEvent(ScopeChangedEvent):
    """Asset flipped from in-scope to out-of-scope (program-wide pause indicator)."""

    event_kind: ClassVar[ScopeChangeKind] = "program_paused"


_EVENT_TYPES: tuple[type[ScopeChangedEvent], ...] = (
    ScopeAddedEvent,
    ScopeRemovedEvent,
    PayoutChangedEvent,
    ProgramPausedEvent,
)


def event_type_for(event: ScopeChangedEvent) -> ScopeChangeKind:
    """Return the wire-level string for the ``scope_changes.event_type`` column."""
    return event.event_kind


__all__ = [
    "PayoutChangedEvent",
    "ProgramPausedEvent",
    "ScopeAddedEvent",
    "ScopeChangedEvent",
    "ScopeChangeKind",
    "ScopeRemovedEvent",
    "event_type_for",
]
