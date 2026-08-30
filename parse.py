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

_COLLECTOR_NUMBER_RE = re.compile(r"^\((\d+)\)")


@dataclass
class ParsedDoc:
    hareruya_product_id: int
    collector_number: str | None
    name_en: str | None
    name_jp: str | None
    language: str  # "jp" or "en" -- Hareruya's language field is "1"/"2"
    price_yen: int
    stock: int
    weekly_sales: int
    foil: bool
    card_condition: str | None


_LANGUAGE_MAP = {"1": "jp", "2": "en"}


def extract_collector_number(product_name: str) -> str | None:
    match = _COLLECTOR_NUMBER_RE.match(product_name.strip())
    return match.group(1) if match else None


def parse_doc(doc: dict) -> ParsedDoc:
    product_name = doc.get("product_name", "") or ""
    product_name_en = doc.get("product_name_en", "") or ""

    collector_number = extract_collector_number(product_name) or extract_collector_number(
        product_name_en
    )

    return ParsedDoc(
        hareruya_product_id=int(doc["product"]),
        collector_number=collector_number,
        name_en=doc.get("card_name"),
        name_jp=None,  # card_name in the sample data is already English;
        # the JP name would need to be pulled from product_name if needed.
        language=_LANGUAGE_MAP.get(str(doc.get("language")), "en"),
        price_yen=int(doc.get("price", 0)),
        stock=int(doc.get("stock", 0)),
        weekly_sales=int(doc.get("weekly_sales", 0)),
        foil=str(doc.get("foil_flg")) == "1",
        card_condition=doc.get("card_condition"),
    )


def parse_docs(docs: list[dict]) -> list[ParsedDoc]:
    return [parse_doc(d) for d in docs]
