"""
Tests for every /api/* endpoint (and the static page routes).

Each endpoint is exercised with a fake in-memory session so the tests run
without a real database. The suggestions endpoint -- which may be hit on
every keystroke -- is covered with both a hit and a miss, plus a guard for
an empty query.
"""

from __future__ import annotations

import datetime as dt
import re
from contextlib import contextmanager
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.main import app
from models import Printing


def _make_printing(
    id: int = 1,
    *,
    set_code: str = "hob",
    collector_number: str = "1",
    name_en: str = "Cranial Benediction",
    name_jp: str = "頭蓋の祝福",
    img_thumb_uri: str = "/thumbs/1.jpg",
) -> Printing:
    return Printing(
        id=id,
        set_code=set_code,
        collector_number=collector_number,
        name_en=name_en,
        name_jp=name_jp,
        rarity="rare",
        img_thumb_uri=img_thumb_uri,
        img_thumb_uri_jp=None,
    )


class PrintingSession:
    """Query-aware fake: inspects the compiled SQL and returns the rows the
    real query would have returned (set codes, filtered printings, or
    prices), so endpoint tests exercise the same filtering the API does."""

    def __init__(self, rows):
        self._rows = rows

    def execute(self, stmt):
        sql = str(stmt.compile(compile_kwargs={"literal_binds": True}))

        if "DISTINCT" in sql and "set_code" in sql and "name_en" not in sql:
            # /api/sets -- distinct set codes, sorted.
            codes = sorted({r.set_code for r in self._rows if r.set_code})
            return _Rows(codes)

        if "prices" in sql:
            # Second query of /api/search and /api/set_cards: prices for the
            # printings the first query returned. No price rows are seeded,
            # so this is always empty -- but it must not error. Checked before
            # the printings branch because the prices query also references
            # the printings table.
            return _Rows([])

        if "printings" in sql and "name_en" in sql:
            return _Rows(self._filter_printings(sql))

        return _Rows(self._rows)

    def _filter_printings(self, sql):
        if "DISTINCT" in sql:
            # /api/suggestions -- leading match, deduped by (name, set).
            # SQLAlchemy renders ilike() as lower(col) LIKE lower('term%').
            m = re.search(r"LIKE lower\('([^%']*)%'\)", sql)
            term = m.group(1) if m else ""
            seen = set()
            rows = []
            for r in sorted(self._rows, key=lambda r: (r.name_en or "")):
                name_en = (r.name_en or "").lower()
                name_jp = (r.name_jp or "").lower()
                if not (name_en.startswith(term) or name_jp.startswith(term)):
                    continue
                key = (r.name_en, r.set_code)
                if key in seen:
                    continue
                seen.add(key)
                rows.append(r)
            return rows

        m = re.search(r"LIKE '%([^']*)%'", sql)
        if m:
            # /api/search -- substring match on either name.
            term = m.group(1)
            return [
                r
                for r in self._rows
                if term in (r.name_en or "").lower()
                or term in (r.name_jp or "").lower()
            ]

        m = re.search(r"set_code = '([^']*)'", sql)
        if m:
            # /api/set_cards -- exact set code.
            return [r for r in self._rows if r.set_code == m.group(1)]

        return list(self._rows)


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None


@contextmanager
def printing_session_factory():
    yield PrintingSession(
        [
            _make_printing(1, name_en="Cranial Benediction", name_jp="頭蓋の祝福"),
            _make_printing(2, set_code="k39", name_en="Lightning Bolt", name_jp="閃光の雷"),
            _make_printing(3, set_code="hob", name_en="Lightning Bolt", name_jp="閃光の雷"),
        ]
    )


client = TestClient(app)


