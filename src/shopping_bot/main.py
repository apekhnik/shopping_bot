from __future__ import annotations

import asyncio

import structlog
from sqlalchemy import text

from shopping_bot.config import settings
from shopping_bot.db.session import engine
from shopping_bot.logging_setup import configure_logging
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


async def _smoke_varus(log: structlog.stdlib.BoundLogger) -> None:
    source = VarusSource(timeout_seconds=settings.varus_request_timeout_seconds)
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
    finally:
        await source.aclose()


async def run() -> None:
    configure_logging()
    log = structlog.get_logger()
    log.info(
        "shopping_bot.boot",
        status="skeleton",
        db_url=_mask_db_url(str(engine.url)),
        note="handlers wired in later tasks",
    )
    await _ping_db(log)
    await _smoke_varus(log)
    # Real wiring lands in tasks #5–#6:
    #   - APScheduler with periodic scan job
    #   - aiogram Dispatcher (long-polling)
    # Until then keep the process alive so the platform doesn't loop-restart us.
    while True:
        await asyncio.sleep(3600)


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
