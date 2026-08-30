"""
Populates the `printings` table from Scryfall's bulk data export --
this is the source of truth for card identity (which cards exist, their
collector numbers, names, rarity, Scryfall id/images). Hareruya is only
ever used to update the `prices` table against printings that already
exist here; see scraper/crawl.py.

Scryfall publishes a few bulk files (https://scryfall.com/docs/api/bulk-data).
We use "default_cards" -- one row per printing, all languages, digital
and paper. We filter to English, non-digital rows: Hareruya's collector
numbers on its storefront follow the English checklist numbering
regardless of which language copy is being sold, so English is the
correct identity to key against even though we're pricing JP listings.

Run this after sync_sets.py (it needs `sets.scryfall_set_code` filled
in to know which Scryfall rows belong to which Hareruya set), and
re-run it whenever new sets are added -- otherwise there's nothing for
the price crawler to attach prices to.
"""

from __future__ import annotations

import logging
from typing import Any, Iterator

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from models import Printing, Set

logger = logging.getLogger(__name__)

BULK_DATA_INDEX_URL = "https://api.scryfall.com/bulk-data"
BULK_DATA_TYPE = "default_cards"
SETS_URL = "https://api.scryfall.com/sets"

# Be a good citizen: Scryfall explicitly asks for this in their API docs.
REQUEST_HEADERS = {
    "User-Agent": "jpy-mtg-price-tracker/0.1 (personal project)",
    "Accept": "application/json",
}


async def _get_bulk_data_download_uri(client: httpx.AsyncClient) -> str:
    resp = await client.get(BULK_DATA_INDEX_URL, headers=REQUEST_HEADERS)
    resp.raise_for_status()
    entries = resp.json()["data"]
    for entry in entries:
        if entry["type"] == BULK_DATA_TYPE:
            return entry["download_uri"]
    raise ValueError(f"No bulk-data entry of type {BULK_DATA_TYPE!r} found")


async def _fetch_all_scryfall_set_codes(client: httpx.AsyncClient) -> set[str]:
    resp = await client.get(SETS_URL, headers=REQUEST_HEADERS)
    resp.raise_for_status()
    return {entry["code"] for entry in resp.json()["data"]}


async def resolve_scryfall_set_codes(session: Session) -> None:
    """Fill in `sets.scryfall_set_code` for any Set missing it.

    Hareruya's `product` code (e.g. "HOB", "HOB-BF", "3EDBB") usually
    matches a Scryfall set code when lowercased, but not always --
    Booster Fun ("-BF"), retro-frame, and a handful of older/alternate
    products use different conventions on each side. We only accept the
    lowercase match when it's a *confirmed* real Scryfall set code;
    anything that doesn't match is left null and logged for manual
    mapping rather than silently guessed.
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        valid_codes = await _fetch_all_scryfall_set_codes(client)

    unresolved: list[Set] = []
    resolved = 0

    for set_row in session.execute(select(Set)).scalars().all():
        if set_row.scryfall_set_code or not set_row.hareruya_product_code:
            continue

        candidate = set_row.hareruya_product_code.lower()
        if candidate in valid_codes:
            set_row.scryfall_set_code = candidate
            resolved += 1
        else:
            unresolved.append(set_row)

    session.commit()
    logger.info("Resolved %d set codes automatically", resolved)
    if unresolved:
        logger.warning(
            "%d sets need manual scryfall_set_code mapping (no direct match): %s",
            len(unresolved),
            ", ".join(s.hareruya_product_code or "?" for s in unresolved[:20]),
        )


async def fetch_default_cards() -> list[dict[str, Any]]:
    """Downloads and parses the full default_cards bulk file.

    This is a large file (several hundred MB as of writing). Fine for a
    periodic batch job; don't call this per-request. If memory becomes
    an issue, switch to a streaming JSON parser (e.g. ijson) -- the
    logic below doesn't care how the dicts arrive, only that it gets an
    iterable of card objects.
    """
    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
        download_uri = await _get_bulk_data_download_uri(client)
        logger.info("Downloading Scryfall bulk data from %s", download_uri)
        resp = await client.get(download_uri, headers=REQUEST_HEADERS)
        resp.raise_for_status()
        return resp.json()


def _relevant_rows(cards: list[dict[str, Any]]) -> Iterator[dict[str, Any]]:
    """English, paper (non-digital) printings only.

    Hareruya's checklist numbering follows the English set list
    regardless of the language of the physical card being sold, so
    English is the correct identity key even though the prices we're
    attaching are for JP-market listings.
    """
    for card in cards:
        if card.get("lang") != "en":
            continue
        if card.get("digital"):
            continue
        if not card.get("collector_number"):
            continue
        yield card


def sync_printings(session: Session, cards: list[dict[str, Any]]) -> None:
    sets_by_code = {
        s.scryfall_set_code: s
        for s in session.execute(select(Set)).scalars().all()
        if s.scryfall_set_code
    }

    if not sets_by_code:
        logger.warning(
            "No sets have scryfall_set_code populated -- run "
            "resolve_scryfall_set_codes() first, or nothing will match."
        )

    existing = {
        (p.set_id, p.collector_number): p
        for p in session.execute(select(Printing)).scalars().all()
    }

    created = 0
    updated = 0
    unmatched_sets: set[str] = set()

    for card in _relevant_rows(cards):
        set_code = card["set"]
        set_row = sets_by_code.get(set_code)
        if set_row is None:
            unmatched_sets.add(set_code)
            continue

        key = (set_row.id, card["collector_number"])
        printing = existing.get(key)

        if printing is None:
            printing = Printing(
                set_id=set_row.id,
                collector_number=card["collector_number"],
                name_en=card.get("name"),
                rarity=card.get("rarity"),
                scryfall_id=card.get("id"),
            )
            session.add(printing)
            existing[key] = printing
            created += 1
        else:
            printing.name_en = card.get("name")
            printing.rarity = card.get("rarity")
            printing.scryfall_id = card.get("id")
            updated += 1

    session.commit()
    logger.info("Printings: %d created, %d updated", created, updated)
    if unmatched_sets:
        logger.info(
            "%d Scryfall set codes had no matching Hareruya set (expected -- "
            "most sets aren't sold there, e.g. promos/online-only): %s",
            len(unmatched_sets),
            ", ".join(sorted(unmatched_sets)[:20]) + ("..." if len(unmatched_sets) > 20 else ""),
        )


async def run(session: Session) -> None:
    await resolve_scryfall_set_codes(session)
    cards = await fetch_default_cards()
    sync_printings(session, cards)


if __name__ == "__main__":
    import asyncio

    from db import SessionLocal

    logging.basicConfig(level=logging.INFO)

    with SessionLocal() as session:
        asyncio.run(run(session))
