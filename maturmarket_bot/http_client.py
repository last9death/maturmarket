from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Optional

import requests


DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
}


@dataclass
class HttpResponse:
    status_code: int
    text: str
    elapsed_ms: float
    url: str


class HttpClient:
    def __init__(self, timeout_seconds: float = 10.0) -> None:
        self.timeout_seconds = timeout_seconds

    def get(self, url: str, referer: Optional[str] = None) -> HttpResponse:
        headers = DEFAULT_HEADERS.copy()
        if referer:
            headers["Referer"] = referer
        start = perf_counter()
        response = requests.get(url, headers=headers, timeout=self.timeout_seconds)
        elapsed_ms = (perf_counter() - start) * 1000
        return HttpResponse(
            status_code=response.status_code,
            text=response.text,
            elapsed_ms=elapsed_ms,
            url=str(response.url),
        )
