from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class DiscountedProduct:
    source: str
    external_id: str
    sku: str
    name: str
    url: str | None
    brand: str | None
    category: str | None
    regular_price: Decimal | None
    current_price: Decimal
    discount_percent: float | None
    in_stock: bool
    raw: dict


class Source(ABC):
    name: str

    @abstractmethod
    def iter_discounts(self) -> AsyncIterator[DiscountedProduct]:
        """Yield every currently discounted product from this source."""
