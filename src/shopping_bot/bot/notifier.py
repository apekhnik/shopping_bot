from __future__ import annotations

import asyncio

import structlog
from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from shopping_bot.bot.rendering import product_image_url, render_event
from shopping_bot.db.models import NotificationSent, WatchedProduct
from shopping_bot.scheduler.events import PriceEvent

log = structlog.get_logger(__name__)


def build_notify_sink(bot: Bot, session_factory: async_sessionmaker):
    """Return a coroutine suitable to pass to ScanRunner as notify_sink.

    For each event: find users watching that SKU whose min% threshold is
    passed, skip anyone already notified for this event_type+discount%,
    render, send, and log the send.
    """

    async def sink(events: list[PriceEvent]) -> None:
        if not events:
            return
        for event in events:
            await _dispatch_one(bot, session_factory, event)

    return sink


async def _dispatch_one(
    bot: Bot, session_factory: async_sessionmaker, event: PriceEvent
) -> None:
    async with session_factory() as session:
        watchers_stmt = select(WatchedProduct).where(
            WatchedProduct.source == event.source,
            WatchedProduct.sku == event.sku,
            WatchedProduct.shop_id == event.shop_id,
        )
        # 'discount_ended' always fires regardless of user's min% threshold —
        # they wanted to know about this product, and it just went off sale.
        if event.new_discount_percent is not None:
            watchers_stmt = watchers_stmt.where(
                WatchedProduct.notify_min_discount_percent <= event.new_discount_percent
            )
        watchers = (await session.execute(watchers_stmt)).scalars().all()

        if not watchers:
            return

        # dedup lookup: any prior notification for these users w/ same event+%?
        prior_stmt = select(NotificationSent).where(
            NotificationSent.source == event.source,
            NotificationSent.sku == event.sku,
            NotificationSent.shop_id == event.shop_id,
            NotificationSent.event_type == event.event_type.value,
        )
        prior_rows = (await session.execute(prior_stmt)).scalars().all()
        already_notified = {
            (n.user_id, n.discount_percent_at_notify) for n in prior_rows
        }

        text = render_event(event)
        img = product_image_url(event.source, event.sku)

        for watcher in watchers:
            key = (watcher.user_id, event.new_discount_percent)
            if key in already_notified:
                continue
            sent = await _send(bot, watcher.user_id, text, img)
            if not sent:
                continue
            session.add(
                NotificationSent(
                    user_id=watcher.user_id,
                    source=event.source,
                    sku=event.sku,
                    shop_id=event.shop_id,
                    event_type=event.event_type.value,
                    discount_percent_at_notify=event.new_discount_percent,
                )
            )
        await session.commit()


async def _send(bot: Bot, user_id: int, text: str, image_url: str | None) -> bool:
    """Best-effort send. Try photo card first, fall back to plain text."""
    try:
        if image_url is not None:
            try:
                await bot.send_photo(user_id, photo=image_url, caption=text)
                return True
            except TelegramForbiddenError:
                raise
            except TelegramRetryAfter:
                raise
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "bot.send_photo_failed_fallback_text",
                    user_id=user_id,
                    error=str(exc),
                )
        await bot.send_message(
            user_id, text, parse_mode=ParseMode.HTML, disable_web_page_preview=True
        )
        return True
    except TelegramForbiddenError:
        log.warning("bot.send_forbidden", user_id=user_id, note="user blocked bot")
        return False
    except TelegramRetryAfter as exc:
        log.warning("bot.send_rate_limited", user_id=user_id, retry_after=exc.retry_after)
        await asyncio.sleep(exc.retry_after)
        try:
            await bot.send_message(
                user_id, text, parse_mode=ParseMode.HTML, disable_web_page_preview=True
            )
            return True
        except Exception as exc2:  # noqa: BLE001
            log.error("bot.send_failed_after_retry", user_id=user_id, error=str(exc2))
            return False
    except Exception as exc:  # noqa: BLE001
        log.error("bot.send_failed", user_id=user_id, error=str(exc))
        return False
