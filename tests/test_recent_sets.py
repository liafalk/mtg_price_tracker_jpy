from __future__ import annotations

import datetime as dt
from contextlib import contextmanager
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.main import app
from models import HareruyaSet


class QueryCheckingSession:
    def __init__(self, rows):
        self._rows = rows

    def execute(self, stmt):
        sql = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        assert "sets.code" not in sql
        assert "sets_hareruya" in sql or "set_code" in sql
        return FakeResult(self._rows)


class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class FakeSession:
    def execute(self, stmt):
        return FakeResult(
            [
                HareruyaSet(
                    id=1,
                    hareruya_cardset_id=101,
                    hareruya_product_code="woe",
                    name_jp="ウィズダムの戦い",
                    set_code="woe",
                    release_date=dt.date(2024, 9, 20),
                ),
                HareruyaSet(
                    id=2,
                    hareruya_cardset_id=102,
                    hareruya_product_code="mkm",
                    name_jp="マキシマム・カップ",
                    set_code="mkm",
                    release_date=dt.date(2025, 2, 5),
                ),
            ]
        )


@contextmanager
def fake_session_factory():
    yield FakeSession()


client = TestClient(app)


def test_recent_sets_api_returns_latest_releases():
    with patch("api.main.SessionLocal", fake_session_factory):
        response = client.get("/api/recent_sets?limit=5")

    assert response.status_code == 200
    data = response.json()
    assert data["sets"][0]["code"] == "mkm"
    assert data["sets"][0]["name"] == "マキシマム・カップ"
    assert data["sets"][1]["code"] == "woe"


def test_recent_sets_query_uses_hareruya_set_schema():
    rows = [
        HareruyaSet(
            id=1,
            hareruya_cardset_id=101,
            hareruya_product_code="woe",
            name_jp="ウィズダムの戦い",
            set_code="woe",
            release_date=dt.date(2024, 9, 20),
        )
    ]

    with patch("api.main.SessionLocal", lambda: QueryCheckingSession(rows)):
        response = client.get("/api/recent_sets?limit=5")

    assert response.status_code == 200
    assert response.json()["sets"][0]["code"] == "woe"
