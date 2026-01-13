from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class Settings:
    telegram_token: str
    database_path: str
    admin_tg_ids: list[int]
    request_timeout_seconds: float = 10.0
    cache_ttl_seconds: int = 90
    user_rate_limit_per_hour: int = 30
    domain_rate_limit_per_minute: int = 60
    min_delay_seconds: float = 0.8
    max_delay_seconds: float = 2.5
    watch_interval_minutes: int = 15
    scan_max_products: int = 200


def _parse_admin_ids(raw: str) -> list[int]:
    if not raw:
        return []
    ids: list[int] = []
    for item in raw.split(","):
        value = item.strip()
        if value.isdigit():
            ids.append(int(value))
    return ids


def load_settings() -> Settings:
    telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    database_path = os.environ.get("DATABASE_PATH", "maturmarket.sqlite3")
    admin_ids = _parse_admin_ids(
        os.environ.get("ADMIN_TG_IDS", "46375955,893022305,951910450")
    )
    return Settings(
        telegram_token=telegram_token,
        database_path=database_path,
        admin_tg_ids=admin_ids,
        request_timeout_seconds=float(os.environ.get("REQUEST_TIMEOUT_SECONDS", "10")),
        cache_ttl_seconds=int(os.environ.get("CACHE_TTL_SECONDS", "90")),
        user_rate_limit_per_hour=int(os.environ.get("USER_RATE_LIMIT_PER_HOUR", "30")),
        domain_rate_limit_per_minute=int(os.environ.get("DOMAIN_RATE_LIMIT_PER_MINUTE", "60")),
        min_delay_seconds=float(os.environ.get("MIN_DELAY_SECONDS", "0.8")),
        max_delay_seconds=float(os.environ.get("MAX_DELAY_SECONDS", "2.5")),
        watch_interval_minutes=int(os.environ.get("WATCH_INTERVAL_MINUTES", "15")),
        scan_max_products=int(os.environ.get("SCAN_MAX_PRODUCTS", "200")),
    )
