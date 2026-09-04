"""Migrate the pre-2026-09 set schema to the current schema.

The legacy ``sets`` table contained Hareruya cardsets. The current schema
uses ``sets`` for canonical Scryfall sets and ``sets_hareruya`` for Hareruya
cardsets. This migration preserves all existing IDs and leaves printings and
prices unchanged.
"""

from __future__ import annotations

import argparse
import os

from sqlalchemy import inspect, text

from db import engine
from models import Base


def migrate() -> int:
    """Run the migration and return the number of unresolved cardsets."""
    with engine.begin() as connection:
        inspector = inspect(connection)
        has_legacy_table = inspector.has_table("sets") and {
            column["name"] for column in inspector.get_columns("sets")
        } >= {"hareruya_cardset_id", "set_code"}

        if has_legacy_table:
            sequence_exists = connection.execute(
                text("""
                    SELECT EXISTS (
                        SELECT 1
                        FROM pg_class
                        WHERE relkind = 'S' AND relname = 'sets_id_seq'
                    )
                """)
            ).scalar_one()
            if sequence_exists:
                connection.execute(
                    text("ALTER SEQUENCE sets_id_seq RENAME TO sets_hareruya_id_seq")
                )
            connection.execute(text("ALTER TABLE sets RENAME TO sets_hareruya"))

        inspector = inspect(connection)
        if not inspector.has_table("sets_hareruya"):
            raise RuntimeError("Neither legacy sets nor sets_hareruya exists")

        hareruya_columns = {
            column["name"] for column in inspector.get_columns("sets_hareruya")
        }
        if "scryfall_set_code" not in hareruya_columns:
            connection.execute(
                text(
                    "ALTER TABLE sets_hareruya "
                    "ADD COLUMN scryfall_set_code VARCHAR(16)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX ix_sets_hareruya_scryfall_set_code "
                    "ON sets_hareruya (scryfall_set_code)"
                )
            )

        # create_all creates the new canonical table but intentionally does
        # not alter the renamed Hareruya table.
        Base.metadata.create_all(connection)

        constraints = inspect(connection).get_foreign_keys("sets_hareruya")
        has_set_fk = any(
            constraint.get("referred_table") == "sets"
            and "scryfall_set_code" in constraint.get("constrained_columns", [])
            for constraint in constraints
        )
        if not has_set_fk:
            connection.execute(
                text(
                    "ALTER TABLE sets_hareruya "
                    "ADD CONSTRAINT fk_sets_hareruya_scryfall_set_code "
                    "FOREIGN KEY (scryfall_set_code) REFERENCES sets(code)"
                )
            )

        connection.execute(
            text("""
                INSERT INTO sets (code, name_en, name_jp, release_date)
                SELECT DISTINCT ON (set_code)
                    set_code,
                    COALESCE(name_jp, set_code),
                    name_jp,
                    release_date
                FROM sets_hareruya
                WHERE set_code IS NOT NULL
                ORDER BY set_code, id
                ON CONFLICT (code) DO NOTHING
            """)
        )
        connection.execute(
            text("""
                UPDATE sets_hareruya
                SET scryfall_set_code = set_code
                WHERE set_code IS NOT NULL
                  AND scryfall_set_code IS DISTINCT FROM set_code
            """)
        )

        unresolved = connection.execute(
            text(
                "SELECT count(*) FROM sets_hareruya "
                "WHERE scryfall_set_code IS NULL"
            )
        ).scalar_one()

    return int(unresolved)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    unresolved = migrate()
    print(f"Migration complete; {unresolved} Hareruya sets need Scryfall mapping.")
    print(f"Database: {os.environ.get('DATABASE_URL', 'default DATABASE_URL')}")


if __name__ == "__main__":
    main()