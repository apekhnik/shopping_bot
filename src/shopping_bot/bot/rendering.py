from __future__ import annotations

from decimal import Decimal
from html import escape

from shopping_bot.db.models import ProductState
from shopping_bot.scheduler.events import EventType, PriceEvent
from shopping_bot.sources.base import ProductSnapshot

_URL_BASE = {
    "varus": "https://varus.ua/",
}

_IMG_URL_BUILDER = {
    # Varus serves per-SKU webp at https://varus.ua/img/product/{w}/{h}/{sku}
    # 670x670 balances quality vs bandwidth for Telegram cards.
    "varus": lambda sku, size=670: f"https://varus.ua/img/product/{size}/{size}/{sku}",
}


def product_image_url(source: str, sku: str, size: int = 670) -> str | None:
    builder = _IMG_URL_BUILDER.get(source)
    return builder(sku, size) if builder else None


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


_NAME_MAX = 30


def _truncate_name(name: str) -> str:
    if len(name) <= _NAME_MAX:
        return name
    return name[: _NAME_MAX - 1].rstrip() + "…"


def _price_cell(value: Decimal | float | None) -> str:
    """8-char right-aligned price column, ending in '₴'."""
    if value is None:
        return "       —"
    return f"{Decimal(value):>7.2f}₴"


def _watchlist_table_row(
    pos: int,
    source: str,
    name: str,
    url_key: str | None,
    state: ProductState | None,
) -> str:
    """Two-line pre-block chunk for one watchlist item.

    Layout inside <pre>:
      "  1. -38% │  34.90₴ │ було 55.90₴"
      "     <a href=...>Напій Revo Кокос 500 мл</a>"
    Widths are tuned for ~30-column mobile monospace.
    """
    disc_col = (
        f"-{state.discount_percent}%".rjust(5)
        if state and state.discount_percent
        else "     "
    )
    price = _price_cell(
        state.special_price if state and state.special_price else (state.price if state else None)
    )

    if state is None:
        note = "не сканували"
    elif state.discount_percent and state.special_price:
        note = f"було {Decimal(state.price):.2f}₴"
    elif not state.in_stock:
        note = "немає"
    else:
        note = "без знижки"

    head = f"{pos:>2}. {disc_col} │ {price} │ {note}"

    name_escaped = escape(_truncate_name(name))
    url = product_url(source, url_key)
    name_line = (
        f'   <a href="{escape(url)}">{name_escaped}</a>' if url else f"   {name_escaped}"
    )
    return f"{head}\n{name_line}"


def render_watchlist_row(source: str, sku: str, name: str, url_key: str | None,
                        state: ProductState | None) -> str:
    """Kept for tests / future single-item views (event messages, etc)."""
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


def render_watchlist_table(
    items: list[tuple[int, str, str, str | None, ProductState | None]],
) -> str:
    """Full /list message body wrapped in one <pre> block.

    items = list of (pos_1based, source, name, url_key, state).
    """
    parts = [f"Твій список ({len(items)}):", ""]
    for pos, source, name, url_key, state in items:
        parts.append(_watchlist_table_row(pos, source, name, url_key, state))
        parts.append("")
    inner = "\n".join(parts).rstrip()
    return f"<pre>{inner}</pre>"


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
