from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from maturmarket_bot.config import Settings
from maturmarket_bot.http_client import HttpClient
from maturmarket_bot.models import AvailabilityStatus, Product
from maturmarket_bot.parser import parse_product, parse_search_results, parse_sitemap_urls
from maturmarket_bot.rate_limiter import SlidingWindowRateLimiter
from maturmarket_bot.storage import Storage

logger = logging.getLogger(__name__)


@dataclass
class CheckResult:
    product: Optional[Product]
    status: AvailabilityStatus
    http_status: Optional[int]
    error: Optional[str]


class ProductService:
    def __init__(self, settings: Settings, storage: Storage) -> None:
        self.settings = settings
        self.storage = storage
        self.http = HttpClient(timeout_seconds=settings.request_timeout_seconds)
        self.domain_limiter = SlidingWindowRateLimiter(settings.domain_rate_limit_per_minute, 60)
        self.user_limiters: dict[int, SlidingWindowRateLimiter] = {}

    def _get_user_limiter(self, user_id: int) -> SlidingWindowRateLimiter:
        if user_id not in self.user_limiters:
            self.user_limiters[user_id] = SlidingWindowRateLimiter(self.settings.user_rate_limit_per_hour, 3600)
        return self.user_limiters[user_id]

    def _apply_delay(self) -> None:
        delay = random.uniform(self.settings.min_delay_seconds, self.settings.max_delay_seconds)
        time.sleep(delay)

    def check_product(self, user_id: int, url: str, bypass_limits: bool = False) -> CheckResult:
        if not bypass_limits:
            user_limiter = self._get_user_limiter(user_id)
            if not user_limiter.allow():
                return CheckResult(None, AvailabilityStatus.BLOCKED, None, "USER_RATE_LIMIT")
        if not self.domain_limiter.allow():
            return CheckResult(None, AvailabilityStatus.BLOCKED, None, "DOMAIN_RATE_LIMIT")

        cached = self.storage.get_cached_product(url)
        if cached:
            age = (datetime.utcnow() - cached.last_checked_at).total_seconds()
            if age <= self.settings.cache_ttl_seconds:
                return CheckResult(cached, cached.availability_status, 200, None)

        self._apply_delay()
        try:
            response = self.http.get(url)
        except Exception as exc:  # noqa: BLE001
            logger.exception("HTTP error", extra={"url": url})
            return CheckResult(None, AvailabilityStatus.ERROR, None, str(exc))

        if response.status_code == 404:
            return CheckResult(None, AvailabilityStatus.NOT_FOUND, response.status_code, None)
        if response.status_code in {403, 429}:
            return CheckResult(None, AvailabilityStatus.BLOCKED, response.status_code, None)
        if response.status_code >= 500:
            return CheckResult(None, AvailabilityStatus.ERROR, response.status_code, None)

        product = parse_product(response.text, response.url, checked_at=datetime.utcnow())
        self.storage.upsert_cache(product)
        logger.info(
            "Parsed product",
            extra={
                "url": product.url,
                "status": product.availability_status.value,
                "price": product.price_current,
                "signals": product.raw_signals.__dict__ if product.raw_signals else None,
            },
        )
        return CheckResult(product, product.availability_status, response.status_code, None)

    def find_products(self, user_id: int, query: str, search_url: str) -> list[Product]:
        user_limiter = self._get_user_limiter(user_id)
        if not user_limiter.allow() or not self.domain_limiter.allow():
            return []

        self._apply_delay()
        response = self.http.get(search_url)
        if response.status_code != 200:
            return []

        results = parse_search_results(response.text, response.url)
        return [
            Product(
                url=result.url,
                title=result.title,
                price_current=result.price_current,
                price_old=None,
                currency="RUB",
                availability_status=result.availability_status,
                image_url=result.image_url,
                last_checked_at=datetime.utcnow(),
                raw_signals=None,
            )
            for result in results
        ]

    def scan_out_of_stock(self, user_id: int, base_url: str, limit: Optional[int] = None) -> list[Product]:
        sitemap_urls = self._collect_sitemap_urls(base_url)
        product_urls = self._filter_product_urls(sitemap_urls)
        max_products = limit or self.settings.scan_max_products
        out_of_stock: list[Product] = []
        for url in product_urls[:max_products]:
            result = self.check_product(user_id, url, bypass_limits=True)
            if result.product and result.product.availability_status == AvailabilityStatus.OUT_OF_STOCK:
                out_of_stock.append(result.product)
        return out_of_stock

    def _collect_sitemap_urls(self, base_url: str) -> list[str]:
        sitemap_candidates = [
            f"{base_url.rstrip('/')}/sitemap_index.xml",
            f"{base_url.rstrip('/')}/sitemap.xml",
        ]
        urls: list[str] = []
        for sitemap_url in sitemap_candidates:
            response = self.http.get(sitemap_url)
            if response.status_code != 200:
                continue
            urls = parse_sitemap_urls(response.text)
            if urls:
                break
        if not urls:
            return []

        sitemap_urls = [url for url in urls if url.endswith(".xml")]
        if not sitemap_urls:
            return urls

        collected: list[str] = []
        for sitemap_url in sitemap_urls:
            response = self.http.get(sitemap_url)
            if response.status_code != 200:
                continue
            collected.extend(parse_sitemap_urls(response.text))
        return collected

    def _filter_product_urls(self, urls: list[str]) -> list[str]:
        product_markers = ["/product/", "/catalog/", "/shop/"]
        filtered = []
        for url in urls:
            if any(marker in url for marker in product_markers):
                filtered.append(url)
        return filtered
