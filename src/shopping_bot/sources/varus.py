from __future__ import annotations

import asyncio
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import httpx
import structlog

from shopping_bot.sources.base import ProductSnapshot, Source, SourceUnavailable

_ENDPOINT = "https://varus.ua/api/catalog/vue_storefront_catalog_2/product_v2/_search"
_MAX_PAGE_SIZE = 1000
_MAX_RETRIES = 3
_RETRY_BACKOFF_SECONDS = 1.5

log = structlog.get_logger(__name__)


def _source_include_fields(shop_id: int) -> list[str]:
    # Ask ES for only what we actually parse. Cuts response size ~10-20x.
    shop_prefix = f"sqpp_data_{shop_id}"
    return [
        "sku",
        "id",
        "name",
        "url_key",
        "slug",
        "brand_data.name",
        f"{shop_prefix}.price",
        f"{shop_prefix}.special_price",
        f"{shop_prefix}.special_price_discount",
        f"{shop_prefix}.special_price_to_date",
        f"{shop_prefix}.in_stock",
    ]


def _parse_date(value: Any) -> date | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _to_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (ArithmeticError, ValueError):
        return None


def _parse_hit(hit: dict[str, Any], shop_id: int) -> ProductSnapshot | None:
    """Turn one raw ES hit into a ProductSnapshot. Returns None if the hit
    doesn't have enough shape to be useful (missing sku, name, or price).
    """
    try:
        sku = hit.get("sku")
        name = hit.get("name")
        if not sku or not name:
            return None

        shop_data = hit.get(f"sqpp_data_{shop_id}") or {}
        price = _to_decimal(shop_data.get("price"))
        if price is None:
            return None

        special_price = _to_decimal(shop_data.get("special_price"))
        discount_raw = shop_data.get("special_price_discount")
        discount_percent = int(discount_raw) if isinstance(discount_raw, (int, float)) else None

        brand = None
        brand_data = hit.get("brand_data")
        if isinstance(brand_data, dict):
            brand = brand_data.get("name")

        return ProductSnapshot(
            source="varus",
            sku=str(sku),
            shop_id=shop_id,
            name=str(name),
            url_key=hit.get("url_key") or hit.get("slug"),
            brand=brand,
            price=price,
            special_price=special_price,
            discount_percent=discount_percent,
            special_price_to_date=_parse_date(shop_data.get("special_price_to_date")),
            in_stock=bool(shop_data.get("in_stock", False)),
        )
    except Exception as exc:  # noqa: BLE001 — one bad hit shouldn't kill the batch
        log.warning("varus.parse_hit_failed", error=str(exc), sku=hit.get("sku"))
        return None


class VarusSource(Source):
    name = "varus"

    def __init__(self, timeout_seconds: int = 15) -> None:
        self._timeout = timeout_seconds
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self._timeout,
                headers={"Accept": "application/json"},
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _call(
        self, filters: list[dict[str, Any]], shop_id: int, size: int, from_: int = 0
    ) -> dict[str, Any]:
        params = {
            "request": json.dumps(
                {"_appliedFilters": filters}, ensure_ascii=False, separators=(",", ":")
            ),
            "request_format": "search-query",
            "response_format": "compact",
            "shop_id": str(shop_id),
            "size": str(size),
            "from": str(from_),
            "_source_include": ",".join(_source_include_fields(shop_id)),
        }
        client = self._get_client()

        last_error: Exception | None = None
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                r = await client.get(_ENDPOINT, params=params)
            except httpx.HTTPError as exc:
                last_error = exc
                log.warning("varus.http_error", attempt=attempt, error=str(exc))
            else:
                if r.status_code == 200 and r.headers.get("content-type", "").startswith(
                    "application/json"
                ):
                    return r.json()
                last_error = SourceUnavailable(
                    f"unexpected response: status={r.status_code}, ct={r.headers.get('content-type')}"
                )
                log.warning(
                    "varus.bad_response",
                    attempt=attempt,
                    status=r.status_code,
                    ct=r.headers.get("content-type"),
                )
            if attempt < _MAX_RETRIES:
                await asyncio.sleep(_RETRY_BACKOFF_SECONDS * attempt)
        assert last_error is not None
        raise SourceUnavailable(str(last_error)) from last_error

    async def search_by_name(
        self, query: str, shop_id: int, limit: int = 5
    ) -> list[ProductSnapshot]:
        # Endpoint is case-sensitive and only respects `_appliedFilters[name.like]`.
        # We split on whitespace and AND the tokens together.
        tokens = [t for t in query.lower().split() if t]
        if not tokens:
            return []
        filters: list[dict[str, Any]] = [
            {"attribute": "name", "value": {"like": t}, "scope": "default"} for t in tokens
        ]
        # Filter out anything the user can't actually buy — a discount tracker
        # has nothing to offer on an out-of-stock SKU.
        filters.append(
            {
                "attribute": f"sqpp_data_{shop_id}.in_stock",
                "value": {"eq": True},
                "scope": "default",
            }
        )
        data = await self._call(filters, shop_id=shop_id, size=min(limit, 20))
        hits = data.get("hits") or []
        parsed = [ps for hit in hits if (ps := _parse_hit(hit, shop_id)) is not None]
        return parsed[:limit]

    async def fetch_by_skus(
        self, skus: list[str], shop_id: int
    ) -> list[ProductSnapshot]:
        if not skus:
            return []
        results: list[ProductSnapshot] = []
        # Chunk in case someone's watchlist explodes past _MAX_PAGE_SIZE.
        for i in range(0, len(skus), _MAX_PAGE_SIZE):
            chunk = skus[i : i + _MAX_PAGE_SIZE]
            filters = [
                {"attribute": "sku", "value": {"in": chunk}, "scope": "default"}
            ]
            data = await self._call(filters, shop_id=shop_id, size=_MAX_PAGE_SIZE)
            hits = data.get("hits") or []
            for hit in hits:
                snapshot = _parse_hit(hit, shop_id)
                if snapshot is not None:
                    results.append(snapshot)
        return results
