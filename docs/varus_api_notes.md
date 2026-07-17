# Varus internal API — validated notes

Официального публичного API у Varus нет. Ниже — то, что подтверждено
живыми запросами к недокументированному внутреннему API сайта varus.ua
(2026-07-17). Всё может измениться в любой момент — эндпоинт закрытый.

## TL;DR

- **Эндпоинт**:
  `GET https://varus.ua/api/catalog/vue_storefront_catalog_2/product_v2/_search`
- **Заголовки не нужны** — работает из голого fetch без cookies/UA/Referer.
- **Правильный фильтр акций** (то, что было в плане — `markdown_id nin null` —
  ничего не фильтрует, дефолтный ES-кап 10 000):

  ```json
  [
    {"attribute": "sqpp_data_<shop_id>.special_price_discount", "value": {"gt": 0}, "scope": "default"},
    {"attribute": "sqpp_data_<shop_id>.in_stock",               "value": {"eq": true}, "scope": "default"}
  ]
  ```

- **Пагинация**: `size` до **1000** отдаёт полную страницу без обрезаний;
  `from` работает; `total` для нашего фильтра приходит с точным
  `relation: "eq"` (в примере shop 57 — **7154 товара в акциях в стоке**).

## Пример URL

```
https://varus.ua/api/catalog/vue_storefront_catalog_2/product_v2/_search
  ?request={"_appliedFilters":[
      {"attribute":"sqpp_data_57.special_price_discount","value":{"gt":0},"scope":"default"},
      {"attribute":"sqpp_data_57.in_stock","value":{"eq":true},"scope":"default"}
    ]}
  &request_format=search-query
  &response_format=compact
  &shop_id=57
  &size=1000
  &from=0
```

## Модель цены (важное — план был неверен)

Цена и скидка **привязаны к конкретному магазину**, а не к товару целиком.
Каждый товар содержит объект `sqpp_data_<shop_id>` под каждый магазин,
где он продаётся, плюс `sqpp_data_region_default` со значениями по региону
по умолчанию.

Структура `sqpp_data_<shop_id>`:

| Поле | Значение |
|---|---|
| `price` | обычная цена (без скидки) |
| `special_price` | акционная цена (если акция активна) |
| `special_price_discount` | целочисленный % скидки, напр. 27 |
| `special_price_from_date` | `YYYY-MM-DD`, начало акции |
| `special_price_to_date` | `YYYY-MM-DD`, конец. У "постоянных" скидок бывает `2050-12-31` |
| `special_promo_type` | int (видели 1 и 3) — тип промо, назначение неясно |
| `in_stock` | bool |
| `qty` | остаток на конкретном магазине |
| `available` | bool (можно ли купить: доставка/самовывоз/…) |
| `availability` | объект с `{delivery, pickup, today, other_market, other_regions, shipping}` |

`sqpp_data_region_default` — почти то же самое, но по региону, а не магазину.

**Как считать скидку:**
- Есть акция ⇔ `special_price_discount > 0`.
- Старая цена = `price`, новая = `special_price`, % скидки = `special_price_discount`.

## Промо-кампании

`promo_offers_<shop_id>` — массив слагов активных промо-кампаний, например:
`["zymova-pidtrymka", "natsionalnyi-keshbek", "tsina-tyzhnia", "shchotyzhnevi-znyzhky"]`.
Может быть пустым (`[]`) — тогда скидка "техническая", без брендированной
кампании. Полезно для группировки уведомлений: "новинки в кампании
'ціна тижня'".

## `markdown_*` (уценка) — НЕ путать с акциями

- `is_markdown` (bool) и (видимо) `markdown_id` — это про **уценку** конкретной
  единицы товара (истёкший срок, повреждённая упаковка), а не про плановую
  акцию.
- В нашей проверке `is_markdown=true` дал **0 товаров** — либо у Varus сейчас
  нет уценки, либо этот флаг заведён иначе. Для трекера скидок он нам **не
  нужен** — работаем через `special_price_discount`.

