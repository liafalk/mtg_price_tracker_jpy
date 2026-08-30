"""
Populate/refresh the `sets` table from Hareruya's own navigation JSON:

    https://www.hareruyamtg.com/user_data/list/sideMenuList.json

This is a first-party file the site's own UI uses to build its set
picker -- we fetch it directly rather than reconstructing it by
scraping the dropdown. It's a big nested tree (by era: Standard,
Pioneer, Modern, Legacy, Commander, Special Sets, ...); we flatten it
and pull out every node that carries a `query` with a `cardset=`
parameter, plus its product code and label.

Run this occasionally (e.g. weekly) to pick up newly released sets --
not on every crawl.
"""

from __future__ import annotations

import datetime as dt
import logging
import re
from typing import Any, Iterator
from urllib.parse import parse_qs, unquote

import httpx
from sqlalchemy.orm import Session

from models import Set

logger = logging.getLogger(__name__)

SIDE_MENU_URL = "https://www.hareruyamtg.com/user_data/list/sideMenuList.json"

_CARDSET_RE = re.compile(r"cardset=(\d+)")
_PRODUCT_RE = re.compile(r"product=%5B([^%]+)%5D")  # product=[XXX] url-encoded


def _iter_nodes(node: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """Depth-first walk over the nested sideMenuList tree."""
    yield node
    for child in node.get("children", []) or []:
        yield from _iter_nodes(child)


def _cardset_id_from_node(node: dict[str, Any]) -> int | None:
    # A set node either has its own top-level "query" (single-rarity sets
    # like Masterpieces) or a family of rarity-specific queries in
    # "children" (normal sets: mythic&rare / uncommon / common / ...).
    # We just need *a* cardset id for the set -- any rarity bucket works
    # since Hareruya's cardset id is one-per-set, not one-per-rarity.
    query = node.get("query")
    if query:
        m = _CARDSET_RE.search(query)
        if m:
            return int(m.group(1))

    for child in node.get("children", []) or []:
        m = _CARDSET_RE.search(child.get("query", "") or "")
        if m:
            return int(m.group(1))

    return None


def _product_code_from_node(node: dict[str, Any]) -> str | None:
    query = node.get("query", "") or ""
    m = _PRODUCT_RE.search(query)
    if m:
        return unquote(m.group(1))

    for child in node.get("children", []) or []:
        m = _PRODUCT_RE.search(child.get("query", "") or "")
        if m:
            return unquote(m.group(1))

    return None


def _parse_release_date(node: dict[str, Any]) -> dt.date | None:
    raw = node.get("release_date")
    if not raw:
        return None
    try:
        return dt.datetime.strptime(raw, "%Y/%m/%d").date()
    except ValueError:
        logger.warning("Unparseable release_date: %r", raw)
        return None


async def fetch_side_menu() -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(SIDE_MENU_URL)
        resp.raise_for_status()
        return resp.json()


def extract_set_rows(tree: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Flatten the tree into one row per distinct cardset id."""
    seen: dict[int, dict[str, Any]] = {}

    for root in tree:
        for node in _iter_nodes(root):
            # Only "leaf-ish" set nodes have an `icon` key in practice;
            # category/era nodes (Standard, Pioneer, ...) don't carry a
            # cardset id at all and are skipped naturally since
            # _cardset_id_from_node returns None for them.
            cardset_id = _cardset_id_from_node(node)
            if cardset_id is None or cardset_id in seen:
                continue

            seen[cardset_id] = {
                "hareruya_cardset_id": cardset_id,
                "hareruya_product_code": _product_code_from_node(node),
                "name_jp": node.get("label", ""),
                "release_date": _parse_release_date(node),
            }

    return list(seen.values())


def upsert_sets(session: Session, rows: list[dict[str, Any]]) -> None:
    existing = {
        s.hareruya_cardset_id: s
        for s in session.query(Set).all()
    }

    for row in rows:
        cardset_id = row["hareruya_cardset_id"]
        existing_set = existing.get(cardset_id)
        if existing_set:
            existing_set.hareruya_product_code = row["hareruya_product_code"]
            existing_set.name_jp = row["name_jp"]
            if row["release_date"]:
                existing_set.release_date = row["release_date"]
        else:
            session.add(Set(**row))

    session.commit()
    logger.info("Synced %d sets", len(rows))


async def run(session: Session) -> None:
    tree = await fetch_side_menu()
    rows = extract_set_rows(tree)
    upsert_sets(session, rows)


if __name__ == "__main__":
    import asyncio

    from db import SessionLocal

    logging.basicConfig(level=logging.INFO)

    with SessionLocal() as session:
        asyncio.run(run(session))
