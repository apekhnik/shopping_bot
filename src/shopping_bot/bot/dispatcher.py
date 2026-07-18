from __future__ import annotations

import asyncio

import structlog
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand
from sqlalchemy.ext.asyncio import async_sessionmaker

from shopping_bot.bot.handlers import build_router
from shopping_bot.bot.message_log import TrackedMessages, TrackSentMiddleware
from shopping_bot.sources.base import Source

log = structlog.get_logger(__name__)

_MENU_COMMANDS = [
    BotCommand(command="add", description="Знайти товар та відстежувати"),
    BotCommand(command="list", description="Мій список"),
    BotCommand(command="clear", description="Прибрати мої повідомлення"),
    BotCommand(command="cancel", description="Скасувати поточну дію"),
    BotCommand(command="help", description="Допомога"),
]


def build_bot(token: str, tracked: TrackedMessages) -> Bot:
    bot = Bot(
        token=token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    bot.session.middleware(TrackSentMiddleware(tracked))
    return bot


def build_dispatcher(
    session_factory: async_sessionmaker,
    sources: dict[str, Source],
    tracked: TrackedMessages,
) -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(build_router(session_factory, sources, tracked))
    return dp


async def start_polling(bot: Bot, dispatcher: Dispatcher) -> asyncio.Task:
    """Run polling as a background task so main() can also run the scheduler."""
    me = await bot.get_me()
    log.info("bot.polling_start", username=me.username, bot_id=me.id)
    try:
        await bot.set_my_commands(_MENU_COMMANDS)
    except Exception as exc:  # noqa: BLE001
        log.warning("bot.set_commands_failed", error=str(exc))
    task = asyncio.create_task(
        dispatcher.start_polling(bot, handle_signals=False),
        name="aiogram-polling",
    )
    return task
