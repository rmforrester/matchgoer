"""Detect retained legacy coordinates whose recorded owner conflicts with current identity."""
from __future__ import annotations

import argparse, csv, json
from decimal import Decimal
from pathlib import Path

from sqlalchemy import MetaData, create_engine, select

from ingestion.environment import ROOT, database_url

COUNTRIES = ("England", "Germany", "Spain", "France", "Italy")


def normalized(value):
    return " ".join((value or "").casefold().replace("&apos;", "'").split())


def coordinate(value):
    return Decimal(str(value)).quantize(Decimal("0.000001"))


def legacy_rows(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return {int(row["venue_id"]): row for row in csv.DictReader(stream)}


def audit(connection, venues, fixtures, legacy):
    rows = connection.execute(
        select(venues).where(
            venues.c.country.in_(COUNTRIES),
            venues.c.latitude.is_not(None), venues.c.longitude.is_not(None),
            venues.c.venue_id.in_(select(fixtures.c.venue_id).where(fixtures.c.season == 2026)),
        )
    ).mappings()
    defects = []
    for row in rows:
        old = legacy.get(int(row["venue_id"]))
        if not old or not old.get("latitude") or not old.get("longitude"):
            continue
        retained = coordinate(row["latitude"]) == coordinate(old["latitude"]) and coordinate(row["longitude"]) == coordinate(old["longitude"])
        city_changed = normalized(row["city"]) != normalized(old.get("city"))
        name_changed = normalized(row["name"]) != normalized(old.get("name"))
        if retained and city_changed and (name_changed or normalized(row["country"]) == normalized(old.get("country"))):
            defects.append({
                "venue_id": int(row["venue_id"]), "country": row["country"],
                "current_name": row["name"], "current_city": row["city"],
                "legacy_name": old.get("name"), "legacy_city": old.get("city"),
                "latitude": str(row["latitude"]), "longitude": str(row["longitude"]),
                "classification": "DEFINITE_SAME_DEFECT",
            })
    return defects


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--legacy", type=Path, default=ROOT / "venues_with_coordinates_retry.csv")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    engine = create_engine(database_url(), connect_args={"connect_timeout": 10})
    metadata = MetaData()
    metadata.reflect(engine, only=["venues", "fixtures"])
    with engine.connect() as connection:
        defects = audit(connection, metadata.tables["venues"], metadata.tables["fixtures"], legacy_rows(args.legacy))
    payload = {"countries": list(COUNTRIES), "definite_same_defect": len(defects), "likely_same_defect": 0, "records": defects, "status": "PASS" if not defects else "FAIL"}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    raise SystemExit(0 if not defects else 1)


if __name__ == "__main__":
    main()
