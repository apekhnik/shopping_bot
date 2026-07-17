# Varus internal API — notes

Официального публичного API у Varus нет. Ниже — то, что удалось
раскопать через DevTools на сайте varus.ua. Всё это **недокументировано**
и может измениться в любой момент.

## Стек сайта

- Vue Storefront (фронтенд).
- Elasticsearch (бэкенд каталога), доступ через прокси-эндпоинт вида
  `/api/catalog/.../_search`.

## Эндпоинт

```
GET https://varus.ua/api/catalog/vue_storefront_catalog_2/product_v2/_search
```

### Query-параметры

| Параметр | Назначение |
|---|---|
| `request` | JSON (urlencoded) с фильтрами и сортировкой |
| `request_format` | `search-query` |
| `response_format` | `compact` — плоский список товаров в `hits`, без ES-обвязки |
| `shop_id` | id магазина/региона. В найденном примере — `57`. Другие города — надо смотреть через DevTools |
| `size` | сколько товаров за раз |
| `from` | пагинация |
| `_source_include` | какие поля вернуть |

### Внутри `request` — `_appliedFilters`

Реальные фильтры из живого запроса на странице акций:

```json
{"attribute": "sku", "value": {"in": [список SKU]}, "scope": "default"}
{"attribute": "visibility", "value": {"in": [2, 4]}, "scope": "default"}
{"attribute": "status", "value": {"in": [1]}, "scope": "default"}
{"attribute": "sqpp_data_region_default.in_stock", "value": {"eq": true}, "scope": "default"}
{"attribute": "markdown_id", "value": {"nin": null}, "scope": "default"}
```

`markdown_id nin null` — по всей видимости, "только товары с активной
уценкой/акцией". Гипотеза: этот фильтр можно использовать вместо
ручного списка SKU, чтобы получить все текущие акции. **Не
подтверждено фактическим тестовым запросом.**

## Поля ответа

Приходят стабильно:

```
sku, id, name, url_key, url_path, slug
brand_data.name
description
category / category_ids
stock.is_in_stock, stock.qty, stock.manage_stock, stock.is_qty_decimal
sqpp_data_region_default.price, .in_stock, .available
weight, volume, packingtype
is_new, is_18_plus, is_tobacco
```

Заявлены в `_source_include`, но пустые у товара без активной акции
(предположительно заполнены при активной — **не подтверждено**):

```
regular_price
special_price_discount
special_price_to_date
markdown_id
markdown_title
markdown_discount
markdown_description
```

## Гипотеза по логике цены

- `sqpp_data_region_default.price` — текущая цена показа
  (акционная, если акция активна; обычная — если нет).
- `regular_price` — обычная цена без скидки.
- `markdown_discount` / `special_price_discount` — величина скидки.
- `markdown_id != null` → товар в уценке.

## Что надо проверить перед реализацией адаптера (task #2)

1. Тестовый запрос с `markdown_id: {nin: null}` без списка SKU:
   - реально ли возвращаются только акционные товары;
   - что в `regular_price`, `markdown_discount`, `special_price_discount`,
     `markdown_title` у таких товаров;
   - как однозначно вычислить старую/новую цену и % скидки.
2. Нужны ли заголовки (`User-Agent`, `Referer`), чтобы бэкенд не
   отдавал ошибку/пустой ответ.
3. Лимиты: максимальный `size`, работает ли `from`, есть ли
   rate-limit / бан по IP.
4. Актуальные `shop_id` для разных городов.
5. Стабильность формата ответа — на что делать fallback / алерт.

## Риски

- Эндпоинт не публичный. Может измениться или закрыться.
- Частые запросы к чужому проду — нужен разумный интервал
  (по умолчанию у нас `SCAN_INTERVAL_SECONDS=3600`, т.е. раз в час).
- Возможен бан по IP/User-Agent при агрессивной частоте — ротация
  заголовков и уважение robots.txt на своей стороне.
