"""Discover and audit requested Swedish men's league coverage for 2026."""

from __future__ import annotations

import json

from config.leagues import LeagueScope
from ingestion.api_football import ApiFootballClient
from ingestion.environment import ROOT, api_football_key
from ingestion.pipeline import TerraceTalkImporter


REPORT = ROOT / "reports" / "ingestion" / "sweden-coverage-2026.json"
EXACT_NAMES = {"Allsvenskan", "Superettan", "Ettan - Norra", "Ettan - Södra"}


def requested(name: str) -> bool:
    return name in EXACT_NAMES or (name.startswith("Division 2 - ") and "Play-offs" not in name)


def main() -> int:
    client = ApiFootballClient(api_football_key(), ROOT / ".cache" / "api-football")
    competitions = [item for item in client.leagues_by_country("Sweden") if requested(item.get("league", {}).get("name", ""))]
    rows = []
    for item in competitions:
        league_id, name = item["league"]["id"], item["league"]["name"]
        scope = LeagueScope("Sweden", league_id, name, 2026, "2026")
        coverage = client.league_for_season(league_id, 2026)
        available = bool(coverage and any(row.get("league", {}).get("id") == league_id for row in coverage))
        teams = client.teams(league_id, 2026) if available else []
        fixtures = client.fixtures(league_id, 2026) if available else []
        home_venues = TerraceTalkImporter._home_team_venues(teams)
        venue_ids = {row.get("venue", {}).get("id") for row in teams if row.get("venue", {}).get("id")}
        direct = fallback = unresolved = 0
        for row in fixtures:
            fixture = row.get("fixture") or {}
            raw_venue = fixture.get("venue") or {}
            if raw_venue.get("id"):
                venue_ids.add(raw_venue["id"])
            _, source, _, _ = TerraceTalkImporter._fixture_venue_link(
                fixture, row.get("teams", {}).get("home", {}).get("id"), home_venues, scope
            )
            direct += source == "fixture_provider"
            fallback += source == "home_team_fallback"
            unresolved += source == "unresolved"
        rows.append({"competition": name, "provider_league_id": league_id, "season": 2026,
                     "available": available, "fixtures": len(fixtures), "teams": len(teams),
                     "venues": len(venue_ids), "fixture_provider_links": direct,
                     "home_team_fallback_links": fallback, "unresolved_fixture_links": unresolved})
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps(rows[-1], ensure_ascii=False), flush=True)
    print(json.dumps({"competitions": len(rows), "api_requests": client.requests_made,
                      "api_cache_hits": client.cache_hits, "errors": client.failures}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
