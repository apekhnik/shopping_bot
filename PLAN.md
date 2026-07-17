# План и текущее состояние — shopping_bot

Telegram-бот для трекинга скидок в супермаркетах Украины. Первый (и пока
единственный) источник — Varus. Данные тянем через недокументированный
внутренний API сайта varus.ua.

**Репо:** https://github.com/apekhnik/shopping_bot
**Ветка:** `main` (автодеплой в Railway на каждый push)
**Продовский тег коммита на момент этой записи:** `839cb71`

---

## Что сейчас умеет бот

**Watchlist-модель**: пользователь сам указывает, за какими товарами
следить. Бот не сканирует весь каталог.

Команды и кнопки (reply-клавиатура внизу чата):

| Кнопка / команда | Что делает |
|---|---|
| `/start` | Регистрирует пользователя, показывает клавиатуру, задаёт `default_shop_id=57` |
| `➕ Додати` / `/add <query>` | FSM-flow: спрашивает запрос → ищет в Varus (5 результатов) → показывает **фото-карточки** с кнопкой "🔔 Відстежувати" |
| `📋 Мій список` / `/list` | Один моноширинный текст-таблица с колонками "% скидки / цена / примечание", названия кликабельные, кнопки `🗑 1 … 🗑 N` под ним |
| `🎲 Випадковий снек` | 3 случайных снека из зашитого списка (`bot/random_pick.py`) — карточки с фото |
| `/cancel` | Выход из любого FSM-состояния |
| `/help` | То же, что `/start` |

Фоновая работа:
- **Скан-джоба** APScheduler раз в час опрашивает **только те SKU**,
  которые есть в чьих-то вотчлистах (`SELECT DISTINCT`), сравнивает с
  `product_state`, генерит события.
- События: `discount_started`, `discount_deepened`, `discount_ended`.
  Изменения только по стоку / только по обычной цене без промо
  событиями не считаются (для MVP).
- **Уведомления** — фото товара + подпись, дедуп через
  `notifications_sent` по `(user, source, sku, event_type, discount%)`.
  Уважает `notify_min_discount_percent` (кроме `discount_ended` —
  тот всегда доходит).

---

## Инфраструктура

**Railway** (проект `shopping_bot`) содержит два сервиса:
- **Postgres** — один volume, автоматически создаёт `DATABASE_URL`.
- **shopping_bot** — Docker-сборка из этого репо. Переменные:
  - `DATABASE_URL` = `${{Postgres.DATABASE_URL}}` (референс)
  - `TELEGRAM_BOT_TOKEN` — от BotFather

Всё остальное (интервал скана, timeout HTTP, default shop) имеет
дефолты в `src/shopping_bot/config.py`. Смотри `.env.example` в корне —
там полный список переменных.

**Что деплоится:** каждый push в `main` → GitHub → Railway тянет →
`Dockerfile` → `alembic upgrade head` → `python -m shopping_bot`. Логи
доступны в Deploy Logs каждого сервиса.

---

## История задач (все done)

| # | Задача | Статус |
|---|---|---|
| 1 | Скаффолд репы (структура, docker, alembic) | ✅ |
| 2 | Валидация Varus API живыми запросами | ✅ |
| 3 | Варус-адаптер (`search_by_name` + `fetch_by_skus`) | ✅ |
| 4 | Модели БД + миграция watchlist-схемы (4 таблицы) | ✅ |
| 5 | Скан-джоба + change detection | ✅ |
| 6 | Telegram-бот (команды + notifier) | ✅ |

Пост-MVP polish (не выделялся в задачи):
- Reply-клавиатура + FSM для `/add`
- Меню слэш-команд в Telegram (`set_my_commands`)
- Один моноширинный список одним сообщением с `🗑 N` кнопками
- Фото-карточки в поиске и уведомлениях
- Кнопка "🎲 Випадковий снек"
- httpx-логи задушены, чтобы не спамили INFO'ы в Railway

