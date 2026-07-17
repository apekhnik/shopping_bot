from __future__ import annotations

import structlog
from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import async_sessionmaker

from shopping_bot.bot.keyboards import (
    BTN_ADD,
    BTN_LIST,
    BTN_RANDOM_SNACK,
    TrackCallback,
    UntrackCallback,
    main_menu,
    track_button,
    watchlist_untrack_row,
)
from shopping_bot.bot.random_pick import pick_random_snacks
from shopping_bot.bot.rendering import (
    product_image_url,
    render_search_hit,
    render_watchlist_table,
)
from shopping_bot.bot.states import AddFlow
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
                log.info(
                    "bot.user_registered",
                    user_id=tg_user.id,
                    username=tg_user.username,
                )
            return user

    async def _send_product_card(message: Message, snap) -> None:
        caption = render_search_hit(snap)
        markup = track_button(snap.source, snap.sku, snap.shop_id)
        img = product_image_url(snap.source, snap.sku)
        if img is not None:
            try:
                await message.answer_photo(photo=img, caption=caption, reply_markup=markup)
                return
            except Exception as exc:  # noqa: BLE001
                log.warning("bot.product_photo_failed", sku=snap.sku, error=str(exc))
        await message.answer(caption, reply_markup=markup, disable_web_page_preview=True)

    async def _do_search(message: Message, user: User, query: str) -> None:
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
            await _send_product_card(message, snap)

    async def _show_list(message: Message, user: User) -> None:
        async with session_factory() as session:
            watched_stmt = (
                select(WatchedProduct)
                .where(WatchedProduct.user_id == user.telegram_user_id)
                .order_by(WatchedProduct.added_at.desc())
            )
            watched = (await session.execute(watched_stmt)).scalars().all()
            if not watched:
                await message.answer(
                    f"Список порожній. Натисни <b>{BTN_ADD}</b> або напиши "
                    "<code>/add назва</code>."
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

        items: list[tuple[int, str, str, str | None, ProductState | None]] = []
        buttons: list[tuple[int, int]] = []
        for pos, w in enumerate(watched, start=1):
            state = states.get((w.source, w.sku, w.shop_id))
            items.append((pos, w.source, w.name_cache, w.url_key, state))
            buttons.append((pos, w.id))

        await message.answer(
            render_watchlist_table(items),
            reply_markup=watchlist_untrack_row(buttons),
            disable_web_page_preview=True,
        )

    # -------- commands --------

    @router.message(CommandStart())
    async def cmd_start(message: Message, state: FSMContext) -> None:
        await _ensure_user(message)
        await state.clear()
        await message.answer(
            "Привіт! Я слідкую за знижками у Varus.\n\n"
            f"• <b>{BTN_ADD}</b> — знайти товар та почати відстежувати\n"
            f"• <b>{BTN_LIST}</b> — переглянути список і прибрати непотрібне\n"
            f"• <b>{BTN_RANDOM_SNACK}</b> — 3 випадкові снеки на пробу\n\n"
            f"За замовчуванням магазин — <code>shop_id={settings.varus_default_shop_id}</code>. "
            "Скасувати додавання — /cancel.",
            reply_markup=main_menu(),
        )

    @router.message(Command("help"))
    async def cmd_help(message: Message, state: FSMContext) -> None:
        await cmd_start(message, state)

    @router.message(Command("cancel"))
    async def cmd_cancel(message: Message, state: FSMContext) -> None:
        current = await state.get_state()
        await state.clear()
        if current:
            await message.answer("Ок, скасував.", reply_markup=main_menu())
        else:
            await message.answer("Нема що скасовувати.", reply_markup=main_menu())

    @router.message(Command("add"))
    async def cmd_add(message: Message, state: FSMContext) -> None:
        user = await _ensure_user(message)
        query = (message.text or "").removeprefix("/add").strip()
        if not query:
            await state.set_state(AddFlow.waiting_for_query)
            await message.answer(
                "Що шукати? Напиши назву товара (можна кілька слів).\n"
                "Скасувати — /cancel."
            )
            return
        await state.clear()
        await _do_search(message, user, query)

    @router.message(Command("list"))
    async def cmd_list(message: Message, state: FSMContext) -> None:
        await state.clear()
        user = await _ensure_user(message)
        await _show_list(message, user)

    @router.message(Command("remove"))
    async def cmd_remove(message: Message, state: FSMContext) -> None:
        await cmd_list(message, state)

    # -------- reply-keyboard buttons --------

    @router.message(F.text == BTN_ADD)
    async def btn_add(message: Message, state: FSMContext) -> None:
        await _ensure_user(message)
        await state.set_state(AddFlow.waiting_for_query)
        await message.answer(
            "Що шукати? Напиши назву товара (можна кілька слів).\n"
            "Скасувати — /cancel."
        )

    @router.message(F.text == BTN_LIST)
    async def btn_list(message: Message, state: FSMContext) -> None:
        await state.clear()
        user = await _ensure_user(message)
        await _show_list(message, user)

    @router.message(F.text == BTN_RANDOM_SNACK)
    async def btn_random_snack(message: Message, state: FSMContext) -> None:
        await state.clear()
        user = await _ensure_user(message)
        source = sources.get(default_source)
        if source is None:
            await message.answer("Джерело не налаштоване.")
            return
        shop_id = user.default_shop_id or settings.varus_default_shop_id
        picks = await pick_random_snacks(source, shop_id=shop_id, count=3)
        if not picks:
            await message.answer("Нічого не знайшов зараз. Спробуй ще раз.")
            return
        await message.answer("🎲 Ось що можна взяти до чаю:")
        for snap in picks:
            await _send_product_card(message, snap)

    # -------- FSM: waiting for search query --------

    @router.message(AddFlow.waiting_for_query, F.text)
    async def add_query_received(message: Message, state: FSMContext) -> None:
        query = (message.text or "").strip()
        if not query:
            await message.answer("Порожній запит. Напиши хоч слово, або /cancel.")
            return
        user = await _ensure_user(message)
        await state.clear()
        await _do_search(message, user, query)

    # -------- callbacks --------

    @router.callback_query(TrackCallback.filter())
    async def cb_track(cb: CallbackQuery, callback_data: TrackCallback) -> None:
        user = await _ensure_user(cb)
        source = sources.get(callback_data.source)
        if source is None:
            await cb.answer("Джерело не налаштоване.", show_alert=True)
            return

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

            # Rebuild list right away so the summary message stays in sync.
            watched_stmt = (
                select(WatchedProduct)
                .where(WatchedProduct.user_id == user.telegram_user_id)
                .order_by(WatchedProduct.added_at.desc())
            )
            watched = (await session.execute(watched_stmt)).scalars().all()
            state_map: dict[tuple[str, str, int], ProductState] = {}
            if watched:
                keys = [(w.source, w.sku, w.shop_id) for w in watched]
                states_stmt = select(ProductState).where(
                    tuple_(
                        ProductState.source, ProductState.sku, ProductState.shop_id
                    ).in_(keys)
                )
                state_map = {
                    (s.source, s.sku, s.shop_id): s
                    for s in (await session.execute(states_stmt)).scalars().all()
                }

        log.info(
            "bot.watched_removed",
            user_id=user.telegram_user_id,
            watched_id=callback_data.watched_id,
        )
        await cb.answer("Прибрав.", show_alert=False)

        if cb.message is None:
            return

        if not watched:
            try:
                await cb.message.edit_text(
                    "Список порожній. Додай товар через кнопку "
                    f"<b>{BTN_ADD}</b>."
                )
            except Exception:  # noqa: BLE001
                pass
            return

        items: list[tuple[int, str, str, str | None, ProductState | None]] = []
        buttons: list[tuple[int, int]] = []
        for pos, w in enumerate(watched, start=1):
            state = state_map.get((w.source, w.sku, w.shop_id))
            items.append((pos, w.source, w.name_cache, w.url_key, state))
            buttons.append((pos, w.id))
        try:
            await cb.message.edit_text(
                render_watchlist_table(items),
                reply_markup=watchlist_untrack_row(buttons),
                disable_web_page_preview=True,
            )
        except Exception:  # noqa: BLE001
            # edit_text can fail if content is identical (rare) or too old; ignore.
            pass

    return router
