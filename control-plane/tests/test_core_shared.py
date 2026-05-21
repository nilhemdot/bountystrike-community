"""Tests for core/shared base classes."""

from __future__ import annotations

import pytest
from control_plane.core.shared import AggregateRoot, DomainEvent, ValueObject
from pydantic import ValidationError


class _Coords(ValueObject):
    x: int
    y: int


class _ItemAdded(DomainEvent):
    item_id: str


class _Cart(AggregateRoot[str]):
    def __init__(self, cart_id: str) -> None:
        super().__init__(cart_id)
        self._items: list[str] = []

    @property
    def items(self) -> list[str]:
        return list(self._items)

    def add_item(self, item_id: str) -> None:
        self._items.append(item_id)
        self._record_event(_ItemAdded(aggregate_id=self.id, item_id=item_id))


def test_value_object_is_frozen():
    a = _Coords(x=1, y=2)
    with pytest.raises(ValidationError):
        a.x = 99  # type: ignore[misc]


def test_value_object_equality_by_value():
    assert _Coords(x=1, y=2) == _Coords(x=1, y=2)
    assert _Coords(x=1, y=2) != _Coords(x=1, y=3)


def test_value_object_hashable():
    # frozen Pydantic models are hashable at runtime even though BaseModel
    # declares __hash__ = None in its stubs.
    pair = {_Coords(x=1, y=2), _Coords(x=1, y=2)}  # pyright: ignore[reportUnhashable]
    assert len(pair) == 1


def test_domain_event_carries_metadata():
    event = _ItemAdded(aggregate_id="cart-1", item_id="sku-9")
    assert event.aggregate_id == "cart-1"
    assert event.item_id == "sku-9"
    assert event.event_id  # uuid v4
    assert event.event_version == 1
    assert event.occurred_on


def test_aggregate_records_and_pulls_events():
    cart = _Cart("cart-1")
    cart.add_item("sku-9")
    cart.add_item("sku-10")

    assert cart.version == 2
    events = cart.pull_events()

    assert len(events) == 2
    assert all(isinstance(e, _ItemAdded) for e in events)
    assert cart.pull_events() == []  # cleared after pull


def test_aggregate_equality_by_type_and_id():
    cart_a = _Cart("cart-1")
    cart_b = _Cart("cart-1")
    cart_c = _Cart("cart-2")

    assert cart_a == cart_b
    assert cart_a != cart_c
    assert hash(cart_a) == hash(cart_b)
