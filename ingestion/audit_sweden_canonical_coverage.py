"""Build the deterministic read-only Sweden canonical-process comparison report."""

from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, text

from config.leagues import COVERAGE_PROFILES
from ingestion.api_football import ApiFootballClient


ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".cache" / "api-football"
CHECKPOINT = ROOT / ".cache" / "nominatim" / "sweden-canonical-coordinate-audit-2026.json"
COORDINATE_REPORT = ROOT / "reports" / "ingestion" / "sweden-canonical-coordinate-audit-2026.json"
OUTPUT = ROOT / "reports" / "ingestion" / "sweden-canonical-process-audit-2026.json"


def fixture_payloads() -> tuple[dict[int, dict], dict[int, dict[int, dict]]]:
    client = ApiFootballClient(os.environ["API_FOOTBALL_KEY"], CACHE)
    fixtures: dict[int, dict] = {}
    team_venues: dict[int, dict[int, dict]] = {}
    for scope in COVERAGE_PROFILES["sweden-priority"]:
        teams = client.teams(scope.league_id, scope.provider_season)
        team_venues[scope.league_id] = {
            int(row["team"]["id"]): row.get("venue") or {}
            for row in teams if (row.get("team") or {}).get("id")
        }
        for row in client.fixtures(scope.league_id, scope.provider_season):
            fixtures[int(row["fixture"]["id"])] = row
    return fixtures, team_venues


