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
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from db import SessionLocal
from models import HareruyaSet, Price, Printing, ScryfallSet
from scraper.parse import normalize_collector_number

app = FastAPI(title="JPY MTG Prices")

STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "home.html")


@app.get("/search")
@app.get("/search/")
def search_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "search.html")


@app.get("/card/{set_code}/{collector_number}")
@app.get("/card/{set_code}/{collector_number}/")
def card_resource() -> FileResponse:
    return FileResponse(STATIC_DIR / "card.html")


def _find_printing(session: Session, set_code: str, collector_number: str) -> Printing | None:
    set_code = set_code.strip().lower()
    collector_number = normalize_collector_number(collector_number.strip())

    return session.execute(
            select(Printing).where(
                Printing.set_code == (set_code),
                Printing.collector_number == collector_number,
            )
        ).scalars().first()


def _bucket_key(price: Price) -> str:
    """e.g. "jp_foil", "en_nonfoil" -- one series per (language, foil)
    combination, which is exactly what the frontend chart/table group by."""
    lang = price.language.value if hasattr(price.language, "value") else price.language
    return f"{lang}_{'foil' if price.foil else 'nonfoil'}"


@app.get("/api/sets")
def list_set_codes() -> dict[str, list[str]]:
    with SessionLocal() as session:
        set_codes = session.execute(
            select(Printing.set_code)
            .where(Printing.set_code.is_not(None))
            .distinct()
            .order_by(Printing.set_code.asc())
        ).scalars().all()
    return {"sets": [code.lower() for code in set_codes if code]}


@app.get("/api/recent_sets")
def recent_sets(limit: int = Query(8, ge=1, le=20)) -> dict[str, list[dict[str, Any]]]:
    with SessionLocal() as session:
        rows = session.execute(
            select(ScryfallSet)
            .where(ScryfallSet.code.is_not(None))
            .order_by(ScryfallSet.release_date.desc().nullslast(), ScryfallSet.name_jp.asc())
            .limit(limit)
        ).scalars().all()

    return {
        "sets": [
            {
                "code": (row.code or "").upper(),
                "name": row.name_en or "Unknown set",
                "release_date": row.release_date.isoformat() if row.release_date else None,
            }
            for row in rows
            if (row.code)
        ]
    }


@app.get("/api/search")
def search_cards(query: str = Query(..., alias="q")) -> dict[str, Any]:
    term = query.strip()
    if not term:
        return {"results": []}

    pattern = f"%{term.lower()}%"
    with SessionLocal() as session:
        rows = session.execute(
            select(Printing)
            .where(
                or_(
                    func.lower(Printing.name_en).like(pattern),
                    func.lower(Printing.name_jp).like(pattern),
                )
            )
            .order_by(Printing.name_en.asc(), Printing.name_jp.asc())
            .limit(200)
        ).scalars().all()

        if not rows:
            return {"results": []}

        latest_prices = {}
        all_prices = session.execute(
            select(Price)
            .where(Price.printing_id.in_([row.id for row in rows]))
            .order_by(Price.printing_id.asc(), Price.fetched_at.desc())
        ).scalars().all()
        for price in all_prices:
            bucket = _bucket_key(price)
            latest_prices.setdefault(price.printing_id, {})
            latest_prices[price.printing_id].setdefault(bucket, price.price_yen)

        results = [
            {
                "id": row.id,
                "set_code": row.set_code,
                "collector_number": row.collector_number,
                "name_en": row.name_en,
                "name_jp": row.name_jp,
                "rarity": row.rarity,
                "thumb": row.img_thumb_uri or row.img_thumb_uri_jp,
                "thumb_jp": row.img_thumb_uri_jp,
                "recent_prices": latest_prices.get(row.id, {}),
                "detail_url": f"/card/{row.set_code}/{row.collector_number}",
            }
            for row in rows
        ]

    return {"results": results}


