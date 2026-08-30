"""
Parsing helpers: turn raw Hareruya JSON docs into structured records.

The collector number isn't a dedicated field in the API response -- it's
embedded as a leading "(123)" in product_name, e.g.:
    "(128)《小さな熊/Little Bear》[HOB] 緑C"

We also strip the bracketed set code and trailing rarity/color glyphs to
get a clean English name where possible, though product_name_en is
generally cleaner for that.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
import logging

_COLLECTOR_NUMBER_RE = re.compile(r"\((\d+)\)")

logger = logging.getLogger(__name__)


# Hareruya zero-pads collector numbers in product names (e.g. "(099)"),
# Scryfall does not (e.g. "99"). Since Scryfall is the identity source
# of truth (see sync_scryfall.py), we normalize to Scryfall's convention
# so lookups against `printings.collector_number` actually match.
_LEADING_ZEROS_RE = re.compile(r"^0*(\d+)(.*)$")

def normalize_collector_number(collector_number: str) -> str:
    match = _LEADING_ZEROS_RE.match(collector_number.strip())
    if match:
        digits, suffix = match.groups()
        return f"{digits}{suffix}"
    return collector_number


@dataclass
class ParsedDoc:
    hareruya_product_id: int
    collector_number: str | None
    card_name: str
    product_name: str
    language: str  # "jp" or "en" -- Hareruya's language field is "1"/"2"
    price_yen: int
    stock: int
    weekly_sales: int
    foil: bool
    card_condition: str | None


_LANGUAGE_MAP = {"1": "jp", "2": "en"}


def extract_collector_number(product_name: str) -> str | None:
    match = _COLLECTOR_NUMBER_RE.search(product_name.strip())
    return match.group(1) if match else None


def parse_doc(doc: dict) -> ParsedDoc:
    product_name = doc.get("product_name", "") or ""
    product_name_en = doc.get("product_name_en", "") or ""

    # Ignore art cards
    if product_name.find("アート・カード") > 0:
        return None

    # Ignore tokens
    if product_name.find("トークン") > 0:
        return None

    # Promo / prerelease cards still map to their Scryfall variants
    # (e.g. TLA -> PTLA, 226 -> 226p or 226s), so we keep them in the
    # pipeline and let the crawl matcher resolve the correct printing.
    raw_collector_number = extract_collector_number(product_name) or extract_collector_number(
        product_name_en
    )

    if raw_collector_number is None:
        logger.warning(
            "Could not extract collector number for product=%s in set=%s; keeping doc for name-based fallback",
            doc.get("product"),
            doc.get("cardset"),
        )

    return ParsedDoc(
        hareruya_product_id=int(doc["product"]),
        collector_number=(
            normalize_collector_number(raw_collector_number)
            if raw_collector_number is not None
            else None
        ),
        card_name=doc.get("card_name"),
        product_name=product_name,
        language=_LANGUAGE_MAP.get(str(doc.get("language")), "en"),
        price_yen=int(doc.get("price", 0)),
        stock=int(doc.get("stock", 0)),
        weekly_sales=int(doc.get("weekly_sales", 0)),
        foil=str(doc.get("foil_flg")) == "1",
        card_condition=doc.get("card_condition"),
    )


def parse_docs(docs: list[dict]) -> list[ParsedDoc]:
    return [x for x in [parse_doc(d) for d in docs] if x is not None]
