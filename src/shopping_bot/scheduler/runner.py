from __future__ import annotations

from collections.abc import Awaitable, Callable

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.ext.asyncio import async_sessionmaker

from shopping_bot.scheduler.events import PriceEvent
from shopping_bot.scheduler.scan import run_scan
from shopping_bot.sources.base import Source

log = structlog.get_logger(__name__)

NotifySink = Callable[[list[PriceEvent]], Awaitable[None]]


async def _default_sink(events: list[PriceEvent]) -> None:
    if events:
        log.info(
            "scan.events_no_sink",
            count=len(events),
            note="wire a notification sink in the bot",
        )


class ScanRunner:
    """Wraps run_scan into a scheduled job and lets the bot plug in a
    notification sink. Kept separate from scan.py so tests can exercise
    run_scan directly without touching APScheduler.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker,
        sources: dict[str, Source],
        interval_seconds: int,
        notify_sink: NotifySink | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._sources = sources
        self._interval = interval_seconds
        self._notify = notify_sink or _default_sink
        self._scheduler: AsyncIOScheduler | None = None

    async def run_once(self) -> list[PriceEvent]:
        async with self._session_factory() as session:
            events = await run_scan(session, self._sources)
        try:
            await self._notify(events)
        except Exception as exc:  # noqa: BLE001
            log.error("scan.notify_failed", error=str(exc), event_count=len(events))
        return events

    def start(self) -> None:
        if self._scheduler is not None:
            return
        self._scheduler = AsyncIOScheduler()
        self._scheduler.add_job(
            self.run_once,
            "interval",
            seconds=self._interval,
            id="scan_watchlist",
            max_instances=1,
            coalesce=True,
        )
        self._scheduler.start()
        log.info("scheduler.started", interval_seconds=self._interval)

    async def stop(self) -> None:
        if self._scheduler is not None:
            self._scheduler.shutdown(wait=False)
            self._scheduler = None
        for source in self._sources.values():
            await source.aclose()
