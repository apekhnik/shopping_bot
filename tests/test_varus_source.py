from __future__ import annotations

from datetime import date
from decimal import Decimal

import httpx
import pytest

from shopping_bot.sources.varus import VarusSource, _parse_hit


@pytest.fixture
def source() -> VarusSource:
    return VarusSource(timeout_seconds=5)


def _sample_hit(sku: str = "2615912") -> dict:
    return {
        "sku": sku,
        "id": 7423,
        "name": "Сир Ферма кисломолочний 5% 350 г",
        "url_key": "sir-ferma-kislomolochniy-5-350-g",
        "slug": "sir-ferma-kislomolochniy-5-350-g",
        "brand_data": {"name": "Ферма"},
        "sqpp_data_57": {
            "price": 99,
            "special_price": 66.9,
            "special_price_discount": 32,
            "special_price_to_date": "2026-07-22",
            "in_stock": True,
        },
    }


def test_parse_hit_extracts_discounted_product() -> None:
    snap = _parse_hit(_sample_hit(), shop_id=57)
    assert snap is not None
    assert snap.source == "varus"
    assert snap.sku == "2615912"
    assert snap.shop_id == 57
    assert snap.name.startswith("Сир Ферма")
    assert snap.brand == "Ферма"
    assert snap.price == Decimal("99")
    assert snap.special_price == Decimal("66.9")
    assert snap.discount_percent == 32
    assert snap.special_price_to_date == date(2026, 7, 22)
    assert snap.in_stock is True
    assert snap.is_discounted is True


def test_parse_hit_handles_non_discounted() -> None:
    hit = _sample_hit()
    hit["sqpp_data_57"] = {"price": 199, "in_stock": True}
    snap = _parse_hit(hit, shop_id=57)
    assert snap is not None
    assert snap.special_price is None
    assert snap.discount_percent is None
    assert snap.is_discounted is False


def test_parse_hit_returns_none_on_missing_price() -> None:
    hit = _sample_hit()
    hit["sqpp_data_57"] = {"in_stock": True}
    assert _parse_hit(hit, shop_id=57) is None


def test_parse_hit_returns_none_when_shop_has_no_data() -> None:
    hit = _sample_hit()
    hit.pop("sqpp_data_57")
    assert _parse_hit(hit, shop_id=57) is None


def test_parse_hit_handles_bad_date_gracefully() -> None:
    hit = _sample_hit()
    hit["sqpp_data_57"]["special_price_to_date"] = "not-a-date"
    snap = _parse_hit(hit, shop_id=57)
    assert snap is not None
    assert snap.special_price_to_date is None


@pytest.mark.asyncio
async def test_search_by_name_lowercases_and_ands_tokens(
    source: VarusSource, httpx_mock
) -> None:
    httpx_mock.add_response(
        json={"hits": [_sample_hit()], "total": {"value": 1, "relation": "eq"}},
    )
    results = await source.search_by_name("Кокосове МОЛОКО", shop_id=57, limit=5)
    assert len(results) == 1
    assert results[0].sku == "2615912"

    req = httpx_mock.get_requests()[0]
    request_param = req.url.params.get("request")
    assert "кокосове" in request_param
    assert "молоко" in request_param
    assert "Кокосове" not in request_param  # normalized
    await source.aclose()


@pytest.mark.asyncio
async def test_top_discounts_sends_gte_filter_and_sort(
    source: VarusSource, httpx_mock
) -> None:
    httpx_mock.add_response(
        json={
            "hits": [
                {**_sample_hit("A"), "sqpp_data_57": {
                    "price": 100, "special_price": 20,
                    "special_price_discount": 80, "in_stock": True,
                }},
                {**_sample_hit("B"), "sqpp_data_57": {
                    "price": 100, "special_price": 40,
                    "special_price_discount": 60, "in_stock": True,
                }},
            ],
            "total": {"value": 2, "relation": "eq"},
        }
    )
    results = await source.top_discounts(
        shop_id=57, min_discount_percent=50, limit=5
    )
    assert [r.sku for r in results] == ["A", "B"]
    assert results[0].discount_percent == 80

    req = httpx_mock.get_requests()[0]
    assert req.url.params.get("sort") == "sqpp_data_57.special_price_discount:desc"
    request_json = req.url.params.get("request")
    assert "special_price_discount" in request_json
    assert '"gte":50' in request_json
    assert "in_stock" in request_json
    # availability.delivery filter is what actually keeps unbuyable pickup-only
    # items out of the top — see top_discounts docstring.
    assert "availability.delivery" in request_json
    await source.aclose()


@pytest.mark.asyncio
async def test_top_discounts_respects_limit(
    source: VarusSource, httpx_mock
) -> None:
    hits = []
    for i, disc in enumerate([90, 85, 80, 70, 60, 55]):
        h = _sample_hit(f"SKU{i}")
        h["sqpp_data_57"] = {
            "price": 100, "special_price": 10,
            "special_price_discount": disc, "in_stock": True,
        }
        hits.append(h)
    httpx_mock.add_response(
        json={"hits": hits, "total": {"value": len(hits), "relation": "eq"}}
    )
    results = await source.top_discounts(
        shop_id=57, min_discount_percent=30, limit=3
    )
    assert len(results) == 3
    assert [r.discount_percent for r in results] == [90, 85, 80]
    await source.aclose()


@pytest.mark.asyncio
async def test_fetch_by_skus_returns_empty_on_empty_input(source: VarusSource) -> None:
    assert await source.fetch_by_skus([], shop_id=57) == []
    await source.aclose()


@pytest.mark.asyncio
async def test_fetch_by_skus_parses_multiple_hits(
    source: VarusSource, httpx_mock
) -> None:
    httpx_mock.add_response(
        json={
            "hits": [_sample_hit("A"), _sample_hit("B")],
            "total": {"value": 2, "relation": "eq"},
        }
    )
    results = await source.fetch_by_skus(["A", "B"], shop_id=57)
    assert [r.sku for r in results] == ["A", "B"]
    await source.aclose()
