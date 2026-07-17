# shopping_bot

Telegram-бот для трекинга скидок и акций в украинских супермаркетах.
Первый интегрированный источник — **Varus** (через недокументированный
внутренний API сайта). Архитектура готова под добавление АТБ, Сільпо,
Novus и т.д. — каждый магазин это отдельный `Source`-адаптер.

## Что делает

- Периодически опрашивает источники, забирает актуальные акции.
- Хранит историю цен, детектит новые скидки и изменения.
- Пользователи в Telegram подписываются на категории / бренды / SKU /
  все акции — и получают уведомления при появлении новых скидок.

## Стек

- Python 3.12, `aiogram 3` (Telegram), `httpx` (HTTP)
- SQLAlchemy 2 async + Alembic + SQLite (в MVP) → Postgres при росте
- APScheduler (периодические джобы), `structlog` (логи),
  `pydantic-settings` (конфиг)

## Структура

```
src/shopping_bot/
├── sources/     # адаптеры магазинов (varus, atb, silpo, ...)
├── db/          # модели, сессия
├── bot/         # aiogram handlers
├── scheduler/   # периодические джобы
├── config.py
└── main.py

docs/            # заметки по API магазинов, архитектурные решения
tests/
alembic/
```

## Быстрый старт

```bash
python -m venv .venv
.venv\Scripts\activate      # Windows
pip install -e ".[dev]"
copy .env.example .env      # заполнить TELEGRAM_BOT_TOKEN и т.д.
alembic upgrade head
python -m shopping_bot
```

## Статус

MVP-этап. См. [docs/varus_api_notes.md](docs/varus_api_notes.md) —
заметки по внутреннему API Varus и что ещё нужно проверить.
