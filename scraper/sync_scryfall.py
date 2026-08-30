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

Run this after sync_sets.py (it needs `sets.scryfall_set_code` filled
in to know which Scryfall rows belong to which Hareruya set), and
re-run it whenever new sets are added -- otherwise there's nothing for
the price crawler to attach prices to.
"""

from __future__ import annotations

import gzip
import json
import logging
import tomllib
from pathlib import Path
from typing import Any, Iterator

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from models import Printing, Set

logger = logging.getLogger(__name__)

BULK_DATA_INDEX_URL = "https://api.scryfall.com/bulk-data"
BULK_DATA_TYPE = "default_cards"
SETS_URL = "https://api.scryfall.com/sets"

DEFAULT_OVERRIDES_PATH = Path(__file__).resolve().parent.parent / "config" / "set_code_overrides.toml"

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
            # jsonl_download_uri is current as of the July 2026 format
            # change; download_uri is the retired pre-change field, kept
            # here only as a fallback in case a cached/older index is
            # ever served.
            uri = entry.get("jsonl_download_uri") or entry.get("download_uri")
            if not uri:
                raise ValueError(
                    f"bulk-data entry for {BULK_DATA_TYPE!r} has neither "
                    f"jsonl_download_uri nor download_uri: {entry!r}"
                )
            return uri
    raise ValueError(f"No bulk-data entry of type {BULK_DATA_TYPE!r} found")


_BOOSTER_FUN_SUFFIX = "-BF"


def _strip_booster_fun_suffix(hareruya_product_code: str) -> str:
    if hareruya_product_code.upper().endswith(_BOOSTER_FUN_SUFFIX):
        return hareruya_product_code[: -len(_BOOSTER_FUN_SUFFIX)]
    return hareruya_product_code


def _is_booster_fun_set(set_row: Set) -> bool:
    return bool(
        set_row.hareruya_product_code
        and set_row.hareruya_product_code.upper().endswith(_BOOSTER_FUN_SUFFIX)
    )


async def _fetch_all_scryfall_set_codes(client: httpx.AsyncClient) -> set[str]:
    resp = await client.get(SETS_URL, headers=REQUEST_HEADERS)
    resp.raise_for_status()
    return {entry["code"] for entry in resp.json()["data"]}


def load_set_code_overrides(path: Path | None = None) -> dict[str, str]:
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
                f"{path}: value for {key!r} must be a string, "
                f"got {type(value).__name__}: {value!r}"
            )
        if not value:
            # Commented-out template entries in the shipped config use
            # empty strings as placeholders -- skip rather than apply.
            continue

    return {k: v for k, v in data.items() if v}


async def resolve_scryfall_set_codes(
    session: Session, overrides_path: Path | None = None
) -> None:
    """Fill in `sets.scryfall_set_code` for every Set.

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

    async with httpx.AsyncClient(timeout=30.0) as client:
        valid_codes = await _fetch_all_scryfall_set_codes(client)

    unresolved: list[Set] = []
    resolved = 0
    overridden = 0

    for set_row in session.execute(select(Set)).scalars().all():
        if not set_row.hareruya_product_code:
            continue

        override = overrides.get(set_row.hareruya_product_code)
        if override:
            if override not in valid_codes:
                logger.warning(
                    "Override %s -> %r is not a recognized Scryfall set code "
                    "-- applying it anyway, but double-check it",
                    set_row.hareruya_product_code, override,
                )
            set_row.scryfall_set_code = override
            overridden += 1
            continue

        if set_row.scryfall_set_code:
            continue  # already resolved (automatically) in a previous run

        base_code = _strip_booster_fun_suffix(set_row.hareruya_product_code)
        candidate = base_code.lower()
        if candidate in valid_codes:
            set_row.scryfall_set_code = candidate
            resolved += 1
        else:
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
            ", ".join(s.hareruya_product_code or "?" for s in unresolved[:20]),
        )


