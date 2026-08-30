"""
Minimal web app: look up a card by (Scryfall set code, collector
number) and see its latest JP/EN, foil/non-foil prices as a table,
plus full price history for a chart.

Reads directly from the local DB the scraper populates -- never hits
Hareruya on a user request, only the scheduled crawl does that.

Run:
    uvicorn api.main:app --reload

Or via Docker Compose (see docker-compose.yml's `web` service):
    docker compose up web
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.orm import Session

from db import SessionLocal
from models import Price, Printing, Set
from scraper.parse import normalize_collector_number

app = FastAPI(title="JPY MTG Prices")

STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


def _find_printings(session: Session, set_code: str, collector_number: str) -> list[Printing]:
    """Looks up every local Printing matching (Scryfall set code,
    collector number).

    Returns a list rather than a single row because scryfall_set_code
    isn't guaranteed unique across local `Set` rows -- Booster Fun
    variants share their base set's code (see sync_scryfall.py), and a
    multi-set override could too in principle. In practice a given
    collector number should only exist under one of them, but we don't
    assume that; we search across all matches and let whichever one
    actually has the number win.
    """
    set_code = set_code.strip().lower()
    collector_number = normalize_collector_number(collector_number.strip())

    return list(
        session.execute(
            select(Printing).where(
                Printing.set_code == (set_code),
                Printing.collector_number == collector_number,
            )
        ).scalars().all()
    )


def _bucket_key(price: Price) -> str:
    """e.g. "jp_foil", "en_nonfoil" -- one series per (language, foil)
    combination, which is exactly what the frontend chart/table group by."""
    lang = price.language.value if hasattr(price.language, "value") else price.language
    return f"{lang}_{'foil' if price.foil else 'nonfoil'}"


@app.get("/api/prices")
def get_prices(
    set_code: str = Query(..., alias="set", description="Scryfall set code, e.g. 'hob'"),
    collector_number: str = Query(..., alias="number", description="Collector number, e.g. '119'"),
) -> dict[str, Any]:
    with SessionLocal() as session:
        printings = _find_printings(session, set_code, collector_number)
        if not printings:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"No card found for set={set_code!r} number={collector_number!r}. "
                    f"Check the set code (it's Scryfall's, e.g. 'hob' not Hareruya's "
                    f"internal cardset id), and make sure sync_all has been run."
                ),
            )

        printing_ids = [p.id for p in printings]
        all_prices = list(
            session.execute(
                select(Price)
                .where(Price.printing_id.in_(printing_ids))
                .order_by(Price.fetched_at.asc())
            ).scalars().all()
        )

        card_name = next((p.name_en for p in printings if p.name_en), None)
        rarity = next((p.rarity for p in printings if p.rarity), None)

        history: dict[str, list[dict[str, Any]]] = {}
        latest_by_bucket: dict[str, Price] = {}

        for price in all_prices:
            bucket = _bucket_key(price)
            history.setdefault(bucket, []).append(
                {"fetched_at": price.fetched_at.isoformat(), "price_yen": price.price_yen}
            )
            # all_prices is ordered ascending by fetched_at, so simply
            # overwriting as we go leaves the latest observation per
            # bucket here once the loop finishes -- no extra sort needed.
            latest_by_bucket[bucket] = price

        latest = [
            {
                "language": (p.language.value if hasattr(p.language, "value") else p.language),
                "foil": p.foil,
                "price_yen": p.price_yen,
                "stock": p.stock,
                "weekly_sales": p.weekly_sales,
                "fetched_at": p.fetched_at.isoformat(),
            }
            for p in latest_by_bucket.values()
        ]

        return {
            "card": {
                "name": card_name,
                "set_code": set_code.strip().lower(),
                "collector_number": normalize_collector_number(collector_number.strip()),
                "rarity": rarity,
            },
            "latest": latest,
            "history": history,
        }
