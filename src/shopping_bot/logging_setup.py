from __future__ import annotations

import logging

import structlog

from shopping_bot.config import settings


def configure_logging() -> None:
    logging.basicConfig(format="%(message)s", level=settings.log_level.upper())
    # httpx logs every request at INFO (`HTTP Request: GET ... "200 OK"`).
    # Successful calls are noise for us — quiet them and let real problems
    # come through our own structured logs.
    for noisy in ("httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(settings.log_level.upper())
        ),
        cache_logger_on_first_use=True,
    )