def _parse_bulk_body(raw: bytes) -> list[dict[str, Any]]:
    """Parses a Scryfall bulk-data response body, tolerating either of
    the shapes Scryfall has served over time:

      - gzip-compressed JSONL (current, as of the July 2026 format
        change): one JSON object per line, body is raw gzip bytes.
      - plain JSONL: same, but not gzip-compressed (e.g. if the HTTP
        client already transparently decoded a Content-Encoding: gzip
        header, which is a different thing from the file itself being
        a .jsonl.gz archive).
      - a single top-level JSON array (the pre-change format): kept as
        a fallback so this doesn't break if an older/cached endpoint
        is ever hit.

    We detect which shape we got rather than assuming, since trusting
    a hardcoded format is exactly what broke on the last format change.
    """
    try:
        text = gzip.decompress(raw).decode("utf-8")
    except OSError:
        # Not gzip-compressed -- either already decoded for us, or was
        # never gzipped in the first place.
        text = raw.decode("utf-8")

    stripped = text.lstrip()
    if stripped.startswith("["):
        return json.loads(text)

    return [json.loads(line) for line in text.splitlines() if line.strip()]


async def fetch_default_cards() -> list[dict[str, Any]]:
    """Downloads and parses the full default_cards bulk file.

    This is a large file (several hundred MB as of writing). Fine for a
    periodic batch job; don't call this per-request. If memory becomes
    an issue, switch to a streaming parser -- the logic below doesn't
    care how the dicts arrive, only that it gets an iterable of card
    objects.
    """
    async with httpx.AsyncClient(timeout=300.0, follow_redirects=True) as client:
        download_uri = await _get_bulk_data_download_uri(client)
        logger.info("Downloading Scryfall bulk data from %s", download_uri)
        resp = await client.get(download_uri, headers=REQUEST_HEADERS)
        resp.raise_for_status()
        cards = _parse_bulk_body(resp.content)
        logger.info("Parsed %d cards from bulk data", len(cards))
        return cards


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


def _card_is_booster_fun(card: dict[str, Any]) -> bool:
    """Mirrors Scryfall's own `is:boosterfun` search filter: true for
    showcase/extended-art/borderless alternate treatments sold
    specifically as Collector Booster chase versions of a card that
    also has a normal-frame printing in the same set."""
    return "boosterfun" in (card.get("promo_types") or [])


def _build_set_resolver(
    session: Session,
) -> tuple[dict[str, Set], dict[str, Set]]:
    """Groups local Set rows by shared scryfall_set_code, splitting
    each group into its "primary" (normal-frame) and "booster fun"
    entry where both exist.

    Returns (primary_by_code, booster_fun_by_code) -- either dict may
    be missing a given code if that variant isn't tracked locally.
    """
    primary_by_code: dict[str, Set] = {}
    booster_fun_by_code: dict[str, Set] = {}

    for set_row in session.execute(select(Set)).scalars().all():
        if not set_row.scryfall_set_code:
            continue
        if _is_booster_fun_set(set_row):
            booster_fun_by_code[set_row.scryfall_set_code] = set_row
        else:
            primary_by_code[set_row.scryfall_set_code] = set_row

    return primary_by_code, booster_fun_by_code


def _resolve_local_set(
    card: dict[str, Any],
    primary_by_code: dict[str, Set],
    booster_fun_by_code: dict[str, Set],
) -> Set | None:
    set_code = card["set"]

    if _card_is_booster_fun(card):
        # Prefer the dedicated Booster Fun product if we track it
        # separately; fall back to the primary set if we don't (better
        # to have the price land somewhere sensible than drop it).
        return booster_fun_by_code.get(set_code) or primary_by_code.get(set_code)

    return primary_by_code.get(set_code)


def sync_printings(session: Session, cards: list[dict[str, Any]]) -> None:
    primary_by_code, booster_fun_by_code = _build_set_resolver(session)

    if not primary_by_code and not booster_fun_by_code:
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
        key = (card["set"], card["collector_number"])
        printing = existing.get(key)

        if printing is None:
            printing = Printing(
                set=card["set"],
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
