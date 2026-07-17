from __future__ import annotations

from datetime import date
from decimal import Decimal

from shopping_bot.bot.rendering import (
    product_image_url,
    product_url,
    render_event,
    render_search_hit,
    render_watchlist_row,
)
from shopping_bot.db.models import ProductState
from shopping_bot.scheduler.events import EventType, PriceEvent
from shopping_bot.sources.base import ProductSnapshot


def _snap(discount: int | None = 25) -> ProductSnapshot:
    return ProductSnapshot(
        source="varus",
        sku="X",
        shop_id=57,
        name="Молоко <тест> 1 л",
        url_key="moloko-test-1l",
        brand="Брендик",
        price=Decimal("99.00"),
        special_price=Decimal("74.25") if discount else None,
        discount_percent=discount,
        special_price_to_date=date(2026, 12, 31) if discount else None,
        in_stock=True,
    )


def test_product_url_uses_source_base() -> None:
    assert product_url("varus", "kokosove-moloko") == "https://varus.ua/kokosove-moloko"
    assert product_url("varus", None) is None
    assert product_url("unknown", "x") is None


def test_product_image_url_varus_pattern() -> None:
    assert (
        product_image_url("varus", "2615912")
        == "https://varus.ua/img/product/670/670/2615912"
    )
    assert (
        product_image_url("varus", "2615912", size=300)
        == "https://varus.ua/img/product/300/300/2615912"
    )
    assert product_image_url("unknown", "x") is None


def test_render_search_hit_escapes_html_and_includes_discount() -> None:
    text = render_search_hit(_snap(discount=25))
    assert "&lt;тест&gt;" in text
    assert "−25%" in text
    assert "74.25" in text
    assert "<s>" in text  # crossed-out regular price
    assert "відкрити на сайті" in text


def test_render_search_hit_no_discount() -> None:
    text = render_search_hit(_snap(discount=None))
    assert "без знижки зараз" in text
    assert "99.00" in text
    assert "−" not in text.split("\n")[1] if len(text.split("\n")) > 1 else True


def test_render_watchlist_row_unscanned() -> None:
    text = render_watchlist_row("varus", "X", "Товар <ok>", "url-key", None)
    assert "ще не сканували" in text
    assert "&lt;ok&gt;" in text


def test_render_event_started() -> None:
    event = PriceEvent(
        source="varus", sku="X", shop_id=57,
        event_type=EventType.DISCOUNT_STARTED,
        old_discount_percent=None,
        new_discount_percent=25,
        old_price=None,
        new_price=Decimal("74.25"),
        snapshot=_snap(discount=25),
    )
    text = render_event(event)
    assert "Нова знижка" in text
    assert "−25%" in text


def test_render_event_ended() -> None:
    event = PriceEvent(
        source="varus", sku="X", shop_id=57,
        event_type=EventType.DISCOUNT_ENDED,
        old_discount_percent=25,
        new_discount_percent=None,
        old_price=Decimal("74.25"),
        new_price=Decimal("99.00"),
        snapshot=_snap(discount=None),
    )
    text = render_event(event)
    assert "Акція закінчилась" in text
    assert "99.00" in text
