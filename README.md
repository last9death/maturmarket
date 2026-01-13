# maturmarket

Telegram-бот для мониторинга товаров maturmarket.ru без headless-браузера: только HTTP-запросы и парсинг HTML.

## Возможности

- `/check <url>` — проверка карточки товара.
- `/find <запрос>` — поиск товаров по сайту.
- `/watch <url>` — подписка на изменения.
- `/watchlist` — список подписок.
- `/unwatch <id>` — удалить подписку.
- `/stats` — статистика (админская).
- `/scanout [limit]` — проверка всех товаров и список отсутствующих (админская).

## Быстрый старт

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

export TELEGRAM_BOT_TOKEN="<token>"
python -m maturmarket_bot.telegram_bot
```

## Переменные окружения

- `TELEGRAM_BOT_TOKEN` — токен Telegram-бота.
- `DATABASE_PATH` — путь к SQLite (по умолчанию `maturmarket.sqlite3`).
- `ADMIN_TG_IDS` — список Telegram ID администраторов через запятую (по умолчанию `46375955,893022305,951910450`).
- `REQUEST_TIMEOUT_SECONDS` — таймаут HTTP (по умолчанию 10).
- `CACHE_TTL_SECONDS` — TTL кэша (по умолчанию 90).
- `USER_RATE_LIMIT_PER_HOUR` — лимит проверок на пользователя (по умолчанию 30).
- `DOMAIN_RATE_LIMIT_PER_MINUTE` — глобальный лимит домена (по умолчанию 60).
- `MIN_DELAY_SECONDS` / `MAX_DELAY_SECONDS` — случайная задержка между запросами.
- `WATCH_INTERVAL_MINUTES` — интервал фоновой проверки подписок.
- `SCAN_MAX_PRODUCTS` — лимит товаров для массовой проверки (по умолчанию 200).

## Примечания

- Если сайт блокирует запросы или отдаёт данные только после JS, бот вернёт `UNKNOWN` и запишет лог.
- Селекторы и ключевые слова для наличия собраны в `maturmarket_bot/parser.py`.
