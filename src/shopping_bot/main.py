from __future__ import annotations

import asyncio
import signal

import structlog
from sqlalchemy import text

from shopping_bot.bot import (
    TrackedMessages,
    build_bot,
    build_dispatcher,
    build_notify_sink,
    start_polling,
)
from shopping_bot.config import settings
from shopping_bot.db.session import SessionLocal, engine
from shopping_bot.logging_setup import configure_logging
from shopping_bot.scheduler import ScanRunner
from shopping_bot.sources import SourceUnavailable, VarusSource


def _mask_db_url(url: str) -> str:
    if "@" not in url:
        return url
    scheme_and_creds, host_part = url.rsplit("@", 1)
    scheme = scheme_and_creds.split("://", 1)[0]
    return f"{scheme}://***@{host_part}"


async def _ping_db(log: structlog.stdlib.BoundLogger) -> None:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        log.info("shopping_bot.db_ping", status="ok", dialect=engine.dialect.name)
    except Exception as exc:  # noqa: BLE001
        log.error("shopping_bot.db_ping", status="fail", error=str(exc))


async def _smoke_varus(source: VarusSource, log: structlog.stdlib.BoundLogger) -> None:
    try:
        results = await source.search_by_name(
            "молоко", shop_id=settings.varus_default_shop_id, limit=3
        )
        log.info(
            "shopping_bot.varus_smoke",
            status="ok",
            hits=len(results),
            first=results[0].name if results else None,
        )
    except SourceUnavailable as exc:
        log.error("shopping_bot.varus_smoke", status="fail", error=str(exc))


async def run() -> None:
    configure_logging()
    log = structlog.get_logger()
    log.info(
        "shopping_bot.boot",
        db_url=_mask_db_url(str(engine.url)),
        scan_interval=settings.scan_interval_seconds,
        default_shop_id=settings.varus_default_shop_id,
        bot_configured=bool(settings.telegram_bot_token),
    )

    await _ping_db(log)

    varus = VarusSource(timeout_seconds=settings.varus_request_timeout_seconds)
    sources = {"varus": varus}
    await _smoke_varus(varus, log)

    bot = None
    polling_task: asyncio.Task | None = None
    notify_sink = None

    if settings.telegram_bot_token:
        tracked_messages = TrackedMessages()
        bot = build_bot(settings.telegram_bot_token, tracked_messages)
        dispatcher = build_dispatcher(SessionLocal, sources, tracked_messages)
        polling_task = await start_polling(bot, dispatcher)
        notify_sink = build_notify_sink(bot, SessionLocal)
    else:
        log.warning(
            "shopping_bot.bot_disabled",
            reason="TELEGRAM_BOT_TOKEN is empty",
            note="scheduler still runs, notifications will be dropped",
        )

    runner = ScanRunner(
        session_factory=SessionLocal,
        sources=sources,
        interval_seconds=settings.scan_interval_seconds,
        notify_sink=notify_sink,
    )
    await runner.run_once()
    runner.start()

    stop_signal = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_signal.set)
        except NotImplementedError:
            pass
    try:
        await stop_signal.wait()
    finally:
        log.info("shopping_bot.shutdown")
        await runner.stop()
        if polling_task is not None:
            polling_task.cancel()
            try:
                await polling_task
            except (asyncio.CancelledError, Exception):
                pass
        if bot is not None:
            await bot.session.close()
        await engine.dispose()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
