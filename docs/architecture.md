# Architecture

Watchlist-based grocery discount bot.

## UX (для MVP)

1. `/start` — регистрируем пользователя, спрашиваем магазин по умолчанию.
2. `/add <название>` — бот делает поиск по каталогу магазина,
   показывает топ-5 совпадений с текущими ценами и inline-кнопками
   "🔔 отслеживать". Тап — товар добавлен в вотчлист пользователя.
3. `/list` — список отслеживаемых товаров с их текущим статусом
   (`—25%`, `в стоке`, `нет акции`, `нет в наличии`).
4. `/remove` — убрать товар из вотчлиста.
5. При появлении/углублении скидки на отслеживаемом товаре — пуш.

## Что бот **не** делает (MVP)

- Не сканирует весь каталог "все акции".
- Не хранит историю цен по всем товарам.
- Не строит графики "как менялась цена молока за год".
- Не даёт подписаться на бренд/категорию целиком.

Всё это — потенциальные фичи "фазы 2", но текущий фокус чётко на
"я слежу за конкретными товарами".

## Data model (4 таблицы)

### `users`
| Поле | Тип | Заметки |
|---|---|---|
| `telegram_user_id` | BIGINT PK | id из Telegram |
| `username` | TEXT | опционально, для дебага |
| `default_shop_id` | INT | какой магазин Varus по умолчанию |
| `timezone` | TEXT | для тайминга уведомлений (пока не используется) |
| `created_at` | TIMESTAMPTZ | |

### `watched_products`
Что каждый юзер отслеживает.
| Поле | Тип | Заметки |
|---|---|---|
| `id` | BIGINT PK | |
| `user_id` | BIGINT FK → users | |
| `source` | TEXT | `"varus"` (задел под ATB/Silpo/…) |
| `sku` | TEXT | external id в системе магазина |
| `shop_id` | INT | магазин наблюдения |
| `name_cache` | TEXT | для отображения без похода в API |
| `url_key` | TEXT | для генерации ссылки |
| `notify_min_discount_percent` | INT | по умолчанию 1 |
| `added_at` | TIMESTAMPTZ | |

Unique: `(user_id, source, sku, shop_id)`.

### `product_state`
Последнее известное состояние отслеживаемого SKU в магазине.
Не история — на каждом скане перезаписываем.
| Поле | Тип | Заметки |
|---|---|---|
| `source` | TEXT | часть PK |
| `sku` | TEXT | часть PK |
| `shop_id` | INT | часть PK |
| `price` | NUMERIC(10,2) | обычная цена |
| `special_price` | NUMERIC(10,2) NULL | акционная (если есть) |
| `discount_percent` | INT NULL | % скидки |
| `special_price_to_date` | DATE NULL | до какого числа акция |
| `in_stock` | BOOL | |
| `checked_at` | TIMESTAMPTZ | когда последний раз проверяли |

PK: `(source, sku, shop_id)`.

### `notifications_sent`
Дедуп: не шлём одно и то же дважды.
| Поле | Тип | Заметки |
|---|---|---|
| `id` | BIGINT PK | |
| `user_id` | BIGINT FK → users | |
| `source` | TEXT | |
| `sku` | TEXT | |
| `shop_id` | INT | |
| `event_type` | TEXT | `discount_started` / `discount_deepened` / `discount_ended` |
| `discount_percent_at_notify` | INT NULL | |
| `sent_at` | TIMESTAMPTZ | |

Правило дедупа: не отправлять `event_type=discount_started` пользователю
по SKU, если предыдущее уведомление по этому SKU было того же типа с
тем же `discount_percent_at_notify`.

## Скан-цикл

Раз в час (`SCAN_INTERVAL_SECONDS`):

1. `SELECT DISTINCT (source, sku, shop_id) FROM watched_products` —
   получаем список того, что вообще нужно проверить.
2. Группируем по `(source, shop_id)` и на каждую группу зовём
   `source.fetch_by_skus(skus)` — один HTTP-запрос на группу.
3. Для каждого товара:
   - берём предыдущий `product_state`;
   - сравниваем с новым;
   - если появилась/углубилась/пропала акция или изменился сток →
     генерим event;
   - апдейтим `product_state` (upsert).
4. Для каждого event:
   - находим всех пользователей, у которых этот SKU в вотчлисте
     и порог `notify_min_discount_percent` пройден;
   - проверяем дедуп по `notifications_sent`;
   - шлём уведомление, пишем строку в `notifications_sent`.

## Source-интерфейс

```python
class Source:
    name: str
    async def search_by_name(self, query: str, shop_id: int, limit: int) -> list[SearchResult]: ...
    async def fetch_by_skus(self, skus: list[str], shop_id: int) -> list[ProductState]: ...
```

Первый метод — для команды `/add`, второй — для скан-цикла.
Первая имплементация — `VarusSource`, вторая (ATB и т.д.) — потом.
