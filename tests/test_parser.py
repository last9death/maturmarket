from datetime import datetime

import pytest

from maturmarket_bot.models import AvailabilityStatus


def test_parse_sitemap_urls_handles_index_and_urlset() -> None:
    pytest.importorskip("bs4")
    from maturmarket_bot.parser import parse_sitemap_urls

    xml = """
    <sitemapindex>
      <sitemap><loc>https://example.com/sitemap-products.xml</loc></sitemap>
      <sitemap><loc>https://example.com/sitemap-pages.xml</loc></sitemap>
    </sitemapindex>
    """
    urls = parse_sitemap_urls(xml)
    assert urls == [
        "https://example.com/sitemap-products.xml",
        "https://example.com/sitemap-pages.xml",
    ]


def test_parse_product_out_of_stock_keyword_wins() -> None:
    pytest.importorskip("bs4")
    from maturmarket_bot.parser import parse_product

    html = """
    <html>
      <body>
        <h1>Куртка</h1>
        <div class="price">12 990 ₽</div>
        <div>Нет в наличии</div>
        <button class="single_add_to_cart_button">Купить</button>
      </body>
    </html>
    """
    product = parse_product(html, "https://example.com/product/1", checked_at=datetime.utcnow())
    assert product.availability_status == AvailabilityStatus.OUT_OF_STOCK
