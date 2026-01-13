from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class AvailabilityStatus(str, Enum):
    IN_STOCK = "IN_STOCK"
    OUT_OF_STOCK = "OUT_OF_STOCK"
    PREORDER = "PREORDER"
    UNKNOWN = "UNKNOWN"
    NOT_FOUND = "NOT_FOUND"
    BLOCKED = "BLOCKED"
    ERROR = "ERROR"


@dataclass
class ProductSignals:
    in_stock_hits: list[str] = field(default_factory=list)
    out_of_stock_hits: list[str] = field(default_factory=list)
    preorder_hits: list[str] = field(default_factory=list)
    buy_button_found: bool = False
    buy_button_disabled: bool = False
    selectors_used: list[str] = field(default_factory=list)


@dataclass
class Product:
    url: str
    title: str
    price_current: Optional[float]
    price_old: Optional[float]
    currency: str
    availability_status: AvailabilityStatus
    image_url: Optional[str]
    last_checked_at: datetime
    raw_signals: Optional[ProductSignals]


@dataclass
class SearchResult:
    url: str
    title: str
    price_current: Optional[float]
    availability_status: AvailabilityStatus
    image_url: Optional[str]
