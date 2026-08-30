
from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select

from db import SessionLocal
from scraper.crawl import crawl_sets

from models import Set, Tier

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def main() -> None:
    with SessionLocal() as session:
        sets = session.execute(select(Set)).scalars().all()

        filtered_sets = [s for s in sets if s.set_code is not None]

        logger.info("Crawling %d sets today", len(filtered_sets))
        for s in filtered_sets:
            logger.info("  - %s (%s) [%s]", s.name_jp, s.hareruya_cardset_id, s.set_code)

        await crawl_sets(session, filtered_sets)


if __name__ == "__main__":
    asyncio.run(main())
