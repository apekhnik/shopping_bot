from __future__ import annotations

from decimal import Decimal
from html import escape

from shopping_bot.db.models import ProductState
from shopping_bot.scheduler.events import EventType, PriceEvent
from shopping_bot.sources.base import ProductSnapshot

_URL_BASE = {
    "varus": "https://varus.ua/",
}


def _money(value: Decimal | float | None) -> str:
    if value is None:
        return "—"
    return f"{Decimal(value):.2f} ₴"


def product_url(source: str, url_key: str | None) -> str | None:
    base = _URL_BASE.get(source)
    if not base or not url_key:
        return None
    return f"{base}{url_key}"


def render_search_hit(snap: ProductSnapshot) -> str:
    """One card in the /add search results."""
    name = escape(snap.name)
    lines = [f"<b>{name}</b>"]
    if snap.brand:
        lines[0] = f"<b>{name}</b>\n<i>{escape(snap.brand)}</i>"

    if snap.is_discounted and snap.special_price is not None:
        lines.append(
            f"<b>−{snap.discount_percent}%</b>  {_money(snap.special_price)}  "
            f"<s>{_money(snap.price)}</s>"
        )
        if snap.special_price_to_date:
            lines.append(f"акція до {snap.special_price_to_date.isoformat()}")
    else:
        lines.append(f"{_money(snap.price)}  ·  без знижки зараз")

    url = product_url(snap.source, snap.url_key)
    if url:
        lines.append(f'<a href="{escape(url)}">відкрити на сайті</a>')

    if not snap.in_stock:
        lines.append("<i>немає в наявності</i>")

    return "\n".join(lines)


def render_watchlist_row(source: str, sku: str, name: str, url_key: str | None,
                        state: ProductState | None) -> str:
    """One line in /list output (single-message layout)."""
    name_escaped = escape(name)
    url = product_url(source, url_key)
    name_html = f'<a href="{escape(url)}">{name_escaped}</a>' if url else f"<b>{name_escaped}</b>"

    if state is None:
        return f"{name_html}\n  <i>ще не сканували</i>"

    if state.discount_percent and state.discount_percent > 0 and state.special_price:
        head = (
            f"<b>−{state.discount_percent}%</b>  {name_html}\n"
            f"  {_money(state.special_price)}  <s>{_money(state.price)}</s>"
        )
    else:
        head = f"{name_html}\n  {_money(state.price)}  ·  без знижки"

    if not state.in_stock:
        head += "  ·  немає"
    return head


def render_event(event: PriceEvent) -> str:
    snap = event.snapshot
    name = escape(snap.name)
    url = product_url(snap.source, snap.url_key)
    url_line = f'\n<a href="{escape(url)}">відкрити на сайті</a>' if url else ""

    if event.event_type is EventType.DISCOUNT_STARTED:
        head = f"🔥 <b>Нова знижка −{event.new_discount_percent}%</b>"
        body = (
            f"{name}\n{_money(snap.special_price)} <s>{_money(snap.price)}</s>"
        )
    elif event.event_type is EventType.DISCOUNT_DEEPENED:
        head = (
            f"🔥 <b>Знижка збільшилась: −{event.new_discount_percent}%</b>"
            f" (було −{event.old_discount_percent}%)"
        )
        body = (
            f"{name}\n{_money(snap.special_price)} <s>{_money(snap.price)}</s>"
        )
    elif event.event_type is EventType.DISCOUNT_ENDED:
        head = "Акція закінчилась"
        body = f"{name}\nЗараз: {_money(snap.price)}"
    else:  # pragma: no cover
        head = "Оновлення"
        body = name

    tail = ""
    if snap.special_price_to_date and event.event_type is not EventType.DISCOUNT_ENDED:
        tail = f"\nдо {snap.special_price_to_date.isoformat()}"

    return f"{head}\n{body}{tail}{url_line}"
