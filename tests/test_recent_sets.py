from __future__ import annotations

import datetime as dt
from contextlib import contextmanager
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.main import app
from models import ScryfallSet


class QueryCheckingSession:
    def __init__(self, rows):
        self._rows = rows

    def execute(self, stmt):
        sql = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        assert "sets" in sql
        assert "set_type" in sql
        return FakeResult(self._rows)


class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


def make_set(code, name_en, name_jp, release_date):
    return ScryfallSet(
        id=f"uuid-{code}",
        code=code,
        name_en=name_en,
        name_jp=name_jp,
        release_date=release_date,
        set_type="expansion",
        parent_set_code=None,
    )


@contextmanager
def fake_session_factory(rows):
    yield QueryCheckingSession(rows)


client = TestClient(app)


def test_recent_sets_api_returns_latest_releases():
    rows = [
        make_set("mkm", "Maximum Cup", "マキシマム・カップ", dt.date(2025, 2, 5)),
        make_set("woe", "Wizards' Edict", "ウィズダムの戦い", dt.date(2024, 9, 20)),
    ]

    with patch("api.main.SessionLocal", lambda: fake_session_factory(rows)):
        response = client.get("/api/recent_sets?limit=5")

    assert response.status_code == 200
    data = response.json()
    assert data["sets"][0]["code"] == "MKM"
    assert data["sets"][0]["name"] == "Maximum Cup"
    assert data["sets"][0]["name_jp"] == "マキシマム・カップ"
    assert data["sets"][0]["release_date"] == "2025-02-05"
    assert data["sets"][1]["code"] == "WOE"


def test_recent_sets_query_uses_scryfall_set_schema():
    rows = [
        make_set("woe", "Wizards' Edict", "ウィズダムの戦い", dt.date(2024, 9, 20)),
    ]

    with patch("api.main.SessionLocal", lambda: fake_session_factory(rows)):
        response = client.get("/api/recent_sets?limit=5")

    assert response.status_code == 200
    assert response.json()["sets"][0]["code"] == "WOE"
