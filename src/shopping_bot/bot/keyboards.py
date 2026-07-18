from __future__ import annotations

from aiogram.filters.callback_data import CallbackData
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

BTN_ADD = "➕ Додати"
BTN_LIST = "📋 Мій список"
BTN_RANDOM_SNACK = "🎲 Випадковий снек"


def main_menu() -> ReplyKeyboardMarkup:
    """Persistent bottom keyboard shown to registered users."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_ADD), KeyboardButton(text=BTN_LIST)],
            [KeyboardButton(text=BTN_RANDOM_SNACK)],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


class TrackCallback(CallbackData, prefix="trk"):
    source: str
    sku: str
    shop_id: int


class UntrackCallback(CallbackData, prefix="untrk"):
    watched_id: int


def buy_row(product_page_url: str | None) -> list[InlineKeyboardButton]:
    """Row with a single 'Купити в Varus' URL button. Empty if no URL."""
    if not product_page_url:
        return []
    return [InlineKeyboardButton(text="🛒 Купити в Varus", url=product_page_url)]


def search_hit_keyboard(
    source: str, sku: str, shop_id: int, product_page_url: str | None
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    buy = buy_row(product_page_url)
    if buy:
        rows.append(buy)
    rows.append([
        InlineKeyboardButton(
            text="🔔 Відстежувати",
            callback_data=TrackCallback(source=source, sku=sku, shop_id=shop_id).pack(),
        )
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def buy_keyboard(product_page_url: str | None) -> InlineKeyboardMarkup | None:
    row = buy_row(product_page_url)
    if not row:
        return None
    return InlineKeyboardMarkup(inline_keyboard=[row])


def untrack_button(watched_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(
                text="🗑 Прибрати",
                callback_data=UntrackCallback(watched_id=watched_id).pack(),
            )
        ]]
    )


def watchlist_untrack_row(items: list[tuple[int, int]]) -> InlineKeyboardMarkup:
    """Grid of numbered 🗑 buttons for the /list summary message.

    items = list of (position_1_based, watched_id).
    Wraps to 5 buttons per row so long lists stay readable on mobile.
    """
    per_row = 5
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for pos, watched_id in items:
        row.append(
            InlineKeyboardButton(
                text=f"🗑 {pos}",
                callback_data=UntrackCallback(watched_id=watched_id).pack(),
            )
        )
        if len(row) == per_row:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows)
