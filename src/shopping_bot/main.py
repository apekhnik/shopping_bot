from __future__ import annotations

import asyncio

import structlog

from shopping_bot.logging_setup import configure_logging


async def run() -> None:
    configure_logging()
    log = structlog.get_logger()
    log.info("shopping_bot.boot", status="skeleton", note="handlers wired in later tasks")
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
