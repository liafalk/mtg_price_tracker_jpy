"""
Thin, rate-limited client around Hareruya's product search endpoints.

Flow (discovered via the site's own frontend):
    1. GET /ja/products/search/unisearch/query?<human filters>
       -> returns {"message": "<fq=...&sort=...&rows=...&page=...>"}
    2. GET /ja/products/search/unisearch_api?<message from step 1>
       -> returns the actual product/price JSON

We always do both steps -- there is no evidence the `fq` query string is
stable across sessions, so we don't try to cache/replay it independently.

Rate limiting: a single asyncio-based client enforces a minimum delay
between *every* outbound request (not just per-set), and never issues
requests concurrently. This is deliberately conservative -- see the
project notes on request volume/day.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://www.hareruyamtg.com"
QUERY_PATH = "/ja/products/search/unisearch/query"
SEARCH_PATH = "/ja/products/search/unisearch_api"

# Conservative default: one request every ~45 seconds. At this rate a
# ~4,300 page full crawl takes a couple of days, which is fine -- prices
# don't move that fast. Tune per set-tier in the caller, not here.
DEFAULT_MIN_INTERVAL_SECONDS = 45.0

ROWS_PER_PAGE = 4000


@dataclass
class HareruyaFilters:
    """Human-readable filters matching the site's own query params."""

    cardset: int
    rarity: list[int] | None = None       # e.g. [3, 4] for rare+mythic
    foil_flg: list[int] | None = None     # [0] non-foil, [1] foil
    stock: int | None = None              # 1 = in-stock only, per the site's own filter
    price_from: int | None = None
    price_to: int | None = None
    page: int = 1
    sort: str = "release_date"
    order: str = "DESC"

    def to_query_params(self) -> dict[str, Any]:
        params: dict[str, Any] = {
            "sort": self.sort,
            "order": self.order,
            "cardId": "",
            "page": self.page,
            "product": "",
            "category": "",
            "cardset": self.cardset,
            "colorsType": 0,
            "cardtypesType": 0,
            "subtype": "",
            "format": "",
            "priceFrom": self.price_from or "",
            "priceTo": self.price_to or "",
            "illustrator": ""
        }
        if self.rarity:
            for i, r in enumerate(self.rarity):
                params[f"rarity[{i}]"] = r
        if self.foil_flg is not None:
            for i, f in enumerate(self.foil_flg):
                params[f"foilFlg[{i}]"] = f
        if self.stock is not None:
            params["stock"] = self.stock
        return params


@dataclass
class RateLimiter:
    """Enforces a minimum delay between requests. Not thread-safe by design
    -- use one instance per crawl process, and don't run crawls concurrently."""

    min_interval_seconds: float = DEFAULT_MIN_INTERVAL_SECONDS
    _last_request_at: float = field(default=0.0, init=False, repr=False)

    async def wait(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        remaining = self.min_interval_seconds - elapsed
        if remaining > 0:
            logger.debug("Rate limiter sleeping %.1fs", remaining)
            await asyncio.sleep(remaining)
        self._last_request_at = time.monotonic()


class HareruyaClient:
    """
    Usage:
        async with HareruyaClient() as client:
            page = await client.fetch_page(HareruyaFilters(cardset=426, page=1))
    """

    def __init__(
        self,
        min_interval_seconds: float = DEFAULT_MIN_INTERVAL_SECONDS,
        timeout: float = 20.0,
    ) -> None:
        self._rate_limiter = RateLimiter(min_interval_seconds)
        self._http = httpx.AsyncClient(
            base_url=BASE_URL,
            timeout=timeout,
            headers={
                # A plain, honest UA -- identify as a script, don't spoof a browser.
                "User-Agent": "jpy-mtg-price-tracker/0.1 (personal project; low-volume)",
            },
        )

    async def __aenter__(self) -> "HareruyaClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self._http.aclose()

    async def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        await self._rate_limiter.wait()
        resp = await self._http.get(path, params=params)
        resp.raise_for_status()
        return resp.json()

    async def _resolve_query_string(self, filters: HareruyaFilters) -> str:
        """Step 1: turn human filters into the Solr-style query string."""
        data = await self._get(QUERY_PATH, filters.to_query_params())
        message = data.get("message")
        if not message:
            raise ValueError(f"Unexpected /query response: {data!r}")
        return message

    async def fetch_page(self, filters: HareruyaFilters) -> dict[str, Any]:
        """
        Full two-step fetch for one page of results.

        Returns the raw unisearch_api JSON: {"response": {"numFound": N, "docs": [...]}}
        """
        query_string = await self._resolve_query_string(filters)
        # The resolved string is already URL-encoded (fq=...&sort=...&rows=...&page=N);
        # pass it through as the raw query rather than re-encoding it.
        await self._rate_limiter.wait()
        # change number of rows
        query_string= query_string.replace("rows=60", f"rows={ROWS_PER_PAGE}")
        resp = await self._http.get(f"{SEARCH_PATH}?{query_string}")
        resp.raise_for_status()
        return resp.json()

    async def fetch_all_pages(self, filters: HareruyaFilters) -> list[dict[str, Any]]:
        """Page through an entire set's results, respecting rate limits throughout."""
        all_docs: list[dict[str, Any]] = []
        page = filters.page
        while True:
            filters.page = page
            data = await self.fetch_page(filters)
            response = data.get("response", {})
            docs = response.get("docs", [])
            all_docs.extend(docs)

            num_found = response.get("numFound", 0)
            logger.info(
                "cardset=%s page=%s docs=%d/%d",
                filters.cardset, page, len(all_docs), num_found,
            )

            if len(all_docs) >= num_found or not docs:
                break
            page += 1

        return all_docs