---

## Архитектура

Полное описание — [`docs/architecture.md`](docs/architecture.md).
Контракт Varus API — [`docs/varus_api_notes.md`](docs/varus_api_notes.md).

Коротко:

```
src/shopping_bot/
├── sources/       — Varus-адаптер, интерфейс Source + ProductSnapshot
├── db/            — SQLAlchemy async engine, модели, сессия
├── scheduler/     — events (pure detect_event), scan (DB + sources), runner (APScheduler)
├── bot/           — dispatcher, handlers, keyboards, states (FSM),
│                    rendering, notifier, random_pick
├── config.py      — pydantic-settings, читает .env / env-переменные
├── logging_setup.py — structlog + глушим httpx
└── main.py        — точка входа: ping DB → smoke Varus → запустить бот + скан
```

Данные — 4 таблицы:

- `users` — Telegram id, shop_id по умолчанию.
- `watched_products` — вотчлист (unique per user + source + sku + shop).
- `product_state` — последнее известное состояние SKU (PK по source+sku+shop).
- `notifications_sent` — дедуп-лог.

---

## Что нужно знать, чтобы продолжить

### Стек и запуск локально

```bash
python -m venv .venv
.venv\Scripts\activate    # Windows
pip install -e ".[dev]"
copy .env.example .env    # заполнить TELEGRAM_BOT_TOKEN
alembic upgrade head       # локальная SQLite
python -m shopping_bot
```

Локально по дефолту используется SQLite (`sqlite+aiosqlite:///./shopping_bot.db`).
При наличии `DATABASE_URL` из Railway/etc — переключается на Postgres автоматом
(`db/session.py` умеет нормализовать `postgresql://` в `postgresql+asyncpg://`).

### Тесты

```bash
pytest
```

Проверяют:
- `test_varus_source.py` — парсинг ответа, поиск с мокнутым httpx.
- `test_events.py` — детектор событий (чистая функция).
- `test_scan.py` — полный цикл скана над in-memory SQLite.
- `test_rendering.py` — рендер поисковой карточки, строки списка, ивента.
- `test_smoke.py` — версия и настройки.

### Ключевые паттерны

- **HTTP-клиент** — один `httpx.AsyncClient` на инстанс `VarusSource`,
  lazy init, `aclose()` на shutdown. Ретраи 3 раза с экспоненциальным
  backoff'ом; при провале — `SourceUnavailable`.
- **Скан** — один broken source не рушит цикл, ловим `SourceUnavailable`
  и логируем.
- **Уведомления** — фото + подпись; если фото не грузится, есть fallback
  на текст. `TelegramForbiddenError` (юзер заблокировал бота) и
  `TelegramRetryAfter` (rate-limit) обрабатываются отдельно.
- **Дедуп** — по `(user_id, event_type, discount_percent_at_notify)`.
  Значит "тот же товар, тот же % скидки, тот же тип события" ни разу
  не задублируется.

### Добавить новый источник (АТБ, Сільпо…)

1. Создать `src/shopping_bot/sources/<name>.py` с классом-наследником
   `Source` и полями `name`, `search_by_name`, `fetch_by_skus`, `aclose`.
2. Экспортировать в `sources/__init__.py`.
3. В `main.py` добавить в `sources` dict:
   `sources = {"varus": VarusSource(...), "atb": AtbSource(...)}`.
4. В `rendering.py` в `_URL_BASE` и `_IMG_URL_BUILDER` добавить паттерн
   для страницы товара и картинки.

Никаких изменений в скан-джобе или боте не потребуется — вся логика
диффа и уведомлений уже source-agnostic.

### Расширить список случайных снеков

`src/shopping_bot/bot/random_pick.py` → массив `SNACK_QUERIES`. Просто
дописать строки, запушить. Ничего компилировать не надо.

---

