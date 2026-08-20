"""Apply only coordinate results explicitly accepted by the bounded QA audit."""

from __future__ import annotations

import argparse
import json

from sqlalchemy import MetaData, create_engine, select

from ingestion.environment import ROOT, database_url


SOURCE = ROOT / "reports" / "ingestion" / "mvp-coordinate-gaps-2026.json"
REPORT = ROOT / "reports" / "ingestion" / "write-reviewed-coordinates-2026.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--confirm-write", action="store_true")
    args = parser.parse_args()
    if args.write and not args.confirm_write:
        parser.error("--write requires --confirm-write")

    audited = json.loads(SOURCE.read_text(encoding="utf-8"))
    accepted = [item for item in audited["venues"] if item["status"] == "accepted"]
    engine = create_engine(database_url(), connect_args={"connect_timeout": 10})
    metadata = MetaData()
    metadata.reflect(engine, only=["venues"])
    venues = metadata.tables["venues"]

    with engine.connect() as connection:
        rows = {
            row.venue_id: row
            for row in connection.execute(
                select(venues.c.venue_id, venues.c.latitude, venues.c.longitude).where(
                    venues.c.venue_id.in_([item["venue"]["venue_id"] for item in accepted])
                )
            )
        }
    missing = [item["venue"]["venue_id"] for item in accepted if item["venue"]["venue_id"] not in rows]
    if missing:
        raise RuntimeError(f"Audited venues no longer exist: {missing}")
    planned = [
        item for item in accepted
        if rows[item["venue"]["venue_id"]].latitude is None
        or rows[item["venue"]["venue_id"]].longitude is None
    ]
    preserved = [
        item for item in accepted
        if rows[item["venue"]["venue_id"]].latitude is not None
        and rows[item["venue"]["venue_id"]].longitude is not None
    ]
    report = {
        "source": str(SOURCE),
        "planned_coordinate_updates": len(planned),
        "already_valid_preserved": len(preserved),
        "written": False,
        "venue_ids": [item["venue"]["venue_id"] for item in planned],
    }
    if not args.write:
        print(json.dumps(report, indent=2))
        return 0

    with engine.begin() as connection:
        updated = 0
        for item in planned:
            venue_id = item["venue"]["venue_id"]
            result = connection.execute(
                venues.update().where(
                    venues.c.venue_id == venue_id,
                    (venues.c.latitude.is_(None) | venues.c.longitude.is_(None)),
                ).values(latitude=item["latitude"], longitude=item["longitude"])
            )
            updated += result.rowcount
        if updated != len(planned):
            raise RuntimeError(f"Expected {len(planned)} updates, got {updated}; rolling back")
    report.update({"written": True, "coordinate_updates": updated})
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
