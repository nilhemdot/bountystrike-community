"""Base value object — immutable, equality by value (not identity).

Pydantic v2 with frozen=True gives us hashing + structural equality for free.
Subclasses inherit immutability + JSON serialization + validation.
"""

from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, ConfigDict


class ValueObject(BaseModel):
    """Frozen Pydantic model — all subclasses are immutable value objects.

    Equality compares all fields. Hashable. Safe for set membership and dict keys.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)
