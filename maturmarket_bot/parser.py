from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from html.parser import HTMLParser
from typing import Iterable, Optional
from urllib.parse import urljoin
from xml.etree import ElementTree

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


@dataclass
class HtmlNode:
    tag: str
    attrs: dict[str, str]
    children: list["HtmlNode"]
    text_parts: list[str]

    def text(self, separator: str = " ", strip: bool = True) -> str:
        chunks: list[str] = []
        if self.text_parts:
            chunks.append(" ".join(self.text_parts))
        for child in self.children:
            child_text = child.text(separator=separator, strip=strip)
            if child_text:
                chunks.append(child_text)
        combined = separator.join(chunk for chunk in chunks if chunk)
        return combined.strip() if strip else combined


class MiniHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.root = HtmlNode(tag="document", attrs={}, children=[], text_parts=[])
        self.stack = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        attr_map = {key: value or "" for key, value in attrs}
        node = HtmlNode(tag=tag, attrs=attr_map, children=[], text_parts=[])
        self.stack[-1].children.append(node)
        self.stack.append(node)

    def handle_endtag(self, tag: str) -> None:
        if len(self.stack) > 1:
            self.stack.pop()

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.stack[-1].text_parts.append(data.strip())


def _parse_html(html: str) -> HtmlNode:
    parser = MiniHTMLParser()
    parser.feed(html)
    return parser.root


def _match_simple_selector(node: HtmlNode, selector: str) -> bool:
    if selector.startswith("."):
        class_name = selector[1:]
        classes = node.attrs.get("class", "").split()
        return class_name in classes
    if "." in selector:
        tag, class_name = selector.split(".", 1)
        if node.tag != tag:
            return False
        classes = node.attrs.get("class", "").split()
        return class_name in classes
    return node.tag == selector


def _select_all(root: HtmlNode, selector: str) -> list[HtmlNode]:
    parts = selector.split()

    def recurse(nodes: list[HtmlNode], part_index: int) -> list[HtmlNode]:
        if part_index >= len(parts):
            return nodes
        part = parts[part_index]
        matched: list[HtmlNode] = []
        for node in nodes:
            for child in node.children:
                if _match_simple_selector(child, part):
                    matched.append(child)
                matched.extend(recurse([child], part_index))
        if part_index == len(parts) - 1:
            return matched
        return recurse(matched, part_index + 1)

    return recurse([root], 0)


def _select_one(root: HtmlNode, selector: str) -> Optional[HtmlNode]:
    matches = _select_all(root, selector)
    return matches[0] if matches else None


def _text_from_selectors(root: HtmlNode, selectors: Iterable[str]) -> tuple[Optional[str], list[str]]:
    for selector in selectors:
        node = _select_one(root, selector)
        if node:
            text = node.text(strip=True)
            if text:
                return text, [selector]
=======
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

    root = _parse_html(html)
    signals = ProductSignals()

    title, selectors = _text_from_selectors(root, TITLE_SELECTORS)
    signals.selectors_used.extend(selectors)
    title = title or ""

    price_text, selectors = _text_from_selectors(root, PRICE_SELECTORS)
    signals.selectors_used.extend(selectors)
    price_current = _extract_price(price_text)

    old_price_text, selectors = _text_from_selectors(root, OLD_PRICE_SELECTORS)

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

        node = _select_one(root, selector)
        if node and node.attrs.get("src"):
            image_url = _resolve_url(url, node.attrs.get("src"))
            signals.selectors_used.append(selector)
            break

    body_text = root.text(separator=" ", strip=True)

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

        button = _select_one(root, selector)
        if button:
            signals.buy_button_found = True
            signals.selectors_used.append(selector)
            classes = button.attrs.get("class", "").split()
            if "disabled" in button.attrs or "disabled" in classes:

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
    root = _parse_html(html)
    results: list[SearchResult] = []

    items: list[HtmlNode] = []
    for selector in SEARCH_ITEM_SELECTORS:
        items = _select_all(root, selector)
        if items:
            break

    for item in items:
        link = _select_one(item, "a")
        url = _resolve_url(base_url, link.attrs.get("href") if link else None) or base_url

        title = None
        for selector in SEARCH_TITLE_SELECTORS:
            node = _select_one(item, selector)
            if node:
                text = node.text(strip=True)
                if text:
                    title = text
                    break
        if not title and link:
            title = link.text(strip=True)
        title = title or ""

        price_text = None
        for selector in SEARCH_PRICE_SELECTORS:
            node = _select_one(item, selector)
            if node:
                text = node.text(strip=True)
                if text:
                    price_text = text
                    break
        price_current = _extract_price(price_text)

        image_url = None
        for selector in SEARCH_IMAGE_SELECTORS:
            node = _select_one(item, selector)
            if node and node.attrs.get("src"):
                image_url = _resolve_url(base_url, node.attrs.get("src"))
                break

        availability = AvailabilityStatus.UNKNOWN
        body_text = item.text(separator=" ", strip=True)
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
    urls: list[str] = []
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError:
        return urls
    for loc in root.iter():
        if loc.tag.endswith("loc") and loc.text:
            urls.append(loc.text.strip())
    return urls