@app.get("/api/suggestions")
def suggest_card_names(
    query: str = Query(..., alias="q"),
    limit: int = Query(10, ge=1, le=25),
) -> dict[str, Any]:
    """Autocomplete helper: leading-match card names as the user types.

    Returns up to `limit` printings whose English or Japanese card name
    begins with the query (case-insensitive). Payload is intentionally small
    -- this endpoint may be hit on every keystroke -- so we return only the
    fields needed to render a dropdown and build a lookup URL. The `ilike`
    pattern is passed as a bound DB parameter (never string-built into SQL),
    which keeps this safe to run on a large table.
    """
    term = query.strip().lower()
    if not term:
        return {"results": []}

    with SessionLocal() as session:
        rows = session.execute(
            select(Printing)
            .where(
                or_(
                    Printing.name_en.ilike(term + "%"),
                    Printing.name_jp.ilike(term + "%"),
                )
            )
            .distinct()
            .order_by(Printing.name_en.asc())
            .limit(limit)
        ).scalars().all()

        results = [
            {
                "id": row.id,
                "set_code": (row.set_code or "").strip().lower(),
                "collector_number": row.collector_number,
                "name_en": row.name_en,
                "name_jp": row.name_jp or "",
                "thumb": row.img_thumb_uri or row.img_thumb_uri_jp,
                "thumb_jp": row.img_thumb_uri_jp,
                "detail_url": f"/card/{row.set_code}/{row.collector_number}",
            }
            for row in rows
        ]

    return {"results": results}

@app.get("/api/set_cards")
def get_cards_for_set(set_code: str = Query(..., alias="set")) -> dict[str, Any]:
    set_code = set_code.strip().lower()
    if not set_code:
        return {"results": []}

    with SessionLocal() as session:
        rows = session.execute(
            select(Printing)
            .where(Printing.set_code == set_code)
            .order_by(Printing.name_en.asc(), Printing.collector_number.asc())
        ).scalars().all()

        if not rows:
            return {"results": []}

        latest_prices = {}
        all_prices = session.execute(
            select(Price)
            .where(Price.printing_id.in_([row.id for row in rows]))
            .order_by(Price.printing_id.asc(), Price.fetched_at.desc())
        ).scalars().all()
        for price in all_prices:
            bucket = _bucket_key(price)
            latest_prices.setdefault(price.printing_id, {})
            latest_prices[price.printing_id].setdefault(bucket, price.price_yen)

        results = [
            {
                "id": row.id,
                "set_code": row.set_code,
                "collector_number": row.collector_number,
                "name_en": row.name_en,
                "name_jp": row.name_jp,
                "rarity": row.rarity,
                "thumb": row.img_thumb_uri or row.img_thumb_uri_jp,
                "thumb_jp": row.img_thumb_uri_jp,
                "recent_prices": latest_prices.get(row.id, {}),
                "detail_url": f"/card/{row.set_code}/{row.collector_number}",
            }
            for row in rows
        ]

    return {"results": results}


@app.get("/api/prices")
def get_prices(
    set_code: str = Query(..., alias="set", description="Scryfall set code, e.g. 'hob'"),
    collector_number: str = Query(..., alias="number", description="Collector number, e.g. '119'"),
) -> dict[str, Any]:
    with SessionLocal() as session:
        printing = _find_printing(session, set_code, collector_number)
        if not printing:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"No card found for set={set_code!r} number={collector_number!r}. "
                    f"Check the set code (it's Scryfall's, e.g. 'hob' not Hareruya's "
                    f"internal cardset id), and make sure sync_all has been run."
                ),
            )

        all_prices = list(
            session.execute(
                select(Price)
                .where(Price.printing_id == printing.id)
                .order_by(Price.fetched_at.asc())
            ).scalars().all()
        )

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
                "name_en": printing.name_en,
                "name_jp": printing.name_jp,
                "set_code": set_code.strip().lower(),
                "collector_number": normalize_collector_number(collector_number.strip()),
                "rarity": printing.rarity,
                "double_faced": printing.double_faced,
                "scryfall_id": printing.scryfall_id,
                "scryfall_id_jp": printing.scryfall_id_jp,
                "img": {
                    "grid": printing.img_grid_uri,
                    "thumb": printing.img_thumb_uri,
                    "grid_jp": printing.img_grid_uri_jp,
                    "thumb_jp": printing.img_thumb_uri_jp,
                    "back_grid": printing.img_back_grid_uri,
                    "back_thumb": printing.img_back_thumb_uri,
                    "back_grid_jp": printing.img_back_grid_uri_jp,
                    "back_thumb_jp": printing.img_back_thumb_uri_jp,
                }
            },
            "latest": latest,
            "history": history,
        }