# --------------------------------------------------------------------------
# /api/suggestions -- the new autocomplete endpoint
# --------------------------------------------------------------------------
def test_suggestions_returns_leading_matches_for_en_names():
    with patch("api.main.SessionLocal", printing_session_factory):
        response = client.get("/api/suggestions?q=cranial")

    assert response.status_code == 200
    data = response.json()
    # "Cranial Benediction" begins with "cranial" (case-insensitive)
    assert len(data["results"]) == 1
    assert data["results"][0]["name_en"] == "Cranial Benediction"
    # Response includes the fields the dropdown needs to build a lookup URL.
    assert data["results"][0]["detail_url"] == "/card/hob/1"


def test_suggestions_matches_japanese_names():
    with patch("api.main.SessionLocal", printing_session_factory):
        response = client.get("/api/suggestions?q=%E9%A0%AD%E8%93%8B")  # 頭蓋

    assert response.status_code == 200
    results = response.json()["results"]
    assert any(r["name_jp"] == "頭蓋の祝福" for r in results)


def test_suggestions_empty_query_returns_no_results():
    with patch("api.main.SessionLocal", printing_session_factory):
        response = client.get("/api/suggestions?q=")

    assert response.status_code == 200
    assert response.json()["results"] == []


def test_suggestions_respects_limit():
    with patch("api.main.SessionLocal", printing_session_factory):
        response = client.get("/api/suggestions?q=lightning&limit=2")

    assert response.status_code == 200
    assert len(response.json()["results"]) == 2


def test_suggestions_returns_empty_when_no_match():
    with patch("api.main.SessionLocal", printing_session_factory):
        response = client.get("/api/suggestions?q=zzzzz")

    assert response.status_code == 200
    assert response.json()["results"] == []


# --------------------------------------------------------------------------
# /api/sets
# --------------------------------------------------------------------------
def test_list_set_codes_returns_sorted_codes():
    with patch("api.main.SessionLocal", printing_session_factory):
        response = client.get("/api/sets")

    assert response.status_code == 200
    codes = response.json()["sets"]
    assert codes == sorted(codes)
    assert "hob" in codes
    assert "k39" in codes


# --------------------------------------------------------------------------
# /api/recent_sets
# --------------------------------------------------------------------------
def test_recent_sets_uses_scryfall_set_model():
    from models import ScryfallSet

    rows = [
        ScryfallSet(
            id="uuid-mkm",
            code="mkm",
            name_en="Maximum Cup",
            name_jp="マキシマム・カップ",
            release_date=dt.date(2025, 2, 5),
            set_type="expansion",
            parent_set_code=None,
        )
    ]

    @contextmanager
    def scryfall_session_factory():
        yield PrintingSession(rows)

    with patch("api.main.SessionLocal", scryfall_session_factory):
        response = client.get("/api/recent_sets?limit=3")

    assert response.status_code == 200
    data = response.json()
    assert data["sets"][0]["code"] == "MKM"
    assert data["sets"][0]["name"] == "Maximum Cup"
    assert data["sets"][0]["name_jp"] == "マキシマム・カップ"


# --------------------------------------------------------------------------
# /api/search
# --------------------------------------------------------------------------
def test_search_returns_matching_printings():
    with patch("api.main.SessionLocal", printing_session_factory):
        response = client.get("/api/search?q=cranial")

    assert response.status_code == 200
    results = response.json()["results"]
    assert any(r["name_en"] == "Cranial Benediction" for r in results)


# --------------------------------------------------------------------------
# /api/set_cards
# --------------------------------------------------------------------------
def test_set_cards_returns_cards_for_set():
    with patch("api.main.SessionLocal", printing_session_factory):
        response = client.get("/api/set_cards?set=hob")

    assert response.status_code == 200
    codes = {r["set_code"] for r in response.json()["results"]}
    assert "hob" in codes


# --------------------------------------------------------------------------
# /api/prices
# --------------------------------------------------------------------------
def test_prices_returns_404_for_unknown_card():
    with patch("api.main.SessionLocal", printing_session_factory):
        response = client.get("/api/prices?set=doesnotexist&number=1")

    assert response.status_code == 404



