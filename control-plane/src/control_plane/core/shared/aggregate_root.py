"""Base aggregate root — entity that owns a consistency boundary and emits events.

Aggregates are the only writable units in the domain. Repositories load and save
aggregates. State changes happen via methods on the aggregate; methods append
domain events to the uncommitted event list. After persistence, events are
published to the event bus and the list is cleared.
"""

from __future__ import annotations

from abc import ABC

from .domain_event import DomainEvent


class AggregateRoot[IdType](ABC):
    """Mutable entity owning a consistency boundary.

    NOT a Pydantic model — aggregates carry mutable state and behavior.
    Subclasses must set ``self._id`` in their constructor.
    """

    _id: IdType
    _version: int
    _uncommitted_events: list[DomainEvent]

    def __init__(self, aggregate_id: IdType) -> None:
        self._id = aggregate_id
        self._version = 0
        self._uncommitted_events = []

    @property
    def id(self) -> IdType:
        return self._id

    @property
    def version(self) -> int:
        return self._version

    def _record_event(self, event: DomainEvent) -> None:
        self._uncommitted_events.append(event)
        self._version += 1

    def pull_events(self) -> list[DomainEvent]:
        """Return uncommitted events and clear the buffer.

        Caller (typically a repository or use case) is responsible for publishing
        them after the aggregate is persisted.
        """
        events = list(self._uncommitted_events)
        self._uncommitted_events.clear()
        return events

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, AggregateRoot):
            return NotImplemented
        return type(self) is type(other) and self._id == other._id

    def __hash__(self) -> int:
        return hash((type(self).__name__, self._id))
