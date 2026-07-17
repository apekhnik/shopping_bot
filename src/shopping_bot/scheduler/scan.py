from __future__ import annotations

from collections import defaultdict

import structlog
from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from shopping_bot.db.models import ProductState, WatchedProduct
from shopping_bot.scheduler.events import PriceEvent, detect_event
from shopping_bot.sources.base import ProductSnapshot, Source, SourceUnavailable

log = structlog.get_logger(__name__)


async def _fetch_watched_targets(
    session: AsyncSession,
) -> list[tuple[str, str, int]]:
    """Distinct (source, sku, shop_id) tuples across all users' watchlists."""
    stmt = select(WatchedProduct.source, WatchedProduct.sku, WatchedProduct.shop_id).distinct()
    result = await session.execute(stmt)
    return [(row[0], row[1], row[2]) for row in result.all()]


async def _load_prev_states(
    session: AsyncSession, keys: list[tuple[str, str, int]]
) -> dict[tuple[str, str, int], ProductState]:
    if not keys:
        return {}
    stmt = select(ProductState).where(
        tuple_(ProductState.source, ProductState.sku, ProductState.shop_id).in_(keys)
    )
    result = await session.execute(stmt)
    return {(s.source, s.sku, s.shop_id): s for s in result.scalars().all()}


def _apply_snapshot(state: ProductState | None, snap: ProductSnapshot) -> ProductState:
    if state is None:
        return ProductState(
            source=snap.source,
            sku=snap.sku,
            shop_id=snap.shop_id,
            price=snap.price,
            special_price=snap.special_price,
            discount_percent=snap.discount_percent,
            special_price_to_date=snap.special_price_to_date,
            in_stock=snap.in_stock,
        )
    state.price = snap.price
    state.special_price = snap.special_price
    state.discount_percent = snap.discount_percent
    state.special_price_to_date = snap.special_price_to_date
    state.in_stock = snap.in_stock
    return state


async def run_scan(
    session: AsyncSession, sources: dict[str, Source]
) -> list[PriceEvent]:
    """One full pass over every watched (source, sku, shop_id).

    Returns detected events. Callers (bot notification path) decide what to
    do with them. Failures on one source do not abort the whole scan.
    """
    targets = await _fetch_watched_targets(session)
    if not targets:
        log.info("scan.empty", note="no watched products")
        return []

    # group by (source_name, shop_id)
    groups: dict[tuple[str, int], list[str]] = defaultdict(list)
    for source_name, sku, shop_id in targets:
        groups[(source_name, shop_id)].append(sku)

    all_events: list[PriceEvent] = []
    stats: dict[str, int] = {"fetched": 0, "missing": 0, "events": 0, "source_errors": 0}

    for (source_name, shop_id), skus in groups.items():
        source = sources.get(source_name)
        if source is None:
            log.warning("scan.unknown_source", source=source_name, watched=len(skus))
            continue

        try:
            snapshots = await source.fetch_by_skus(skus, shop_id)
        except SourceUnavailable as exc:
            log.error(
                "scan.source_unavailable",
                source=source_name,
                shop_id=shop_id,
                error=str(exc),
            )
            stats["source_errors"] += 1
            continue

        stats["fetched"] += len(snapshots)
        stats["missing"] += max(0, len(skus) - len(snapshots))

        keys = [(s.source, s.sku, s.shop_id) for s in snapshots]
        prev_map = await _load_prev_states(session, keys)

        for snap in snapshots:
            key = (snap.source, snap.sku, snap.shop_id)
            prev = prev_map.get(key)
            event = detect_event(prev, snap)
            if event is not None:
                all_events.append(event)
                stats["events"] += 1
            new_state = _apply_snapshot(prev, snap)
            if prev is None:
                session.add(new_state)

    await session.commit()
    log.info("scan.done", targets=len(targets), **stats)
    return all_events
