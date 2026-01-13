from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from maturmarket_bot.models import AvailabilityStatus, Product, ProductSignals, SearchResult


IN_STOCK_KEYWORDS = [
    "в наличии",
    "доступно",
    "добавить в корзину",
    "купить",
]
OUT_OF_STOCK_KEYWORDS = [
    "нет в наличии",
    "распродано",
    "ожидается поступление",
]
PREORDER_KEYWORDS = [
    "предзаказ",
    "ожидается",
]

TITLE_SELECTORS = [
    "h1",
    ".product-title",
    ".product_title",
]
PRICE_SELECTORS = [
    ".price .amount",
    ".price .woocommerce-Price-amount",
    ".product-price",
    ".price",
]
OLD_PRICE_SELECTORS = [
    ".price del .amount",
    ".price del .woocommerce-Price-amount",
    ".old-price",
]
IMAGE_SELECTORS = [
    ".product-gallery img",
    ".woocommerce-product-gallery__image img",
    ".product-image img",
]
BUY_BUTTON_SELECTORS = [
    "button.add-to-cart",
    "button.single_add_to_cart_button",
    "button.buy",
    "button[data-product_id]",
]

SEARCH_ITEM_SELECTORS = [
    ".products .product",
    ".product-list .product-item",
    ".catalog-items .item",
]
SEARCH_TITLE_SELECTORS = [
    ".woocommerce-loop-product__title",
    ".product-title",
    "h2",
    "h3",
]
SEARCH_PRICE_SELECTORS = [
    ".price .amount",
    ".price",
]
SEARCH_IMAGE_SELECTORS = [
    "img",
]

SITEMAP_LOC_SELECTORS = [
    "loc",
]


@dataclass
class ParseResult:
    product: Product
    html: str


def _text_from_selectors(soup: BeautifulSoup, selectors: Iterable[str]) -> tuple[Optional[str], list[str]]:
    for selector in selectors:
        node = soup.select_one(selector)
        if node and node.get_text(strip=True):
            return node.get_text(strip=True), [selector]
    return None, []


def _extract_price(text: Optional[str]) -> Optional[float]:
    if not text:
        return None
    cleaned = (
        text.replace("\xa0", " ")
        .replace("₽", "")
        .replace("руб.", "")
        .replace("руб", "")
    )
    digits = "".join(ch for ch in cleaned if ch.isdigit() or ch in ",.")
    if not digits:
        return None
    digits = digits.replace(",", ".")
    try:
        return float(digits)
    except ValueError:
        return None


def _has_keyword(text: str, keywords: Iterable[str]) -> list[str]:
    hits = []
    lowered = text.lower()
    for keyword in keywords:
        if keyword in lowered:
            hits.append(keyword)
    return hits


def _resolve_url(base_url: str, href: Optional[str]) -> Optional[str]:
    if not href:
        return None
    return urljoin(base_url, href)


def parse_product(html: str, url: str, checked_at: Optional[datetime] = None) -> Product:
    soup = BeautifulSoup(html, "html.parser")
    signals = ProductSignals()

    title, selectors = _text_from_selectors(soup, TITLE_SELECTORS)
    signals.selectors_used.extend(selectors)
    title = title or ""

    price_text, selectors = _text_from_selectors(soup, PRICE_SELECTORS)
    signals.selectors_used.extend(selectors)
    price_current = _extract_price(price_text)

    old_price_text, selectors = _text_from_selectors(soup, OLD_PRICE_SELECTORS)
    signals.selectors_used.extend(selectors)
    price_old = _extract_price(old_price_text)

    image_url = None
    for selector in IMAGE_SELECTORS:
        node = soup.select_one(selector)
        if node and node.get("src"):
            image_url = _resolve_url(url, node.get("src"))
            signals.selectors_used.append(selector)
            break

    body_text = soup.get_text(separator=" ", strip=True)
    signals.in_stock_hits = _has_keyword(body_text, IN_STOCK_KEYWORDS)
    signals.out_of_stock_hits = _has_keyword(body_text, OUT_OF_STOCK_KEYWORDS)
    signals.preorder_hits = _has_keyword(body_text, PREORDER_KEYWORDS)

    for selector in BUY_BUTTON_SELECTORS:
        button = soup.select_one(selector)
        if button:
            signals.buy_button_found = True
            signals.selectors_used.append(selector)
            if button.has_attr("disabled") or "disabled" in button.get("class", []):
                signals.buy_button_disabled = True
            break

    availability = AvailabilityStatus.UNKNOWN
    if signals.out_of_stock_hits:
        availability = AvailabilityStatus.OUT_OF_STOCK
    elif signals.preorder_hits:
        availability = AvailabilityStatus.PREORDER
    elif signals.in_stock_hits:
        availability = AvailabilityStatus.IN_STOCK
    elif signals.buy_button_found and not signals.buy_button_disabled:
        availability = AvailabilityStatus.IN_STOCK
    elif signals.buy_button_found and signals.buy_button_disabled:
        availability = AvailabilityStatus.OUT_OF_STOCK

    return Product(
        url=url,
        title=title,
        price_current=price_current,
        price_old=price_old,
        currency="RUB",
        availability_status=availability,
        image_url=image_url,
        last_checked_at=checked_at or datetime.utcnow(),
        raw_signals=signals,
    )


def parse_search_results(html: str, base_url: str, limit: int = 10) -> list[SearchResult]:
    soup = BeautifulSoup(html, "html.parser")
    results: list[SearchResult] = []

    items = []
    for selector in SEARCH_ITEM_SELECTORS:
        items = soup.select(selector)
        if items:
            break

    for item in items:
        link = item.find("a", href=True)
        url = _resolve_url(base_url, link.get("href") if link else None) or base_url

        title = None
        for selector in SEARCH_TITLE_SELECTORS:
            node = item.select_one(selector)
            if node and node.get_text(strip=True):
                title = node.get_text(strip=True)
                break
        if not title and link:
            title = link.get_text(strip=True)
        title = title or ""

        price_text = None
        for selector in SEARCH_PRICE_SELECTORS:
            node = item.select_one(selector)
            if node and node.get_text(strip=True):
                price_text = node.get_text(strip=True)
                break
        price_current = _extract_price(price_text)

        image_url = None
        for selector in SEARCH_IMAGE_SELECTORS:
            node = item.select_one(selector)
            if node and node.get("src"):
                image_url = _resolve_url(base_url, node.get("src"))
                break

        availability = AvailabilityStatus.UNKNOWN
        body_text = item.get_text(separator=" ", strip=True)
        if _has_keyword(body_text, OUT_OF_STOCK_KEYWORDS):
            availability = AvailabilityStatus.OUT_OF_STOCK
        elif _has_keyword(body_text, IN_STOCK_KEYWORDS):
            availability = AvailabilityStatus.IN_STOCK

        results.append(
            SearchResult(
                url=url,
                title=title,
                price_current=price_current,
                availability_status=availability,
                image_url=image_url,
            )
        )
        if len(results) >= limit:
            break

    return results


def parse_sitemap_urls(xml: str) -> list[str]:
    soup = BeautifulSoup(xml, "xml")
    urls = []
    for selector in SITEMAP_LOC_SELECTORS:
        for node in soup.select(selector):
            text = node.get_text(strip=True)
            if text:
                urls.append(text)
    return urls
