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


def main_menu() -> ReplyKeyboardMarkup:
    """Persistent bottom keyboard shown to registered users."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BTN_ADD), KeyboardButton(text=BTN_LIST)]],
        resize_keyboard=True,
        is_persistent=True,
    )


class TrackCallback(CallbackData, prefix="trk"):
    source: str
    sku: str
    shop_id: int


class UntrackCallback(CallbackData, prefix="untrk"):
    watched_id: int


def track_button(source: str, sku: str, shop_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(
                text="🔔 Відстежувати",
                callback_data=TrackCallback(source=source, sku=sku, shop_id=shop_id).pack(),
            )
        ]]
    )


def untrack_button(watched_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(
                text="🗑 Прибрати",
                callback_data=UntrackCallback(watched_id=watched_id).pack(),
            )
        ]]
    )
