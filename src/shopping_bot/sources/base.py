from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class ProductSnapshot:
    """A single product's state at one shop at one moment in time.

    Used both as a search result (for /add) and as periodic refresh output
    (for the scan job). Discount fields are None when the product has no
    active promo. `discount_percent` is an integer 0-100 as the source returns.
    """

    source: str
    sku: str
    shop_id: int
    name: str
    url_key: str | None
    brand: str | None
    price: Decimal
    special_price: Decimal | None
    discount_percent: int | None
    special_price_to_date: date | None
    in_stock: bool

    @property
    def is_discounted(self) -> bool:
        return self.discount_percent is not None and self.discount_percent > 0


class SourceUnavailable(Exception):
    """The upstream source returned an unexpected shape or repeated 5xx.

    Callers should catch this, log it, and move on — one broken source
    must not take down the scan cycle.
    """


class Source(ABC):
    name: str

    @abstractmethod
    async def search_by_name(
        self, query: str, shop_id: int, limit: int = 5
    ) -> list[ProductSnapshot]:
        """Fulltext search by product name. Used by /add."""

    @abstractmethod
    async def fetch_by_skus(
        self, skus: list[str], shop_id: int
    ) -> list[ProductSnapshot]:
        """Bulk refresh state of specific SKUs. Used by the scan job.

        Skus not found in the source are simply omitted from the result —
        the caller decides how to handle disappearances.
        """

    async def aclose(self) -> None:
        """Release any long-lived resources (HTTP client, etc.)."""
