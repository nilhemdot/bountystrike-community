"""Shared kernel — domain primitives reused across bounded contexts."""

from .aggregate_root import AggregateRoot
from .domain_event import DomainEvent
from .value_object import ValueObject

__all__ = ["AggregateRoot", "DomainEvent", "ValueObject"]
