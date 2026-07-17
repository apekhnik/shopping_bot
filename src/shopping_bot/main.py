from __future__ import annotations

import asyncio

import structlog
from sqlalchemy import text

from shopping_bot.db.session import engine
from shopping_bot.logging_setup import configure_logging


def _mask_db_url(url: str) -> str:
    # Strip credentials from a SQLAlchemy URL for logging.
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
    # Real wiring lands in tasks #3–#6:
    #   - build enabled sources
    #   - start APScheduler with periodic scan job
    #   - start aiogram Dispatcher (long-polling)
    # Until then keep the process alive so the platform doesn't loop-restart us.
    while True:
        await asyncio.sleep(3600)


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
