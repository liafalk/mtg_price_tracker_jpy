"""
Entrypoint for the daily scheduled crawl. Intended to be invoked by
cron/systemd timer/etc, once a day:

    python -m scraper.daily_run

What it does, in order:
    1. Recompute tiers (hot/warm/cold) from each set's linked Scryfall
       set's release_date.
    2. Pick today's crawl list (all hot, 1/7 of warm, 1/30 of cold).
    3. Crawl them sequentially through one rate-limited client.

Sets themselves (the `sets` table) are refreshed separately and less
often -- see sync_sets.py -- since new sets appear rarely compared to
price changes.
"""

from __future__ import annotations

import asyncio
import logging

from db import SessionLocal
from scraper.crawl import crawl_sets
from scraper.tiering import assign_tiers, sets_to_crawl_today

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def main() -> None:
    with SessionLocal() as session:
        assign_tiers(session)
        todays_sets = sets_to_crawl_today(session)

        logger.info("Crawling %d sets today", len(todays_sets))
        for s in todays_sets:
            logger.info("  - %s (%s) [%s]", s.hareruya_product_code, s.hareruya_cardset_id, s.tier)

        await crawl_sets(session, todays_sets)


if __name__ == "__main__":
    asyncio.run(main())
