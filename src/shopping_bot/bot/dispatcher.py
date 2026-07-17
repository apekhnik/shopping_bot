from __future__ import annotations

import asyncio

import structlog
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from sqlalchemy.ext.asyncio import async_sessionmaker

from shopping_bot.bot.handlers import build_router
from shopping_bot.sources.base import Source

log = structlog.get_logger(__name__)


def build_bot(token: str) -> Bot:
    return Bot(
        token=token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def build_dispatcher(
    session_factory: async_sessionmaker, sources: dict[str, Source]
) -> Dispatcher:
    dp = Dispatcher()
    dp.include_router(build_router(session_factory, sources))
    return dp


async def start_polling(bot: Bot, dispatcher: Dispatcher) -> asyncio.Task:
    """Run polling as a background task so main() can also run the scheduler."""
    me = await bot.get_me()
    log.info("bot.polling_start", username=me.username, bot_id=me.id)
    task = asyncio.create_task(
        dispatcher.start_polling(bot, handle_signals=False),
        name="aiogram-polling",
    )
    return task
