from __future__ import annotations

import asyncio
import signal

import structlog
from sqlalchemy import text

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
    )

    await _ping_db(log)

    varus = VarusSource(timeout_seconds=settings.varus_request_timeout_seconds)
    await _smoke_varus(varus, log)

    runner = ScanRunner(
        session_factory=SessionLocal,
        sources={"varus": varus},
        interval_seconds=settings.scan_interval_seconds,
        notify_sink=None,  # bot wires this in task #6
    )
    # First pass immediately so we get a "scan.done" log right after boot
    # (helps confirm the scheduler wiring works even before the interval fires).
    await runner.run_once()
    runner.start()

    stop_signal = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_signal.set)
        except NotImplementedError:
            # Windows dev — signals aren't wired the same way; keepalive still works.
            pass
    try:
        await stop_signal.wait()
    finally:
        log.info("shopping_bot.shutdown")
        await runner.stop()
        await engine.dispose()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
