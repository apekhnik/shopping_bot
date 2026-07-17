from __future__ import annotations

import structlog
from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import async_sessionmaker

from shopping_bot.bot.keyboards import (
    TrackCallback,
    UntrackCallback,
    track_button,
    untrack_button,
)
from shopping_bot.bot.rendering import (
    render_search_hit,
    render_watchlist_row,
)
from shopping_bot.config import settings
from shopping_bot.db.models import ProductState, User, WatchedProduct
from shopping_bot.sources.base import Source

log = structlog.get_logger(__name__)


def build_router(
    session_factory: async_sessionmaker,
    sources: dict[str, Source],
    default_source: str = "varus",
) -> Router:
    router = Router()

    async def _ensure_user(message_or_cb: Message | CallbackQuery) -> User:
        tg_user = message_or_cb.from_user
        assert tg_user is not None
        async with session_factory() as session:
            user = await session.get(User, tg_user.id)
            if user is None:
                user = User(
                    telegram_user_id=tg_user.id,
                    username=tg_user.username,
                    default_shop_id=settings.varus_default_shop_id,
                )
                session.add(user)
                await session.commit()
                log.info("bot.user_registered", user_id=tg_user.id, username=tg_user.username)
            return user

    @router.message(CommandStart())
    async def cmd_start(message: Message) -> None:
        await _ensure_user(message)
        await message.answer(
            "Привіт! Я слідкую за знижками у Varus.\n\n"
            "<b>/add кокосове молоко</b> — знайти товар і почати відстежувати.\n"
            "<b>/list</b> — мій список відстежень.\n"
            "<b>/remove</b> — прибрати щось зі списку.\n\n"
            f"За замовчуванням магазин — <code>shop_id={settings.varus_default_shop_id}</code>."
        )

    @router.message(Command("help"))
    async def cmd_help(message: Message) -> None:
        await cmd_start(message)

    @router.message(Command("add"))
    async def cmd_add(message: Message) -> None:
        user = await _ensure_user(message)
        query = (message.text or "").removeprefix("/add").strip()
        if not query:
            await message.answer(
                "Напиши, що шукати, після <code>/add</code>. Приклад:\n"
                "<code>/add кокосове молоко</code>"
            )
            return

        source = sources.get(default_source)
        if source is None:
            await message.answer("Джерело не налаштоване. Спробуй пізніше.")
            return

        shop_id = user.default_shop_id or settings.varus_default_shop_id
        results = await source.search_by_name(query, shop_id=shop_id, limit=5)

        if not results:
            await message.answer(
                f"Нічого не знайшов за запитом «{query}». Спробуй інші слова."
            )
            return

        for snap in results:
            await message.answer(
                render_search_hit(snap),
                reply_markup=track_button(snap.source, snap.sku, snap.shop_id),
                disable_web_page_preview=True,
            )

    @router.callback_query(TrackCallback.filter())
    async def cb_track(cb: CallbackQuery, callback_data: TrackCallback) -> None:
        user = await _ensure_user(cb)
        source = sources.get(callback_data.source)
        if source is None:
            await cb.answer("Джерело не налаштоване.", show_alert=True)
            return

        # Refresh the SKU to cache its name/url_key/current state.
        snapshots = await source.fetch_by_skus([callback_data.sku], callback_data.shop_id)
        if not snapshots:
            await cb.answer("Товар не знайшов у каталозі.", show_alert=True)
            return
        snap = snapshots[0]

        async with session_factory() as session:
            existing_stmt = select(WatchedProduct).where(
                WatchedProduct.user_id == user.telegram_user_id,
                WatchedProduct.source == snap.source,
                WatchedProduct.sku == snap.sku,
                WatchedProduct.shop_id == snap.shop_id,
            )
            existing = (await session.execute(existing_stmt)).scalar_one_or_none()
            if existing is not None:
                await cb.answer("Вже відстежую.", show_alert=False)
                return

            session.add(
                WatchedProduct(
                    user_id=user.telegram_user_id,
                    source=snap.source,
                    sku=snap.sku,
                    shop_id=snap.shop_id,
                    name_cache=snap.name,
                    url_key=snap.url_key,
                )
            )
            await session.commit()

        log.info(
            "bot.watched_added",
            user_id=user.telegram_user_id,
            source=snap.source,
            sku=snap.sku,
        )
        await cb.answer("✅ Відстежую!", show_alert=False)

    @router.message(Command("list"))
    async def cmd_list(message: Message) -> None:
        user = await _ensure_user(message)
        async with session_factory() as session:
            watched_stmt = (
                select(WatchedProduct)
                .where(WatchedProduct.user_id == user.telegram_user_id)
                .order_by(WatchedProduct.added_at.desc())
            )
            watched = (await session.execute(watched_stmt)).scalars().all()
            if not watched:
                await message.answer(
                    "Список порожній. Додай товар через <code>/add назва</code>."
                )
                return

            keys = [(w.source, w.sku, w.shop_id) for w in watched]
            states_stmt = select(ProductState).where(
                tuple_(
                    ProductState.source, ProductState.sku, ProductState.shop_id
                ).in_(keys)
            )
            states = {
                (s.source, s.sku, s.shop_id): s
                for s in (await session.execute(states_stmt)).scalars().all()
            }

        for w in watched:
            state = states.get((w.source, w.sku, w.shop_id))
            await message.answer(
                render_watchlist_row(w.source, w.sku, w.name_cache, w.url_key, state),
                reply_markup=untrack_button(w.id),
                disable_web_page_preview=True,
            )

    @router.message(Command("remove"))
    async def cmd_remove(message: Message) -> None:
        # /remove is a convenience alias — the untrack action lives on each /list card.
        await cmd_list(message)

    @router.callback_query(UntrackCallback.filter())
    async def cb_untrack(cb: CallbackQuery, callback_data: UntrackCallback) -> None:
        user = await _ensure_user(cb)
        async with session_factory() as session:
            item = await session.get(WatchedProduct, callback_data.watched_id)
            if item is None or item.user_id != user.telegram_user_id:
                await cb.answer("Не знайшов у твоєму списку.", show_alert=True)
                return
            await session.delete(item)
            await session.commit()
        log.info(
            "bot.watched_removed",
            user_id=user.telegram_user_id,
            watched_id=callback_data.watched_id,
        )
        await cb.answer("Прибрав.", show_alert=False)
        if cb.message:
            try:
                await cb.message.delete()
            except Exception:  # noqa: BLE001
                pass

    return router
