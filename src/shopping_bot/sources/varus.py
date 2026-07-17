from __future__ import annotations

from collections.abc import AsyncIterator

from shopping_bot.sources.base import DiscountedProduct, Source


class VarusSource(Source):
    """Varus discounts adapter — talks to the undocumented internal API of varus.ua.

    See docs/varus_api_notes.md for the discovered endpoint and open questions.
    Not implemented yet — first we validate the API contract, then fill this in.
    """

    name = "varus"

    def __init__(self, shop_id: int) -> None:
        self.shop_id = shop_id

    async def iter_discounts(self) -> AsyncIterator[DiscountedProduct]:  # pragma: no cover
        raise NotImplementedError("VarusSource.iter_discounts is not implemented yet")
        yield  # keep the async generator signature
