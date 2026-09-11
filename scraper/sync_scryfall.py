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

As of Scryfall's July 2026 API change, bulk files are served as
gzip-compressed JSONL (one JSON object per line) via a
`jsonl_download_uri` field; the older single-JSON-array `download_uri`
was retired. `_parse_bulk_body` below handles either shape (gzipped or
not, JSONL or a single array) so this keeps working if the format
shifts again -- see its docstring.

Manual set-code overrides (for sets that don't auto-resolve) live in
config/set_code_overrides.toml -- see load_set_code_overrides below.

Run this after sync_sets.py (it needs `sets.set_code` filled
in to know which Scryfall rows belong to which Hareruya set), and
re-run it whenever new sets are added -- otherwise there's nothing for
the price crawler to attach prices to.
"""

from __future__ import annotations

import argparse
import datetime as dt
from enum import StrEnum
import gzip
import json
import logging
import tempfile
import tomllib
from pathlib import Path
from typing import Any, Iterator

import httpx
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from tqdm import tqdm

from models import Printing, ScryfallSet, HareruyaSet

logger = logging.getLogger(__name__)

BULK_DATA_INDEX_URL = "https://api.scryfall.com/bulk-data"
SETS_URL = "https://api.scryfall.com/sets"
MTGJSON_SET_LIST_URL = "https://mtgjson.com/api/v5/SetList.json"
MAINFEST_URL = "https://api.scryfall.com/cards/manifest"

DEFAULT_OVERRIDES_PATH = Path(__file__).resolve().parent.parent / "config" / "set_code_overrides.toml"
DEFAULT_NAME_JP_OVERRIDES_PATH = Path(__file__).resolve().parent.parent / "config" / "set_name_jp_overrides.toml"

class BulkDataType(StrEnum):
    DEFAULT = "default_cards"
    ALL = "all_cards"

# Be a good citizen: Scryfall explicitly asks for this in their API docs.
REQUEST_HEADERS = {
    "User-Agent": "jpy-mtg-price-tracker/0.1 (personal project)",
    "Accept": "application/json",
}

async def _get_bulk_data_download_uri(client: httpx.AsyncClient, type: BulkDataType) -> str:
    resp = await client.get(BULK_DATA_INDEX_URL, headers=REQUEST_HEADERS)
    resp.raise_for_status()
    entries: list[dict[str, Any]] = resp.json()["data"]
    for entry in entries:
        if entry["type"] == type:
            # jsonl_download_uri is current as of the July 2026 format
            # change; download_uri is the retired pre-change field, kept
            # here only as a fallback in case a cached/older index is
            # ever served.
            uri = entry.get("jsonl_download_uri") or entry.get("download_uri")
            if not uri:
                raise ValueError(
                    f"bulk-data entry for {type!r} has neither "
                    f"jsonl_download_uri nor download_uri: {entry!r}"
                )
            return uri
    raise ValueError(f"No bulk-data entry of type {type!r} found")


_BOOSTER_FUN_SUFFIX = "-BF"


def _strip_booster_fun_suffix(hareruya_product_code: str) -> str:
    if hareruya_product_code.upper().endswith(_BOOSTER_FUN_SUFFIX):
        return hareruya_product_code[: -len(_BOOSTER_FUN_SUFFIX)]
    return hareruya_product_code


def _is_booster_fun_set(set_row: HareruyaSet) -> bool:
    return bool(
        set_row.hareruya_product_code
        and set_row.hareruya_product_code.upper().endswith(_BOOSTER_FUN_SUFFIX)
    )


async def _fetch_all_scryfall_set_codes(client: httpx.AsyncClient) -> set[str]:
    resp = await client.get(SETS_URL, headers=REQUEST_HEADERS)
    resp.raise_for_status()
    return {entry["code"] for entry in resp.json()["data"]}


async def fetch_scryfall_sets() -> list[dict[str, Any]]:
    """Fetch the canonical set metadata from Scryfall."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(SETS_URL, headers=REQUEST_HEADERS)
        resp.raise_for_status()

    rows: list[dict[str, Any]] = []
    for entry in resp.json()["data"]:
        release_date = entry.get("released_at")
        rows.append(
            {
                "code": entry["code"],
                "name_en": entry["name"],
                "release_date": (
                    dt.date.fromisoformat(release_date) if release_date else None
                ),
                "parent_set_code": entry.get("parent_set_code"),
                "set_type": entry["set_type"]
            }
        )
    return rows


async def fetch_mtgjson_japanese_names() -> dict[str, str]:
    """Fetch Japanese set-name translations keyed by set code."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(MTGJSON_SET_LIST_URL, headers=REQUEST_HEADERS)
        resp.raise_for_status()

    entries = resp.json().get("data", [])
    return {
        entry["code"].lower(): translations["Japanese"]
        for entry in entries
        if entry.get("code")
        and (translations := entry.get("translations", {})).get("Japanese")
    }


def upsert_scryfall_sets(session: Session, rows: list[dict[str, Any]]) -> None:
    """Insert or refresh canonical Scryfall set metadata."""
    existing = {
        set_row.code: set_row
        for set_row in session.execute(select(ScryfallSet)).scalars().all()
    }
    created = 0
    updated = 0

    for row in rows:
        set_row = existing.get(row["code"])
        if set_row is None:
            session.add(ScryfallSet(**row))
            created += 1
            continue

        set_row.name_en = row["name_en"]
        if row.get("name_jp"):
            set_row.name_jp = row["name_jp"]
        set_row.set_type = row["set_type"]
        set_row.parent_set_code = row["parent_set_code"]

        updated += 1

    session.commit()
    logger.info("Scryfall sets: %d created, %d updated", created, updated)


def fill_missing_japanese_set_names(session: Session) -> None:
    """Use Hareruya labels as a fallback for missing Japanese names."""
    scryfall_sets = {
        set_row.code: set_row
        for set_row in session.execute(select(ScryfallSet)).scalars().all()
    }
    updated = 0
    for set_row in session.execute(select(HareruyaSet)).scalars().all():
        if not set_row.set_code:
            continue
        canonical = scryfall_sets.get(set_row.set_code)
        if canonical and not canonical.name_jp and set_row.name_jp:
            canonical.name_jp = set_row.name_jp
            updated += 1

    session.commit()
    logger.info("Hareruya fallback Japanese set names: %d updated", updated)


async def sync_scryfall_sets(
    session: Session, name_jp_overrides_path: Path | None = None
) -> None:
    """Refresh canonical sets and their Japanese names.

    Japanese names come from MTGJSON, with manual overrides from
    config/set_name_jp_overrides.toml taking precedence.
    """
    japanese_names = await fetch_mtgjson_japanese_names()
    overrides = load_set_name_jp_overrides(name_jp_overrides_path)
    if overrides:
        logger.info("Loaded %d manual Japanese name overrides", len(overrides))
    rows = await fetch_scryfall_sets()
    for row in rows:
        code = row["code"].lower()
        row["name_jp"] = overrides.get(code) or japanese_names.get(code)
    upsert_scryfall_sets(session, rows)


def load_set_code_overrides(path: Path | None = None) -> dict[int, str]:
    """Loads manual hareruya_product_code -> scryfall_set_code overrides
    from a TOML config file (default: config/set_code_overrides.toml).

    Returns {} if the file doesn't exist -- overrides are optional,
    most sets resolve automatically. Every value must be a string;
    anything else raises immediately rather than silently no-op'ing on
    a malformed entry (e.g. an accidentally-unquoted TOML value).
    """
    path = path or DEFAULT_OVERRIDES_PATH
    if not path.exists():
        return {}

    with path.open("rb") as f:
        data = tomllib.load(f)

    for key, value in data.items():
        if not isinstance(value, str):
            raise ValueError(
                f"{path}: value for {key!r} must be a str, "
                f"got {type(value).__name__}: {value!r}"
            )
        if not value:
            # Commented-out template entries in the shipped config use
            # empty strings as placeholders -- skip rather than apply.
            continue

    return {int(k): v for k, v in data.items() if v}


def load_set_name_jp_overrides(path: Path | None = None) -> dict[str, str]:
    """Loads manual scryfall_set_code -> Japanese name overrides from a
    TOML config file (default: config/set_name_jp_overrides.toml).

    Returns {} if the file doesn't exist -- overrides are optional,
    most sets get their Japanese name from MTGJSON. Every value must be
    a string; anything else raises immediately rather than silently
    no-op'ing on a malformed entry.
    """
    path = path or DEFAULT_NAME_JP_OVERRIDES_PATH
    if not path.exists():
        return {}

    with path.open("rb") as f:
        data = tomllib.load(f)

    for key, value in data.items():
        if not isinstance(value, str):
            raise ValueError(
                f"{path}: value for {key!r} must be a str, "
                f"got {type(value).__name__}: {value!r}"
            )
        if not value:
            # Commented-out template entries in the shipped config use
            # empty strings as placeholders -- skip rather than apply.
            continue

    return {str(k).lower(): v for k, v in data.items() if v}


async def resolve_scryfall_set_codes(
    session: Session, overrides_path: Path | None = None
) -> None:
    """Fill in `sets.set_code` for every Set.

    Resolution order:
      1. Manual override from config/set_code_overrides.toml, if the
         set's hareruya_product_code has an entry there. This always
         wins, including overwriting an already-resolved value -- it's
         also how you fix a bad automatic match, not just fill gaps.
      2. Automatic: lowercase Hareruya's `product` code (e.g. "HOB"),
         accept it only if it's a *confirmed* real Scryfall set code.

    Booster Fun variants ("HOB-BF") are a special case, not a mapping
    gap: Scryfall doesn't mint separate set codes for showcase/
    extended-art/borderless treatments -- they're catalogued inside the
    *base* set (confirmed by Scryfall's own `is:boosterfun` search
    filter, e.g. `set:eld is:boosterfun` returns Eldraine cards, not
    cards in some other set). So a "-BF" Hareruya product code
    resolves to the same scryfall_set_code as its base set (after
    stripping the suffix, before step 2 above), and two local `Set`
    rows end up sharing one Scryfall code. sync_printings below
    disambiguates between them using each card's promo_types.

    Anything that doesn't resolve via either step is left null and
    logged for manual mapping -- add it to the overrides file.
    """
    overrides = load_set_code_overrides(overrides_path)

    logger.info("Loaded %d manual overrides", len(overrides))

    async with httpx.AsyncClient(timeout=30.0) as client:
        valid_codes = await _fetch_all_scryfall_set_codes(client)

    unresolved: list[HareruyaSet] = []
    resolved = 0
    overridden = 0

    for set_row in session.execute(select(HareruyaSet)).scalars().all():
        override = overrides.get(set_row.hareruya_cardset_id)
        if override:
            if override not in valid_codes:
                logger.warning(
                    "Override %s -> %r is not a recognized Scryfall set code "
                    "-- applying it anyway, but double-check it",
                    set_row.hareruya_product_code, override,
                )
            set_row.set_code = override
            overridden += 1
            continue

        if set_row.set_code:
            continue  # already resolved (automatically) in a previous run

        if set_row.hareruya_product_code is not None:
            base_code = _strip_booster_fun_suffix(set_row.hareruya_product_code)
            candidate = base_code.lower()
            if candidate in valid_codes:
                set_row.set_code = candidate
                resolved += 1
                continue

        unresolved.append(set_row)

    session.commit()
    logger.info(
        "Resolved %d set codes automatically, %d from manual overrides",
        resolved, overridden,
    )
    if unresolved:
        used_path = overrides_path or DEFAULT_OVERRIDES_PATH
        logger.warning(
            "%d sets still need manual scryfall_set_code mapping -- add "
            "them to %s: %s",
            len(unresolved),
            used_path,
            ", ".join(str(s.hareruya_cardset_id) for s in unresolved),
        )


def _parse_bulk_body(raw: bytes) -> list[dict[str, Any]]:
    """Parses a bulk-data payload into a temporary JSONL cache.

    We intentionally keep this helper for compatibility with older call
    sites and tests, but the hot path in the application now writes the
    large payload to disk instead of keeping the full decoded list in
    memory.
    """
    try:
        text = gzip.decompress(raw).decode("utf-8")
    except OSError:
        text = raw.decode("utf-8")

    stripped = text.lstrip()
    if stripped.startswith("["):
        return json.loads(text)

    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _write_bulk_data_to_temp_file(raw: bytes, temp_path: Path) -> int:
    """Write large bulk-data payload to a temp JSONL file and return row count."""
    try:
        text = gzip.decompress(raw).decode("utf-8")
    except OSError:
        text = raw.decode("utf-8")

    count = 0
    with temp_path.open("w", encoding="utf-8") as handle:
        stripped = text.lstrip()
        if stripped.startswith("["):
            rows = json.loads(text)
            for row in rows:
                handle.write(json.dumps(row, separators=(",", ":")))
                handle.write("\n")
                count += 1
            return count

        for line in text.splitlines():
            if not line.strip():
                continue
            handle.write(line)
            handle.write("\n")
            count += 1

    return count


def _write_bulk_data_from_path(raw_path: Path, temp_path: Path) -> int:
    """Convert a downloaded bulk payload on disk to a JSONL temp file."""
    with raw_path.open("rb") as source_file:
        first_chunk = source_file.read(2)
        source_file.seek(0)

        if first_chunk == b"\x1f\x8b":
            with gzip.open(raw_path, "rb") as source:
                text = source.read().decode("utf-8")
        else:
            text = source_file.read().decode("utf-8")

    count = 0
    with temp_path.open("w", encoding="utf-8") as handle:
        stripped = text.lstrip()
        if stripped.startswith("["):
            rows = json.loads(text)
            for row in rows:
                handle.write(json.dumps(row, separators=(",", ":")))
                handle.write("\n")
                count += 1
            return count

        for line in text.splitlines():
            if not line.strip():
                continue
            handle.write(line)
            handle.write("\n")
            count += 1

    return count


def _iter_cards_from_path(path: Path) -> Iterator[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            yield json.loads(line)


def _iter_relevant_cards(cards: Path | list[dict[str, Any]]) -> Iterator[dict[str, Any]]:
    if isinstance(cards, Path):
        iterable = _iter_cards_from_path(cards)
    else:
        iterable = cards

    for card in iterable:
        if card.get("digital"):
            continue
        if not card.get("collector_number"):
            continue
        yield card


async def fetch_default_cards(type: BulkDataType) -> Path:
    """Downloads the bulk file and spools it to a temporary JSONL cache.

    The full Scryfall export is large enough to blow up memory if you keep
    it as a Python list. Returning a path lets the caller stream rows one
    by one while still preserving the same logical data flow.
    """
    async with httpx.AsyncClient(timeout=300.0, follow_redirects=True) as client:
        download_uri = await _get_bulk_data_download_uri(client, type)
        logger.info("Downloading Scryfall default bulk data from %s", download_uri)

        with tempfile.NamedTemporaryFile(
            mode="wb",
            delete=False,
            suffix=".bin",
            prefix=f"{type.value}_",
        ) as temp_file:
            temp_path = Path(temp_file.name)

        async with client.stream("GET", download_uri, headers=REQUEST_HEADERS) as resp:
            resp.raise_for_status()
            total = int(resp.headers.get("Content-Length") or 0)
            with temp_path.open("wb") as handle:
                with tqdm(
                    total=total,
                    unit="B",
                    unit_scale=True,
                    unit_divisor=1024,
                    desc=f"download {type.value}",
                    leave=True,
                ) as progress:
                    async for chunk in resp.aiter_bytes(chunk_size=1024 * 1024):
                        if not chunk:
                            continue
                        handle.write(chunk)
                        progress.update(len(chunk))

        jsonl_path = temp_path.with_suffix(".jsonl")
        row_count = _write_bulk_data_from_path(temp_path, jsonl_path)
        logger.info("Wrote %d cards to temporary bulk cache %s", row_count, jsonl_path)
        temp_path.unlink(missing_ok=True)
        return jsonl_path


def _relevant_rows(cards: list[dict[str, Any]]) -> Iterator[dict[str, Any]]:
    """English, paper (non-digital) printings only.

    Hareruya's checklist numbering follows the English set list
    regardless of the language of the physical card being sold, so
    English is the correct identity key even though the prices we're
    attaching are for JP-market listings.
    """
    for card in cards:
        if card.get("digital"):
            continue
        if not card.get("collector_number"):
            continue
        yield card

def _build_set_resolver(
    session: Session,
) -> tuple[dict[str, HareruyaSet], dict[str, HareruyaSet]]:
    """Groups local Set rows by shared scryfall_set_code, splitting
    each group into its "primary" (normal-frame) and "booster fun"
    entry where both exist.

    Returns (primary_by_code, booster_fun_by_code) -- either dict may
    be missing a given code if that variant isn't tracked locally.
    """
    primary_by_code: dict[str, HareruyaSet] = {}
    booster_fun_by_code: dict[str, HareruyaSet] = {}

    for set_row in session.execute(select(HareruyaSet)).scalars().all():
        if not set_row.set_code:
            continue
        if _is_booster_fun_set(set_row):
            booster_fun_by_code[set_row.set_code] = set_row
        else:
            primary_by_code[set_row.set_code] = set_row

    return primary_by_code, booster_fun_by_code

def sync_printings(session: Session, cards: Path | list[dict[str, Any]]) -> None:
    primary_by_code, booster_fun_by_code = _build_set_resolver(session)

    if not primary_by_code and not booster_fun_by_code:
        logger.warning(
            "No sets have scryfall_set_code populated -- run "
            "resolve_scryfall_set_codes() first, or nothing will match."
        )

    existing = {
        (p.set_code, p.collector_number): p
        for p in session.execute(select(Printing)).scalars().all()
    }

    total = sum(1 for _ in _iter_relevant_cards(cards)) if isinstance(cards, Path) else len(cards)
    created = 0
    updated = 0

    iterable = _iter_relevant_cards(cards)
    for card in tqdm(iterable, total=total, desc="sync_printings"):
        key = (card["set"], card["collector_number"])

        double_faced = card["layout"] in ("transform", "modal_dfc", "double_faced_token")
        if printed_name := card.get("printed_name"):
            name_en = printed_name
        elif not double_faced and (faces := card.get("card_faces")):
            name_en = faces[0].get("printed_name", faces[0].get("name", card["name"]))
        else:
            name_en = card["name"]

        img_grid_uri = None
        img_thumb_uri = None
        img_back_grid_uri = None
        img_back_thumb_uri = None

        if double_faced and (faces := card.get("card_faces")):
            img_grid_uri = faces[0].get("image_uris", {}).get("grid")
            img_thumb_uri = faces[0].get("image_uris", {}).get("thumb")
            if double_faced:
                img_back_grid_uri = faces[1].get("image_uris", {}).get("grid")
                img_back_thumb_uri = faces[1].get("image_uris", {}).get("thumb")
        else:
            img_grid_uri = card.get("image_uris", {}).get("grid")
            img_thumb_uri = card.get("image_uris", {}).get("thumb")

        printing = existing.get(key)

        if printing is None:
            printing = Printing(
                set_code=card["set"],
                collector_number=card["collector_number"],
                name_en=name_en,
                scryfall_id=card["id"],
                rarity=card.get("rarity"),
                double_faced=double_faced
            )
            printing.img_grid_uri = img_grid_uri
            printing.img_thumb_uri = img_thumb_uri
            printing.img_back_grid_uri = img_back_grid_uri
            printing.img_back_thumb_uri = img_back_thumb_uri

            session.add(printing)
            existing[key] = printing
            created += 1
        else:
            printing.name_en = name_en
            printing.rarity = card.get("rarity")
            printing.scryfall_id = card["id"]
            printing.double_faced = double_faced
            printing.img_grid_uri = img_grid_uri
            printing.img_thumb_uri = img_thumb_uri
            printing.img_back_grid_uri = img_back_grid_uri
            printing.img_back_thumb_uri = img_back_thumb_uri
            updated += 1

    session.commit()
    logger.info("Printings: %d created, %d updated", created, updated)


async def update_japanese_data(session: Session):
    cards_path = await fetch_default_cards(BulkDataType.ALL)

    total = sum(1 for _ in _iter_cards_from_path(cards_path)) if cards_path is not None else 0
    try:
        for card in tqdm(_iter_cards_from_path(cards_path), total=total, desc="update_japanese_data"):
            if card["lang"] != "ja":
                continue
            matches = session.execute(
                select(Printing)
                .where(
                    Printing.set_code == card["set"],
                    Printing.collector_number == card["collector_number"]
                )
            ).scalars().all()

            if len(matches) > 1:
                logger.warning("Found %d matches for %s %s, skipping...",
                               len(matches), card["set"], card["collector_number"])

            if not matches:
                continue
            double_faced = matches[0].double_faced

            name_jp = ""
            if name := card.get("printed_name"):
                name_jp = name
            elif faces := card.get("card_faces"):
                if double_faced:
                    name_jp = " // ".join(face.get("printed_name", "") for face in faces)
                else:
                    name_jp = faces[0].get("printed_name", "")
            else:
                logger.warning("No printed_name or card_faces for %s %s, defaulting to english name", card["set"], card["collector_number"])
                name_jp = card.get("name")

            img_grid_uri = None
            img_thumb_uri = None
            img_back_grid_uri = None
            img_back_thumb_uri = None

            if double_faced and (faces := card.get("card_faces")):
                img_grid_uri = faces[0].get("image_uris", {}).get("grid")
                img_thumb_uri = faces[0].get("image_uris", {}).get("thumb")
                if double_faced:
                    img_back_grid_uri = faces[1].get("image_uris", {}).get("grid")
                    img_back_thumb_uri = faces[1].get("image_uris", {}).get("thumb")
            else:
                img_grid_uri = card.get("image_uris", {}).get("grid")
                img_thumb_uri = card.get("image_uris", {}).get("thumb")

            session.execute(
                update(Printing)
                .where(
                    Printing.id == matches[0].id
                ).values(
                    scryfall_id_jp=card["id"],
                    name_jp=name_jp,
                    img_grid_uri_jp=img_grid_uri,
                    img_thumb_uri_jp=img_thumb_uri,
                    img_back_grid_uri_jp=img_back_grid_uri,
                    img_back_thumb_uri_jp=img_back_thumb_uri
                )
            )

        session.commit()
    finally:
        if cards_path is not None:
            cards_path.unlink(missing_ok=True)


async def run(session: Session) -> None:
    await sync_scryfall_sets(session)
    await resolve_scryfall_set_codes(session)
    fill_missing_japanese_set_names(session)
    cards_path = await fetch_default_cards(BulkDataType.DEFAULT)
    try:
        sync_printings(session, cards_path)
        await update_japanese_data(session)
    finally:
        if cards_path is not None:
            cards_path.unlink(missing_ok=True)


if __name__ == "__main__":
    import asyncio

    from db import SessionLocal
    
    parser = argparse.ArgumentParser(
        description="Sync local printing data from Scryfall bulk data."
    )
    parser.add_argument(
        "--overrides",
        type=Path,
        default=DEFAULT_OVERRIDES_PATH,
        help="Path to the TOML file containing manual set-code overrides.",
    )
    parser.add_argument(
        "--name-jp-overrides",
        type=Path,
        default=DEFAULT_NAME_JP_OVERRIDES_PATH,
        help="Path to the TOML file containing manual Japanese set-name overrides.",
    )

    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser(
        "run",
        help="Run the full sync pipeline (this is the default behavior).",
    )
    subparsers.add_parser(
        "sets",
        help="Sync Scryfall sets and resolve Hareruya set codes.",
    )
    subparsers.add_parser(
        "sync_jp",
        help="Sync Japanese card data from Scryfall.",
    )
    subparsers.add_parser(
        "sync_en",
        help="Sync English card data from Scryfall (default_cards bulk data).",
    )

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)

    with SessionLocal() as session:
        match args.command:
            case "sets":
                asyncio.run(
                    sync_scryfall_sets(
                        session, name_jp_overrides_path=args.name_jp_overrides
                    )
                )
                asyncio.run(resolve_scryfall_set_codes(session, overrides_path=args.overrides))
                fill_missing_japanese_set_names(session)
            case "sync_en":
                cards_path = asyncio.run(fetch_default_cards(BulkDataType.DEFAULT))
                try:
                    sync_printings(session, cards_path)
                finally:
                    if cards_path is not None:
                        cards_path.unlink(missing_ok=True)
            case "sync_jp":
                asyncio.run(update_japanese_data(session))
            case "run" | None:
                asyncio.run(run(session))
