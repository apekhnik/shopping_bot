from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from shopping_bot.db.models import ProductState
from shopping_bot.sources.base import ProductSnapshot


class EventType(StrEnum):
    DISCOUNT_STARTED = "discount_started"
    DISCOUNT_DEEPENED = "discount_deepened"
    DISCOUNT_ENDED = "discount_ended"


@dataclass(frozen=True, slots=True)
class PriceEvent:
    source: str
    sku: str
    shop_id: int
    event_type: EventType
    old_discount_percent: int | None
    new_discount_percent: int | None
    old_price: Decimal | None
    new_price: Decimal
    snapshot: ProductSnapshot


def _discount_of(state: ProductState | None) -> int:
    if state is None:
        return 0
    return state.discount_percent or 0


def detect_event(prev: ProductState | None, new: ProductSnapshot) -> PriceEvent | None:
    """Compare last known state with fresh snapshot; return event or None.

    Pure function, no DB. Rules:
    - was 0%, now >0%  -> discount_started
    - was >0%, now 0%  -> discount_ended
    - both >0%, new%>prev% -> discount_deepened
    - anything else (same %, only stock change, only price shift with no promo)
      -> no event
    Stock changes without a discount move are intentionally ignored for MVP.
    """
    was = _discount_of(prev)
    now = new.discount_percent or 0

    event_type: EventType | None
    if was == 0 and now > 0:
        event_type = EventType.DISCOUNT_STARTED
    elif was > 0 and now == 0:
        event_type = EventType.DISCOUNT_ENDED
    elif was > 0 and now > was:
        event_type = EventType.DISCOUNT_DEEPENED
    else:
        return None

    return PriceEvent(
        source=new.source,
        sku=new.sku,
        shop_id=new.shop_id,
        event_type=event_type,
        old_discount_percent=was if was > 0 else None,
        new_discount_percent=now if now > 0 else None,
        old_price=Decimal(str(prev.special_price)) if prev and prev.special_price else (
            Decimal(str(prev.price)) if prev else None
        ),
        new_price=new.special_price or new.price,
        snapshot=new,
    )
