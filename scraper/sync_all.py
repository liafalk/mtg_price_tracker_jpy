"""
Runs the full identity-sync pipeline in one command:

    1. sync_sets   -- Hareruya's sideMenuList.json -> sets table
    2. sync_scryfall -- resolve Scryfall set codes, then populate
                         printings from Scryfall's bulk data

This is the "just get me set up" entrypoint. Run it once initially,
and again whenever new sets are released (weekly is plenty -- there's
no need to run this daily; only scraper/daily_run.py needs to run
that often, for prices).

    python -m scraper.sync_all
"""

from __future__ import annotations

import asyncio
import logging

from db import SessionLocal
from scraper import sync_scryfall, sync_sets

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def main() -> None:
    with SessionLocal() as session:
        logger.info("Syncing sets from Hareruya...")
        await sync_sets.run(session)

        logger.info("Syncing printings from Scryfall...")
        await sync_scryfall.run(session)

    logger.info("Done. Ready to crawl prices with scraper.daily_run or scraper.crawl.")


if __name__ == "__main__":
    asyncio.run(main())
