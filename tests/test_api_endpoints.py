"""
Tests for every /api/* endpoint (and the static page routes).

Each endpoint is exercised with a fake in-memory session so the tests run
without a real database. The suggestions endpoint -- which may be hit on
every keystroke -- is covered with both a hit and a miss, plus a guard for
an empty query.
"""

from __future__ import annotations

import datetime as dt
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
    """Returns the same set of printings for every query."""

    def __init__(self, rows):
        self._rows = rows

    def execute(self, stmt):
        return _Rows(self._rows)


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


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
        response = client.get("/api/suggestions?q=%E9%BB%92%E5%B3%B6")  # 頭蓋

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
        response = client.get("/api/suggestions?q=bolt&limit=2")

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
def test_recent_sets_uses_hareruya_model():
    from models import HareruyaSet

    with patch("api.main.SessionLocal", printing_session_factory):
        response = client.get("/api/recent_sets?limit=3")

    assert response.status_code == 200
    data = response.json()
    # No rows match the HareruyaSet query, so the list is empty.
    assert data["sets"] == []


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
        response = client.get("/api/prices?set=doesnotexist?number=1")

    assert response.status_code == 404



