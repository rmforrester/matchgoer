"""Non-writing coordinate-enrichment audit for cached API-Football venues."""

import json
from collections import defaultdict
from pathlib import Path

from sqlalchemy import MetaData, create_engine, select

from config.leagues import COVERAGE_PROFILES
from ingest_leagues import resolve_scope
from ingestion.api_football import ApiFootballClient
from ingestion.coordinates import NominatimCoordinateEnricher, valid_coordinates
from ingestion.environment import ROOT, api_football_key, database_url
from ingestion.pipeline import TerraceTalkImporter


PROFILES = ("england-pyramid", "usa-priority", "sweden-priority")
CACHE_FILE = ROOT / ".cache" / "nominatim" / "coordinate-dry-run-2026.json"
REPORT_FILE = ROOT / "reports" / "ingestion" / "coordinate-dry-run-2026.json"


def load_cache() -> dict[str, dict]:
    if CACHE_FILE.exists():
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    return {}


def save_cache(cache: dict[str, dict]) -> None:
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(cache, indent=2), encoding="utf-8")


def main() -> int:
    client = ApiFootballClient(api_football_key(), ROOT / ".cache" / "api-football")
    importer = TerraceTalkImporter(client, database_url())
    engine = create_engine(database_url(), connect_args={"connect_timeout": 10})
    metadata = MetaData(); metadata.reflect(engine, only=["venues"])
    venue_table = metadata.tables["venues"]
    venue_by_id: dict[int, dict] = {}
    league_venues: dict[str, set[int]] = defaultdict(set)
    labels: dict[str, tuple[str, str]] = {}

    for profile in PROFILES:
        for configured in COVERAGE_PROFILES[profile]:
            scope = resolve_scope(client, configured)
            key = f"{scope.country}|{scope.display_name}"
            labels[key] = (scope.country, scope.display_name)
            if scope.league_id is None:
                continue
            teams, fixtures, available = importer._records(scope)
            if not available:
                continue
            for item in [*teams, *fixtures]:
                raw = item.get("venue") or (item.get("fixture") or {}).get("venue") or {}
                venue = importer._venue_record(raw, scope.country)
                if venue:
                    venue_by_id.setdefault(venue["venue_id"], venue)
                    league_venues[key].add(venue["venue_id"])

    with engine.connect() as connection:
        database_coordinates = {
            row.venue_id: (row.latitude, row.longitude)
            for row in connection.execute(
                select(venue_table.c.venue_id, venue_table.c.latitude, venue_table.c.longitude)
                .where(venue_table.c.venue_id.in_(venue_by_id))
            )
        }

    cache = load_cache()
    results: dict[int, dict] = {}
    enricher = NominatimCoordinateEnricher()
    for venue_id, venue in venue_by_id.items():
        existing = database_coordinates.get(venue_id, (None, None))
        if valid_coordinates(*existing):
            results[venue_id] = {"status": "database", "errors": []}
            continue
        cached = cache.get(str(venue_id))
        if cached:
            results[venue_id] = cached
            continue
        result = enricher.enrich(venue, strict_uniqueness=True)
        status = "geocoded" if result.source else "ambiguous" if result.ambiguous else "unresolved"
        cached = {
            "status": status,
            "latitude": result.latitude,
            "longitude": result.longitude,
            "queries_attempted": result.queries_attempted,
            "errors": list(result.errors),
        }
        cache[str(venue_id)] = cached
        results[venue_id] = cached
        save_cache(cache)

    reports = []
    for key, ids in league_venues.items():
        country, league = labels[key]
        rows = [results[venue_id] for venue_id in ids]
        reports.append({
            "country": country,
            "league": league,
            "total_unique_venues": len(ids),
            "already_valid_database_coordinates": sum(row["status"] == "database" for row in rows),
            "successfully_geocoded": sum(row["status"] == "geocoded" for row in rows),
            "still_unresolved": sum(row["status"] == "unresolved" for row in rows),
            "ambiguous_geocoding_results": sum(row["status"] == "ambiguous" for row in rows),
            "failed_geocoding_requests": sum(len(row.get("errors", [])) for row in rows),
            "unresolved_venues": [
                {"venue_id": venue_id, "name": venue_by_id[venue_id]["name"], "city": venue_by_id[venue_id]["city"], "status": results[venue_id]["status"]}
                for venue_id in ids if results[venue_id]["status"] in {"unresolved", "ambiguous"}
            ],
        })
    REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    REPORT_FILE.write_text(json.dumps(reports, indent=2), encoding="utf-8")
    print(json.dumps(reports, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
