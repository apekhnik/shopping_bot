from __future__ import annotations

import random

from shopping_bot.sources.base import ProductSnapshot, Source

# Curated snack-flavored search terms. Easy to edit — no code changes needed.
# Kept lowercase because the Varus search endpoint is case-sensitive
# (we still lowercase on the way in, but this keeps the source of truth clean).
SNACK_QUERIES: list[str] = [
    "чіпси",
    "снек",
    "горіхи",
    "сухарики",
    "попкорн",
    "печиво",
    "шоколад",
    "батончик",
    "крекер",
    "фісташки",
    "мигдаль",
    "кеш'ю",
]


async def pick_random_snacks(
    source: Source,
    shop_id: int,
    count: int = 3,
    rng: random.Random | None = None,
) -> list[ProductSnapshot]:
    """Pick `count` random snack products from the source.

    Strategy: shuffle the query list, walk it until we have enough distinct
    picks, taking one random hit per query. Distinct = distinct SKU.
    """
    r = rng or random.SystemRandom()
    queries = list(SNACK_QUERIES)
    r.shuffle(queries)

    picks: list[ProductSnapshot] = []
    seen_skus: set[str] = set()

    for query in queries:
        if len(picks) >= count:
            break
        results = await source.search_by_name(query, shop_id=shop_id, limit=10)
        if not results:
            continue
        # Random hit within this query's page, biasing away from the top 1-2
        # so the same 'star' item doesn't dominate.
        pool = [s for s in results if s.sku not in seen_skus]
        if not pool:
            continue
        pick = r.choice(pool)
        picks.append(pick)
        seen_skus.add(pick.sku)

    return picks
