"""Small, idempotent migration separating canonical and provider venue IDs."""

from __future__ import annotations

import json

from sqlalchemy import create_engine, inspect, text

from ingestion.environment import database_url


def main() -> int:
    engine = create_engine(database_url(), connect_args={"connect_timeout": 10})
    before: dict[str, object] = {}
    after: dict[str, object] = {}
    with engine.begin() as connection:
        connection.execute(text("LOCK TABLE venues IN ACCESS EXCLUSIVE MODE"))
        before = dict(connection.execute(text("""
            SELECT count(*) AS venue_count, max(venue_id) AS max_venue_id,
                   count(*) FILTER (WHERE venue_id IS NOT NULL) AS rows_to_backfill
            FROM venues
        """)).mappings().one())
        columns = {column["name"] for column in inspect(connection).get_columns("venues")}
        if "provider_venue_id" not in columns:
            connection.execute(text("ALTER TABLE venues ADD COLUMN provider_venue_id INTEGER NULL"))
        connection.execute(text("UPDATE venues SET provider_venue_id = venue_id WHERE provider_venue_id IS NULL"))
        connection.execute(text("""
            DO $$ BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint
                    WHERE conname = 'uq_venues_provider_venue_id'
                      AND conrelid = 'venues'::regclass
                ) THEN
                    ALTER TABLE venues
                    ADD CONSTRAINT uq_venues_provider_venue_id UNIQUE (provider_venue_id);
                END IF;
            END $$
        """))
        connection.execute(text("CREATE SEQUENCE IF NOT EXISTS venues_venue_id_seq AS INTEGER"))
        connection.execute(text("SELECT setval('venues_venue_id_seq', (SELECT max(venue_id) FROM venues), true)"))
        connection.execute(text("ALTER SEQUENCE venues_venue_id_seq OWNED BY venues.venue_id"))
        connection.execute(text("ALTER TABLE venues ALTER COLUMN venue_id SET DEFAULT nextval('venues_venue_id_seq')"))
        after = dict(connection.execute(text("""
            SELECT count(*) AS venue_count, max(venue_id) AS max_venue_id,
                   count(*) FILTER (WHERE provider_venue_id IS NOT NULL) AS populated_provider_ids,
                   count(*) FILTER (WHERE provider_venue_id IS NULL) AS manual_venues,
                   count(*) - count(DISTINCT provider_venue_id) AS null_adjusted_duplicate_check
            FROM venues
        """)).mappings().one())
        duplicate_count = connection.execute(text("""
            SELECT count(*) FROM (
                SELECT provider_venue_id FROM venues
                WHERE provider_venue_id IS NOT NULL
                GROUP BY provider_venue_id HAVING count(*) > 1
            ) duplicates
        """)).scalar_one()
        after["duplicate_provider_venue_ids"] = duplicate_count
        if before["venue_count"] != after["venue_count"] or duplicate_count:
            raise RuntimeError("Venue migration integrity check failed; transaction will roll back.")
    print(json.dumps({"before": before, "after": after}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
