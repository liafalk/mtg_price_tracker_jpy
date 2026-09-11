"""Add the oracle_id, tcgplayer_id, and cardmarket_id columns to printings.

These columns were added to the Printing model in commit a764304
("add oracle, tcgplayer, cardmarket id") but the database was never
migrated. This script is idempotent -- it skips any column that
already exists.

Usage:
    python -m scripts.migrate_printing_ids
"""

from __future__ import annotations

from sqlalchemy import inspect, text

from db import engine

COLUMNS: dict[str, str] = {
    "oracle_id": "VARCHAR(36)",
    "tcgplayer_id": "INTEGER",
    "cardmarket_id": "INTEGER",
}


def migrate() -> None:
    with engine.begin() as connection:
        inspector = inspect(connection)
        existing = {
            column["name"] for column in inspector.get_columns("printings")
        }

        for name, sql_type in COLUMNS.items():
            if name in existing:
                print(f"{name}: already exists, skipping")
                continue
            connection.execute(
                text(f"ALTER TABLE printings ADD COLUMN {name} {sql_type}")
            )
            print(f"{name}: added ({sql_type})")

        # Index oracle_id to match the model definition (index=True).
        index_exists = connection.execute(
            text(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM pg_indexes
                    WHERE tablename = 'printings'
                      AND indexname = 'ix_printings_oracle_id'
                )
                """
            )
        ).scalar_one()
        if not index_exists:
            connection.execute(
                text("CREATE INDEX ix_printings_oracle_id ON printings (oracle_id)")
            )
            print("ix_printings_oracle_id: created")
        else:
            print("ix_printings_oracle_id: already exists, skipping")

        # Drop the now-removed sets_hareruya.release_date column. Release
        # dates are sourced from the linked Scryfall set (sets.release_date)
        # instead -- see models.HareruyaSet and scraper/tiering.py.
        hareruya_columns = {
            column["name"] for column in inspector.get_columns("sets_hareruya")
        }
        if "release_date" in hareruya_columns:
            connection.execute(text("ALTER TABLE sets_hareruya DROP COLUMN release_date"))
            print("sets_hareruya.release_date: dropped")
        else:
            print("sets_hareruya.release_date: already dropped, skipping")


if __name__ == "__main__":
    migrate()
