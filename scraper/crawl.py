"""
Ties the pieces together: for a given Set, page through Hareruya's
results (via HareruyaClient), parse each doc, and append Price rows.

Scryfall is the source of truth for card identity (see
scraper/sync_scryfall.py) -- this module never creates a Printing.
It only looks one up by (set, collector_number) and, if found, records
a price observation against it. Run sync_scryfall.py before this, or
every doc will fail to match and nothing will be written.

Run as a script for a manual/one-off crawl, or import `crawl_set`
into a worker for the scheduled version.
"""

from __future__ import annotations

import re
import asyncio
import datetime as dt
import logging

from sqlalchemy.orm import Session

from models import Language, Price, Printing, Set
from scraper.hareruya_client import HareruyaClient, HareruyaFilters
from scraper.parse import ParsedDoc, parse_docs
from scraper.sync_scryfall import _strip_booster_fun_suffix

logger = logging.getLogger(__name__)

_SET_CODE_RE = re.compile(r".*\[(.*)]")

def _get_printing(session: Session, set_row: Set, doc: ParsedDoc) -> Printing | None:
    """Look up the printing this price observation belongs to.

    Scryfall (via sync_scryfall.py) is the source of truth for which
    printings exist -- this function only *matches* against that, it
    never creates a Printing from Hareruya data. A miss here means
    either the printings table hasn't been synced from Scryfall yet,
    or a genuine identity mismatch (see module docstring), and either
    way the price observation is dropped rather than guessed into a
    new row.
    """
    if doc.collector_number is None:
        logger.warning(
            "Could not extract collector number for product=%s in set=%s; skipping",
            doc.hareruya_product_id, set_row.hareruya_cardset_id,
        )
        return None

    set_code = set_row.set_code

    if set_row.set_code is None:
        match = _SET_CODE_RE.match(doc.product_name)
        if match:
            set_code = _strip_booster_fun_suffix(match.group(1))
            logger.warning("Set has no Scryfall set code, parsed from card title as %s", set_code)
        else:
            logger.warning("Set has no Scryfall set code, skipping...")
            return None

    printing = (
        session.query(Printing)
        .filter_by(set_code=set_code, collector_number=doc.collector_number)
        .one_or_none()
    )
    if printing is None:
        logger.warning(
            "No matching Scryfall printing for set=%s collector_number=%s "
            "(product=%s) -- run sync_scryfall first, or this is a genuine "
            "mismatch worth checking by hand",
            set_code, doc.collector_number, doc.hareruya_product_id,
        )
    return printing


async def crawl_set(
    session: Session,
    set_row: Set,
    client: HareruyaClient,
    *,
    non_foil_only: bool = False,
) -> int:
    """Crawl every page for one set, appending Price rows for matched printings.

    Returns the number of price observations written.
    """
    filters = HareruyaFilters(
        cardset=set_row.hareruya_cardset_id,
        foil_flg=[0] if non_foil_only else None,
    )

    docs = await client.fetch_all_pages(filters)
    parsed = parse_docs(docs)

    now = dt.datetime.now(dt.timezone.utc)
    written = 0

    unmatched = 0
    for doc in parsed:
        printing = _get_printing(session, set_row, doc)
        if printing is None:
            unmatched += 1
            continue

        session.add(
            Price(
                printing_id=printing.id,
                language=Language(doc.language),
                hareruya_product_id=doc.hareruya_product_id,
                price_yen=doc.price_yen,
                stock=doc.stock,
                weekly_sales=doc.weekly_sales,
                foil=doc.foil,
                card_condition=doc.card_condition,
                fetched_at=now,
            )
        )
        written += 1

    set_row.last_crawled_at = now
    session.commit()

    logger.info(
        "Crawled set %s (%s): got %d rows, %d price rows written, %d docs unmatched",
        set_row.name_jp, set_row.hareruya_cardset_id, len(parsed), written, unmatched,
    )
    if unmatched and written == 0:
        logger.warning(
            "Every doc in this set failed to match a printing -- have you "
            "run sync_scryfall.py for this set yet?"
        )
    return written


async def crawl_sets(
    session: Session,
    sets: list[Set],
    *,
    min_interval_seconds: float = 3.0,
) -> None:
    """Crawl multiple sets sequentially through a single rate-limited client.

    Sequential + one shared client is deliberate: it guarantees the
    minimum-interval rate limit applies globally across the whole run,
    not just within a single set.
    """
    async with HareruyaClient(min_interval_seconds=min_interval_seconds) as client:
        for set_row in sets:
            try:
                await crawl_set(session, set_row, client)
            except Exception:
                logger.exception("Failed to crawl set %s", set_row.hareruya_cardset_id)
                session.rollback()


if __name__ == "__main__":
    import sys

    from db import SessionLocal  # local dev session factory, see db.py

    logging.basicConfig(level=logging.INFO)

    if len(sys.argv) < 1 or not isinstance(sys.argv[1], str):
        print("provide a set code or cardset id")
        exit(1)

    param = str(sys.argv[1])

    with SessionLocal() as session:
        if not param.isdigit():
            set_row = session.query(Set).filter_by(set_code=param).all()
        else:
            set_row = session.query(Set).filter_by(hareruya_cardset_id=int(param)).all()
        asyncio.run(crawl_sets(session, set_row))
