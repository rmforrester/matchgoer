"""Apply one reviewed manual venue override without broad league upserts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sqlalchemy import MetaData, create_engine, func, select

from config.venue_overrides import manual_override_for
from ingestion.api_football import ApiFootballClient
from ingestion.environment import ROOT, api_football_key, database_url


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--league-id", type=int, required=True)
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--home-team-id", type=int, required=True)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--confirm-write", action="store_true")
    args = parser.parse_args()
    if args.write and not args.confirm_write:
        parser.error("--write requires --confirm-write")

    override = manual_override_for(args.league_id, args.season, args.home_team_id)
    if override is None:
        raise RuntimeError("No reviewed manual override matches the requested scope.")
    report_path = (
        ROOT / "reports" / "ingestion" /
        f"manual-venue-override-{args.league_id}-{args.season}-{args.home_team_id}.json"
    )
    client = ApiFootballClient(api_football_key(), ROOT / ".cache" / "api-football")
    payloads = client.fixtures(args.league_id, args.season)
    eligible_provider_fixtures = {
        item["fixture"]["id"]
        for item in payloads
        if item.get("fixture", {}).get("id")
        and not (item.get("fixture", {}).get("venue") or {}).get("id")
        and item.get("teams", {}).get("home", {}).get("id") == args.home_team_id
    }

    engine = create_engine(database_url(), connect_args={"connect_timeout": 10})
    metadata = MetaData()
    metadata.reflect(engine, only=["fixtures", "venues"])
    fixtures, venues = metadata.tables["fixtures"], metadata.tables["venues"]
    fixture_scope = (
        fixtures.c.fixture_id.in_(eligible_provider_fixtures),
        fixtures.c.league_id == args.league_id,
        fixtures.c.season == args.season,
        fixtures.c.home_team_id == args.home_team_id,
        fixtures.c.venue_id.is_(None),
    )
    with engine.connect() as connection:
        unresolved_before = connection.execute(
            select(func.count()).select_from(fixtures).where(*fixture_scope)
        ).scalar_one()
        existing_venue_id = connection.execute(
            select(venues.c.venue_id).where(
                venues.c.provider_venue_id.is_(None),
                venues.c.name == override.venue_name,
                venues.c.city == override.city,
                venues.c.country == override.country,
            )
        ).scalar_one_or_none()
    planned = {
        "manual_venue_inserts": int(existing_venue_id is None),
        "fixture_updates": unresolved_before,
        "team_updates": 0,
        "other_fixture_updates": 0,
    }
    report = {
        "scope": {"provider": override.provider, "league_id": args.league_id, "season": args.season,
                  "home_team_provider_id": args.home_team_id, "team": override.team_name},
        "source": override.source,
        "unresolved_before": unresolved_before,
        "eligible_provider_fixture_ids": sorted(eligible_provider_fixtures),
        "planned": planned,
        "written": False,
    }
    if not args.write:
        print(json.dumps(report, indent=2))
        return 0
    if unresolved_before != len(eligible_provider_fixtures):
        raise RuntimeError(
            f"Expected {len(eligible_provider_fixtures)} eligible unresolved fixtures, found {unresolved_before}; refusing write."
        )

    with engine.begin() as connection:
        venue_id = connection.execute(
            select(venues.c.venue_id).where(
                venues.c.provider_venue_id.is_(None),
                venues.c.name == override.venue_name,
                venues.c.city == override.city,
                venues.c.country == override.country,
            )
        ).scalar_one_or_none()
        venue_values = {
            "provider_venue_id": None, "name": override.venue_name, "address": None,
            "city": override.city, "country": override.country, "capacity": None,
            "latitude": override.latitude, "longitude": override.longitude,
        }
        if venue_id is None:
            venue_id = connection.execute(
                venues.insert().values(**venue_values).returning(venues.c.venue_id)
            ).scalar_one()
        else:
            connection.execute(venues.update().where(venues.c.venue_id == venue_id).values(**venue_values))
        result = connection.execute(
            fixtures.update().where(*fixture_scope).values(
                venue_id=venue_id, venue_name=override.venue_name, venue_city=override.city
            )
        )
        if result.rowcount != unresolved_before:
            raise RuntimeError("Fixture update count changed during transaction; rolling back.")

    with engine.connect() as connection:
        unresolved_after = connection.execute(
            select(func.count()).select_from(fixtures).where(
                fixtures.c.fixture_id.in_(eligible_provider_fixtures),
                fixtures.c.league_id == args.league_id,
                fixtures.c.season == args.season,
                fixtures.c.home_team_id == args.home_team_id,
                fixtures.c.venue_id.is_(None),
            )
        ).scalar_one()
        venue_row = dict(connection.execute(select(venues).where(venues.c.venue_id == venue_id)).mappings().one())
    report.update({
        "written": True, "fixtures_linked_manual_verified": unresolved_before,
        "unresolved_after": unresolved_after, "venue": venue_row,
        "api_requests": client.requests_made, "api_cache_hits": client.cache_hits,
    })
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
