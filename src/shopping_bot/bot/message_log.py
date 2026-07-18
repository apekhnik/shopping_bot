from __future__ import annotations

from collections import defaultdict, deque
from typing import Any

import structlog
from aiogram import Bot
from aiogram.client.session.middlewares.base import (
    BaseRequestMiddleware,
    NextRequestMiddlewareType,
)
from aiogram.methods import TelegramMethod
from aiogram.types import Message

log = structlog.get_logger(__name__)


class TrackedMessages:
    """In-memory ring buffer of message IDs the bot has sent, per chat.

    Enough to power a 'clear chat' button — Telegram lets bots delete
    their own messages in private chats without a time limit, but only
    if we know the message IDs. Bounded (default 500) so long-lived
    processes don't grow unbounded.
    """

    def __init__(self, max_per_chat: int = 500) -> None:
        self._max = max_per_chat
        self._store: dict[int, deque[int]] = defaultdict(
            lambda: deque(maxlen=max_per_chat)
        )

    def record(self, chat_id: int, message_id: int) -> None:
        self._store[chat_id].append(message_id)

    def drain(self, chat_id: int) -> list[int]:
        """Return + reset the tracked IDs for a chat."""
        q = self._store.get(chat_id)
        if not q:
            return []
        ids = list(q)
        q.clear()
        return ids


class TrackSentMiddleware(BaseRequestMiddleware):
    """Record chat_id + message_id for every Message the bot sends.

    Runs on the session middleware chain, so every outgoing API call
    passes through here. We record whatever `Message`s come back —
    covers sendMessage, sendPhoto, sendMediaGroup, forwardMessage,
    copyMessage, and any other send-shaped method.
    """

    def __init__(self, tracked: TrackedMessages) -> None:
        self._tracked = tracked

    async def __call__(
        self,
        make_request: NextRequestMiddlewareType,
        bot: Bot,
        method: TelegramMethod,
    ) -> Any:
        result = await make_request(bot, method)
        if isinstance(result, Message):
            self._tracked.record(result.chat.id, result.message_id)
        elif isinstance(result, list):
            for m in result:
                if isinstance(m, Message):
                    self._tracked.record(m.chat.id, m.message_id)
        return result


async def clear_chat(bot: Bot, chat_id: int, tracked: TrackedMessages) -> int:
    """Delete every tracked bot message in `chat_id`. Returns count deleted."""
    ids = tracked.drain(chat_id)
    deleted = 0
    for mid in ids:
        try:
            await bot.delete_message(chat_id, mid)
            deleted += 1
        except Exception as exc:  # noqa: BLE001
            # Message may already be gone, too old, or unreachable — that's fine,
            # goal is a clean chat, not a report of every 400.
            log.debug("bot.delete_failed", chat_id=chat_id, mid=mid, error=str(exc))
    return deleted
