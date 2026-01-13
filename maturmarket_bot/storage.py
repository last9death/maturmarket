from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Optional

from maturmarket_bot.models import AvailabilityStatus, Product


@dataclass
class Watch:
    id: int
    user_id: int
    product_url: str
    created_at: datetime
    last_status: AvailabilityStatus
    last_price: Optional[float]
    last_notified_status: Optional[AvailabilityStatus]
    is_active: bool


class Storage:
    def __init__(self, path: str) -> None:
        self.path = path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tg_id INTEGER UNIQUE NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS watches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    product_url TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    last_status TEXT,
                    last_price REAL,
                    last_notified_status TEXT,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                );

                CREATE TABLE IF NOT EXISTS product_cache (
                    product_url TEXT PRIMARY KEY,
                    title TEXT,
                    last_price REAL,
                    last_status TEXT,
                    last_checked_at TEXT
                );
                """
            )

    def get_or_create_user(self, tg_id: int) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT id FROM users WHERE tg_id = ?", (tg_id,)).fetchone()
            if row:
                return int(row["id"])
            created_at = datetime.utcnow().isoformat()
            cursor = conn.execute(
                "INSERT INTO users (tg_id, created_at) VALUES (?, ?)",
                (tg_id, created_at),
            )
            return int(cursor.lastrowid)

    def add_watch(self, user_id: int, product_url: str) -> int:
        created_at = datetime.utcnow().isoformat()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO watches (user_id, product_url, created_at, is_active)
                VALUES (?, ?, ?, 1)
                """,
                (user_id, product_url, created_at),
            )
            return int(cursor.lastrowid)

    def list_watches(self, user_id: int) -> list[Watch]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM watches WHERE user_id = ? AND is_active = 1",
                (user_id,),
            ).fetchall()
        return [self._row_to_watch(row) for row in rows]

    def remove_watch(self, watch_id: int, user_id: int) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE watches SET is_active = 0 WHERE id = ? AND user_id = ?",
                (watch_id, user_id),
            )
            return cursor.rowcount > 0

    def update_watch_status(self, watch_id: int, status: AvailabilityStatus, price: Optional[float]) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE watches SET last_status = ?, last_price = ? WHERE id = ?",
                (status.value, price, watch_id),
            )

    def update_watch_notified_status(self, watch_id: int, status: AvailabilityStatus) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE watches SET last_notified_status = ? WHERE id = ?",
                (status.value, watch_id),
            )

    def list_active_watches(self) -> list[Watch]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM watches WHERE is_active = 1").fetchall()
        return [self._row_to_watch(row) for row in rows]

    def get_user_tg_id(self, user_id: int) -> Optional[int]:
        with self._connect() as conn:
            row = conn.execute("SELECT tg_id FROM users WHERE id = ?", (user_id,)).fetchone()
        if not row:
            return None
        return int(row["tg_id"])

    def count_users(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS count FROM users").fetchone()
        return int(row["count"]) if row else 0

    def count_active_watches(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS count FROM watches WHERE is_active = 1").fetchone()
        return int(row["count"]) if row else 0

    def count_cached_products(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS count FROM product_cache").fetchone()
        return int(row["count"]) if row else 0

    def upsert_cache(self, product: Product) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO product_cache (product_url, title, last_price, last_status, last_checked_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(product_url) DO UPDATE SET
                    title = excluded.title,
                    last_price = excluded.last_price,
                    last_status = excluded.last_status,
                    last_checked_at = excluded.last_checked_at
                """,
                (
                    product.url,
                    product.title,
                    product.price_current,
                    product.availability_status.value,
                    product.last_checked_at.isoformat(),
                ),
            )

    def get_cached_product(self, product_url: str) -> Optional[Product]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM product_cache WHERE product_url = ?",
                (product_url,),
            ).fetchone()
        if not row:
            return None
        return Product(
            url=row["product_url"],
            title=row["title"],
            price_current=row["last_price"],
            price_old=None,
            currency="RUB",
            availability_status=AvailabilityStatus(row["last_status"]) if row["last_status"] else AvailabilityStatus.UNKNOWN,
            image_url=None,
            last_checked_at=datetime.fromisoformat(row["last_checked_at"]),
            raw_signals=None,
        )

    def _row_to_watch(self, row: sqlite3.Row) -> Watch:
        return Watch(
            id=int(row["id"]),
            user_id=int(row["user_id"]),
            product_url=row["product_url"],
            created_at=datetime.fromisoformat(row["created_at"]),
            last_status=AvailabilityStatus(row["last_status"]) if row["last_status"] else AvailabilityStatus.UNKNOWN,
            last_price=row["last_price"],
            last_notified_status=(
                AvailabilityStatus(row["last_notified_status"]) if row["last_notified_status"] else None
            ),
            is_active=bool(row["is_active"]),
        )
