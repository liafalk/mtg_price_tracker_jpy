"""
Ties the pieces together: for a given Set, page through Hareruya's
results (via HareruyaClient), parse each doc, and upsert
Printing/Price rows.

Run as a script for a manual/one-off crawl, or import `crawl_set`
into a worker for the scheduled version.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging

from sqlalchemy.orm import Session

from models import Language, Price, Printing, Set
from scraper.hareruya_client import HareruyaClient, HareruyaFilters
from scraper.parse import ParsedDoc, parse_docs

logger = logging.getLogger(__name__)


def _get_or_create_printing(
    session: Session, set_row: Set, doc: ParsedDoc
) -> Printing | None:
    if doc.collector_number is None:
        logger.warning(
            "Could not extract collector number for product=%s in set=%s; skipping",
            doc.hareruya_product_id, set_row.hareruya_cardset_id,
        )
        return None

    printing = (
        session.query(Printing)
        .filter_by(set_id=set_row.id, collector_number=doc.collector_number)
        .one_or_none()
    )
    if printing is None:
        printing = Printing(
            set_id=set_row.id,
            collector_number=doc.collector_number,
            name_en=doc.name_en,
        )
        session.add(printing)
        session.flush()  # assign printing.id without a full commit
    elif doc.name_en and not printing.name_en:
        printing.name_en = doc.name_en

    return printing


async def crawl_set(
    session: Session,
    set_row: Set,
    client: HareruyaClient,
    *,
    non_foil_only: bool = True,
) -> int:
    """Crawl every page for one set, writing Printing/Price rows.

    Returns the number of price observations written.
    """
    filters = HareruyaFilters(
        cardset=set_row.hareruya_cardset_id,
        foil_flg=[0] if non_foil_only else None,
    )

    docs = await client.fetch_all_pages(filters)
    parsed = parse_docs(docs)

    now = dt.datetime.utcnow()
    written = 0

    for doc in parsed:
        printing = _get_or_create_printing(session, set_row, doc)
        if printing is None:
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
        "Crawled set %s (%s): %d price rows written",
        set_row.hareruya_product_code, set_row.hareruya_cardset_id, written,
    )
    return written


async def crawl_sets(
    session: Session,
    sets: list[Set],
    *,
    min_interval_seconds: float = 45.0,
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

    cardset_id = int(sys.argv[1]) if len(sys.argv) > 1 else 426  # HOB by default

    with SessionLocal() as session:
        set_row = session.query(Set).filter_by(hareruya_cardset_id=cardset_id).one()
        asyncio.run(crawl_sets(session, [set_row]))
