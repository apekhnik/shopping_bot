from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from shopping_bot.db.models import Base, ProductState, User, WatchedProduct
from shopping_bot.scheduler.events import EventType
from shopping_bot.scheduler.scan import run_scan
from shopping_bot.sources.base import ProductSnapshot, Source


class FakeSource(Source):
    name = "varus"

    def __init__(self, snapshots: list[ProductSnapshot]) -> None:
        self._snapshots = snapshots
        self.calls: list[tuple[list[str], int]] = []

    async def search_by_name(self, query, shop_id, limit=5):
        return []

    async def fetch_by_skus(self, skus, shop_id):
        self.calls.append((list(skus), shop_id))
        return [s for s in self._snapshots if s.sku in skus and s.shop_id == shop_id]

    async def top_discounts(self, shop_id, min_discount_percent, limit):
        return []


def _snap(sku: str, discount: int | None, price: str = "100.00", special: str | None = None) -> ProductSnapshot:
    return ProductSnapshot(
        source="varus",
        sku=sku,
        shop_id=57,
        name=f"Product {sku}",
        url_key=f"product-{sku}",
        brand="B",
        price=Decimal(price),
        special_price=Decimal(special) if special else None,
        discount_percent=discount,
        special_price_to_date=date(2026, 12, 31) if discount else None,
        in_stock=True,
    )


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as s:
        yield s
    await engine.dispose()


async def _make_user_watching(session: AsyncSession, sku: str) -> None:
    session.add(User(telegram_user_id=1, default_shop_id=57))
    await session.flush()
    session.add(
        WatchedProduct(
            user_id=1,
            source="varus",
            sku=sku,
            shop_id=57,
            name_cache=f"Product {sku}",
            url_key=f"product-{sku}",
        )
    )
    await session.commit()


@pytest.mark.asyncio
async def test_empty_watchlist_returns_no_events(session: AsyncSession) -> None:
    events = await run_scan(session, {"varus": FakeSource([])})
    assert events == []


@pytest.mark.asyncio
async def test_first_scan_of_discounted_item_emits_started(session: AsyncSession) -> None:
    await _make_user_watching(session, "A")
    source = FakeSource([_snap("A", discount=25, special="75.00")])

    events = await run_scan(session, {"varus": source})

    assert len(events) == 1
    assert events[0].event_type is EventType.DISCOUNT_STARTED
    assert source.calls == [(["A"], 57)]

    # state is now persisted
    state = await session.get(ProductState, ("varus", "A", 57))
    assert state is not None
    assert state.discount_percent == 25


@pytest.mark.asyncio
async def test_second_scan_with_no_change_emits_nothing(session: AsyncSession) -> None:
    await _make_user_watching(session, "A")
    source = FakeSource([_snap("A", discount=25, special="75.00")])

    await run_scan(session, {"varus": source})
    events = await run_scan(session, {"varus": source})

    assert events == []


@pytest.mark.asyncio
async def test_second_scan_with_deeper_discount_emits_deepened(session: AsyncSession) -> None:
    await _make_user_watching(session, "A")
    first = FakeSource([_snap("A", discount=15, special="85.00")])
    second = FakeSource([_snap("A", discount=40, special="60.00")])

    await run_scan(session, {"varus": first})
    events = await run_scan(session, {"varus": second})

    assert len(events) == 1
    assert events[0].event_type is EventType.DISCOUNT_DEEPENED
    assert events[0].old_discount_percent == 15
    assert events[0].new_discount_percent == 40