def main() -> None:
    checkpoint = json.loads(CHECKPOINT.read_text(encoding="utf-8"))
    coordinate_report = json.loads(COORDINATE_REPORT.read_text(encoding="utf-8"))
    if coordinate_report["summary"]["NOT_ATTEMPTED"]:
        raise RuntimeError("Coordinate audit is incomplete")
    provider_fixtures, team_venues = fixture_payloads()
    engine = create_engine(os.environ["DATABASE_URL"], connect_args={"connect_timeout": 10})
    with engine.connect() as connection:
        connection.execute(text("SET TRANSACTION READ ONLY"))
        fixture_rows = [dict(row) for row in connection.execute(text("""
            SELECT f.fixture_id, f.league_id, f.league_name, f.home_team_id,
                   f.venue_id, v.latitude, v.longitude
            FROM fixtures f LEFT JOIN venues v ON v.venue_id=f.venue_id
            WHERE f.country='Sweden'
            ORDER BY f.league_id,f.fixture_id
        """)).mappings()]
        ref_rows = [dict(row) for row in connection.execute(text("""
            SELECT provider_venue_id, venue_id
            FROM venue_provider_refs WHERE provider='api_football'
        """)).mappings()]
        legacy_rows = [dict(row) for row in connection.execute(text("""
            SELECT provider_venue_id, venue_id FROM venues WHERE provider_venue_id IS NOT NULL
        """)).mappings()]
    provider_to_canonical: dict[int, set[int]] = defaultdict(set)
    canonical_to_provider: dict[int, set[int]] = defaultdict(set)
    for row in [*ref_rows, *legacy_rows]:
        provider_to_canonical[int(row["provider_venue_id"])].add(int(row["venue_id"]))
        canonical_to_provider[int(row["venue_id"])].add(int(row["provider_venue_id"]))

    classifications = Counter()
    safe_link_targets: dict[int, int] = {}
    for row in fixture_rows:
        if row["venue_id"] is not None:
            continue
        raw = provider_fixtures[row["fixture_id"]]
        fixture_venue = (raw.get("fixture") or {}).get("venue") or {}
        home_venue = team_venues[row["league_id"]].get(row["home_team_id"], {})
        direct_id, home_id = fixture_venue.get("id"), home_venue.get("id")
        if direct_id is not None and len(provider_to_canonical[int(direct_id)]) == 1:
            category = "fixture_provider_id_uniquely_mapped"
            safe_link_targets[row["fixture_id"]] = next(iter(provider_to_canonical[int(direct_id)]))
        elif direct_id is not None:
            category = "fixture_provider_id_unmapped_or_ambiguous"
        elif home_id is not None and len(provider_to_canonical[int(home_id)]) == 1:
            category = "home_provider_id_uniquely_mapped"
            safe_link_targets[row["fixture_id"]] = next(iter(provider_to_canonical[int(home_id)]))
        elif home_id is not None:
            category = "home_provider_id_unmapped_or_ambiguous"
        elif fixture_venue.get("name") or fixture_venue.get("city"):
            category = "fixture_name_or_city_only"
        elif home_venue.get("name") or home_venue.get("city"):
            category = "home_venue_name_or_city_only"
        else:
            category = "no_useful_provider_venue_data"
        classifications[category] += 1

    resolved_provider_ids = {
        int(provider_id) for provider_id, result in checkpoint.items()
        if result.get("status") == "geocoded"
    }
    used_null_canonical_ids = {
        int(row["venue_id"]) for row in fixture_rows
        if row["venue_id"] is not None
        and (row["latitude"] is None or row["longitude"] is None)
    }
    relevant_provider_ids = {
        int(provider_id) for provider_id in checkpoint
        if provider_to_canonical.get(int(provider_id), set()) & used_null_canonical_ids
    }
    relevant_statuses = Counter(checkpoint[str(provider_id)].get("status") for provider_id in relevant_provider_ids)
    relevant_resolved_provider_ids = resolved_provider_ids & relevant_provider_ids
    resolved_canonical_ids = {
        canonical_id
        for provider_id in resolved_provider_ids
        for canonical_id in provider_to_canonical.get(provider_id, set())
    }
    coordinate_unlock_ids = {
        row["fixture_id"] for row in fixture_rows
        if row["venue_id"] in resolved_canonical_ids
        and (row["latitude"] is None or row["longitude"] is None)
    }
    link_unlock_ids = {
        fixture_id for fixture_id, venue_id in safe_link_targets.items()
        if any(
            row["venue_id"] == venue_id
            and row["latitude"] is not None and row["longitude"] is not None
            for row in fixture_rows
        )
    }
    both_unlock_ids = set(coordinate_unlock_ids) | set(link_unlock_ids)
    for fixture_id, venue_id in safe_link_targets.items():
        if venue_id in resolved_canonical_ids:
            both_unlock_ids.add(fixture_id)

    competitions = []
    by_league: dict[int, list[dict]] = defaultdict(list)
    for row in fixture_rows:
        by_league[row["league_id"]].append(row)
    for league_id, rows in sorted(by_league.items()):
        ready = sum(row["venue_id"] is not None and row["latitude"] is not None and row["longitude"] is not None for row in rows)
        unlinked = sum(row["venue_id"] is None for row in rows)
        coordinate_null = len(rows) - ready - unlinked
        projected = ready + sum(row["fixture_id"] in both_unlock_ids for row in rows)
        competitions.append({
            "league_id": league_id, "competition": rows[0]["league_name"], "fixtures": len(rows),
            "current_map_ready": ready, "current_percent": round(100 * ready / len(rows), 1),
            "unlinked": unlinked, "coordinate_null": coordinate_null,
            "projected_safe_map_ready": projected, "projected_percent": round(100 * projected / len(rows), 1),
        })

    current = sum(row["venue_id"] is not None and row["latitude"] is not None and row["longitude"] is not None for row in fixture_rows)
    scenarios = {
        "current": current,
        "automatic_coordinates_only": current + len(coordinate_unlock_ids),
        "deterministic_links_only": current + len(link_unlock_ids),
        "both": current + len(both_unlock_ids),
    }
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "READ_ONLY",
        "hosted": {
            "fixtures": len(fixture_rows), "current_map_ready": current,
            "unlinked": sum(row["venue_id"] is None for row in fixture_rows),
            "linked_coordinate_null": sum(row["venue_id"] is not None and (row["latitude"] is None or row["longitude"] is None) for row in fixture_rows),
            "distinct_linked_coordinate_null_venues": len({row["venue_id"] for row in fixture_rows if row["venue_id"] is not None and (row["latitude"] is None or row["longitude"] is None)}),
        },
        "unlinked_classification": dict(sorted(classifications.items())),
        "deterministic_safe_link_count": len(safe_link_targets),
        "coordinate_audit": {
            "venues_considered": len(used_null_canonical_ids),
            "AUTO_RESOLVED": relevant_statuses["geocoded"],
            "AMBIGUOUS": relevant_statuses["ambiguous"],
            "UNRESOLVED": relevant_statuses["unresolved"],
            "ERROR": relevant_statuses["error"],
            "raw_provider_cohort_note": "The generic runner also examined two null-coordinate provider venues unused by Swedish fixtures; they are excluded here.",
        },
        "coordinate_auto_resolved_provider_ids": sorted(relevant_resolved_provider_ids),
        "safe_coordinate_fixture_unlocks": len(coordinate_unlock_ids),
        "scenarios": {
            name: {
                "map_ready": value,
                "sweden_percent": round(100 * value / len(fixture_rows), 1),
                "europe_map_ready": 22515 + value - current,
                "europe_percent": round(100 * (22515 + value - current) / 26043, 1),
            }
            for name, value in scenarios.items()
        },
        "competitions": competitions,
        "safety": {"hosted_writes": 0, "fixture_links_changed": 0, "coordinates_changed": 0},
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(OUTPUT)


if __name__ == "__main__":
    main()
