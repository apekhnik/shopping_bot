from __future__ import annotations

from datetime import date
from decimal import Decimal

from shopping_bot.db.models import ProductState
from shopping_bot.scheduler.events import EventType, detect_event
from shopping_bot.sources.base import ProductSnapshot


def _snap(discount: int | None, price: str = "100.00", special: str | None = None) -> ProductSnapshot:
    return ProductSnapshot(
        source="varus",
        sku="X",
        shop_id=57,
        name="Product X",
        url_key="product-x",
        brand="B",
        price=Decimal(price),
        special_price=Decimal(special) if special else None,
        discount_percent=discount,
        special_price_to_date=date(2026, 12, 31) if discount else None,
        in_stock=True,
    )


def _state(discount: int | None, price: str = "100.00", special: str | None = None) -> ProductState:
    return ProductState(
        source="varus",
        sku="X",
        shop_id=57,
        price=Decimal(price),
        special_price=Decimal(special) if special else None,
        discount_percent=discount,
        special_price_to_date=None,
        in_stock=True,
    )


def test_no_prev_no_discount_emits_nothing() -> None:
    assert detect_event(None, _snap(discount=None)) is None


def test_no_prev_but_discounted_emits_started() -> None:
    event = detect_event(None, _snap(discount=25, special="75.00"))
    assert event is not None
    assert event.event_type is EventType.DISCOUNT_STARTED
    assert event.new_discount_percent == 25
    assert event.old_discount_percent is None


def test_discount_deepens() -> None:
    event = detect_event(_state(discount=10), _snap(discount=25, special="75.00"))
    assert event is not None
    assert event.event_type is EventType.DISCOUNT_DEEPENED
    assert event.old_discount_percent == 10
    assert event.new_discount_percent == 25


def test_same_discount_no_event() -> None:
    assert detect_event(_state(discount=15), _snap(discount=15, special="85.00")) is None


def test_discount_shrinks_no_event() -> None:
    # Product-getting-more-expensive is intentionally NOT surfaced (MVP).
    assert detect_event(_state(discount=25), _snap(discount=10, special="90.00")) is None


def test_discount_ended() -> None:
    event = detect_event(_state(discount=25, special="75.00"), _snap(discount=None))
    assert event is not None
    assert event.event_type is EventType.DISCOUNT_ENDED
    assert event.new_discount_percent is None
    assert event.old_discount_percent == 25


def test_zero_discount_treated_as_no_discount() -> None:
    # Some sources report 0% instead of null. Should behave like "no promo".
    assert detect_event(None, _snap(discount=0)) is None
    assert detect_event(_state(discount=0), _snap(discount=15, special="85.00")).event_type is EventType.DISCOUNT_STARTED
