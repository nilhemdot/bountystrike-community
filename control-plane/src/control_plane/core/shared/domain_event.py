"""Base domain event — emitted by aggregates when state transitions occur.

Events carry: unique id, aggregate id (the entity that emitted), timestamp,
event version (for schema evolution).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field


class DomainEvent(BaseModel):
    """Immutable domain event. Subclasses add event-specific payload."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    aggregate_id: str
    occurred_on: datetime = Field(default_factory=lambda: datetime.now(UTC))
    event_version: int = 1