## Что можно сделать дальше (не обязательно)

Ничего из этого сейчас не в работе — это идеи для следующих итераций:

- **"Топ знижок" — разведрежим по каталогу.** Отдельная кнопка (типа
  `🔥 Топ знижок`) или команда `/top`. Пользователь задаёт порог (напр.
  `≥ 30%`), бот отдаёт N товаров с самой большой скидкой в его магазине.
  Отличается от watchlist тем, что это разовый показ, а не подписка.

  Технически **реализуемо на уже готовом эндпоинте**: тот же
  `_appliedFilters`, только вместо фильтра по SKU:
  ```json
  [
    {"attribute": "sqpp_data_<shop>.special_price_discount", "value": {"gte": 30}, "scope": "default"},
    {"attribute": "sqpp_data_<shop>.in_stock", "value": {"eq": true}, "scope": "default"}
  ]
  ```
  По нашему тесту на shop 57 с `> 0` возвращается ~7 000 товаров, с
  порогом 30% будет в разы меньше. Сортировка по проценту скидки:
  либо через ES `sort` в теле `request` (не проверено, но эндпоинт —
  прямой прокси в ES, скорее всего сработает), либо клиентская
  сортировка после фетча. Со `_source_include` (уже настроен) один
  товар ~1 КБ — даже 5 000 товаров это ~5 МБ, для on-demand команды
  терпимо. Порог хранить в `users` (доп поле `top_min_discount_percent`)
  или спрашивать каждый раз через FSM.

- **Уведомления при возврате в сток** — сейчас `back_in_stock` не
  событие. Легко добавить: `EventType.BACK_IN_STOCK`, доп ветка в
  `detect_event`.
- **Порог `notify_min_discount_percent` через UI** — сейчас у всех
  дефолт `1`. Добавить команду `/settings` или отдельный экран.
- **Другой магазин по умолчанию** — сейчас всем ставится `shop_id=57`.
  Дать `/setshop <id>` с валидацией через тестовый запрос.
- **Дайджест раз в день** — если у юзера много подписок, батчить
  события в одно сообщение "5 знижок сьогодні".
- **Экспорт списка** — `/export` в JSON/CSV.
- **Групповая работа** — сейчас чат-only. Если хочется работать
  в группах — надо чуть переработать `_ensure_user` (там `from_user`,
  а в группе это тот, кто прислал сообщение, что окей).
- **Второй магазин (ATB / Сільпо)** — см. "Добавить новый источник".
- **Мониторинг деградации API** — таблица `scan_runs` с `errors_count`,
  алерт разработчику при пороге.
- **Sentry / метрики** — если станет много юзеров.

---

## Риски и ограничения

- **Эндпоинт Varus не публичный** и не документирован. Может измениться
  или закрыться в любой момент. В коде на этот случай:
  - retry + backoff в `_call`;
  - `SourceUnavailable` → сжирается скан-джобой без падения всего;
  - структурные логи — по ним видно деградацию.
- **Rate-limit Varus** не тестировался. Опрос раз в час — не агрессивно,
  но если пойдут тысячи юзеров с большими вотчлистами — стоит замерить.
- **Telegram API** — 30 сообщений/сек в среднем. При массовой рассылке
  рано или поздно упрёмся; сейчас не батчим.
- **Railway Free tier** — 1 GB Postgres, 512 MB RAM, $5 credit/мес.
  При нагрузке MVP хватает с большим запасом. Оценка потолка — сотни
  тысяч пользователей на текущей архитектуре.

---

## История файла

Изначально этот план лежал вне репозитория (на рабочем столе). Он был
сильно рассинхронизирован с реальностью (гипотезы про фильтр
`markdown_id`, поля `regular_price`, UX "подписки на категории" — всё
оказалось иначе). Файл переписан заново и перемещён в корень репы
2026-07-17 после закрытия всех 6 базовых задач и pos-MVP polish'а.
