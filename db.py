"""Database engine and session factory."""

from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models import Base

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql+psycopg://localhost/jpy_mtg_prices"
)

engine = create_engine(DATABASE_URL, echo=False, future=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db() -> None:
    """Create all tables. Fine for local dev; use Alembic migrations
    once the schema needs to evolve without dropping data."""
    Base.metadata.create_all(engine)


if __name__ == "__main__":
    init_db()
    print(f"Initialized schema at {DATABASE_URL}")