## URL товара

`https://varus.ua/{url_key}` — возвращает 200 OK.
Поле `url_key` = `url_path` = `slug` в нашем сэмпле (все три идентичны).

## Картинка товара

Отдельного поля с URL картинки в ответе `_search` **нет**. Есть только
`fv_image_timestamp` (int, unix timestamp — вероятно cache-buster). Реальный
URL картинки надо либо:
- достать из HTML страницы товара при первом сохранении,
- либо угадать по паттерну статики Magento (`static.varus.ua/media/catalog/product/...`)
  — не проверено.

Для MVP — не критично; в Telegram-сообщении можно давать ссылку на страницу,
пользователь увидит картинку на сайте.

## Лимиты и пагинация

- `size` — работает как минимум до **1000** (проверено).
- `from` — работает; на `from >= total` возвращает пустой массив, без 400.
- `total.relation` — `"eq"` (точно) когда результат меньше 10 000; `"gte"`
  (усечено ES) когда больше. С двумя фильтрами (discount + in_stock) для
  shop 57 получаем ровно **7154 — всегда `eq`**.
- Rate-limit не тестировался. По умолчанию бот будет опрашивать раз в час
  (`SCAN_INTERVAL_SECONDS=3600`), это далеко от агрессивной частоты.

## Что делать с `_source_include`

Ответ жирный — под каждый магазин отдельные `sqpp_data_*`, `promo_offers_*`,
`category_listing_rank_*`. Один товар легко >20 КБ. При загрузке страницы
на 1000 товаров — 20+ МБ.

**Оптимизация:** передавать `_source_include=` со списком нужных полей:

```
sku,id,name,url_key,slug,brand_data,category_ids,
sqpp_data_<shop_id>.price,
sqpp_data_<shop_id>.special_price,
sqpp_data_<shop_id>.special_price_discount,
sqpp_data_<shop_id>.special_price_from_date,
sqpp_data_<shop_id>.special_price_to_date,
sqpp_data_<shop_id>.in_stock,
sqpp_data_<shop_id>.qty,
promo_offers_<shop_id>,
is_new
```

Ожидаем сокращения в ~10-20 раз.

## Ошибки в исходном плане (исправлено)

| Что было в плане | Что на самом деле |
|---|---|
| Фильтр акций = `markdown_id nin null` | Ничего не фильтрует. Правильный — `sqpp_data_<shop>.special_price_discount > 0` |
| `regular_price` / `markdown_discount` — поля товара | Нет таких полей в ответе. Всё в `sqpp_data_<shop>` |
| Заголовки, вероятно, нужны | Не нужны. 200 OK без всяких заголовков |
| Уценка = акция | Разные вещи. `is_markdown` — уценка (истёкший срок/повреждение), `special_price` — плановая скидка |

## Что ещё не проверено

- Точный шейп `promo_offers_<shop_id>[i]` (только слаг или объект с
  началом/концом кампании?). Пока видим только массив слагов.
- Rate-limit / бан по IP при частых запросах.
- Другие `shop_id` — 57 подтверждён, для других городов нужен свой id.
  План проверки: открыть `varus.ua`, выбрать магазин через переключатель
  → в DevTools → Network подсмотреть `shop_id` в запросах.
- Категории: как получить список категорий (`category_ids` возвращает
  массив int, но без имён). Отдельный ES-индекс, вероятно.
- Что такое `special_promo_type` (видели 1 и 3).

## Риски

- Эндпоинт не публичный. Может быть закрыт / изменён без предупреждения.
  Нужен алерт при неожиданном формате ответа (см. task #5).
- 1 запрос = 1000 товаров = один HTTP-вызов. Для полного скана shop 57
  нужно ~8 запросов. Разумный интервал между запросами — 1-2 сек, чтобы
  не выглядеть как атака.
