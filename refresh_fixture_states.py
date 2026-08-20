"""Controlled API-Football refresh for mutable fixture time/status/result data."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import date, datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys

from dotenv import load_dotenv
from sqlalchemy import create_engine, select, text, update

from ingestion.api_football import ApiFootballClient


ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / "backend" / ".env")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Refresh existing Terrace Talk fixture states from API-Football")
    result.add_argument("--from-date", type=date.fromisoformat, default=date.today() - timedelta(days=7))
    result.add_argument("--to-date", type=date.fromisoformat, default=date.today() + timedelta(days=60))
    result.add_argument("--country", help="Optional existing fixture country scope")
    result.add_argument("--write", action="store_true")
    result.add_argument("--confirm-write", action="store_true")
    result.add_argument("--report", type=Path, default=ROOT / "reports" / "fixture-refresh-latest.json")
    return result


def main() -> int:
    args = parser().parse_args()
    if args.from_date > args.to_date:
        raise SystemExit("--from-date must not be after --to-date")
    if args.write and not args.confirm_write:
        raise SystemExit("--write requires --confirm-write after reviewing a dry run")
    database_url = os.getenv("DATABASE_URL")
    api_key = os.getenv("API_FOOTBALL_KEY") or os.getenv("API_SPORTS_KEY")
    if not database_url or not api_key:
        raise SystemExit("DATABASE_URL and API_FOOTBALL_KEY/API_SPORTS_KEY must be configured")

    engine = create_engine(database_url)
    from sqlalchemy import MetaData, Table
    metadata = MetaData()
    fixtures = Table("fixtures", metadata, autoload_with=engine)
    utc_day = fixtures.c.fixture_date.op("AT TIME ZONE")("UTC")
    scope_query = select(fixtures.c.league_id, fixtures.c.season).where(
        utc_day >= datetime.combine(args.from_date, datetime.min.time()),
        utc_day < datetime.combine(args.to_date + timedelta(days=1), datetime.min.time()),
        fixtures.c.league_id.is_not(None),
        fixtures.c.season.is_not(None),
    ).distinct()
    if args.country:
        scope_query = scope_query.where(fixtures.c.country == args.country)
    current_query = select(
        fixtures.c.fixture_id, fixtures.c.fixture_date, fixtures.c.status,
        fixtures.c.home_goals, fixtures.c.away_goals, fixtures.c.venue_name, fixtures.c.venue_city,
    ).where(
        utc_day >= datetime.combine(args.from_date, datetime.min.time()),
        utc_day < datetime.combine(args.to_date + timedelta(days=1), datetime.min.time()),
    )
    if args.country:
        current_query = current_query.where(fixtures.c.country == args.country)
    with engine.connect() as connection:
        scopes = connection.execute(scope_query).all()
        current_by_id = {row.fixture_id: row for row in connection.execute(current_query)}

    client = ApiFootballClient(api_key, ROOT / ".cache" / "api-football-refresh")
    changes: list[dict] = []
    pending_updates: list[tuple[int, dict]] = []
    provider_statuses: Counter[str] = Counter()
    for league_id, season in scopes:
        for item in client.fixtures_between(league_id, season, args.from_date.isoformat(), args.to_date.isoformat()):
            raw_fixture = item.get("fixture") or {}
            fixture_id = raw_fixture.get("id")
            if not fixture_id:
                continue
            provider_statuses[(raw_fixture.get("status") or {}).get("short") or "UNKNOWN"] += 1
            current = current_by_id.get(fixture_id)
            if current is None:
                continue
            kickoff = datetime.fromisoformat(raw_fixture["date"].replace("Z", "+00:00")).astimezone(timezone.utc)
            values = {
                "fixture_date": kickoff,
                "status": (raw_fixture.get("status") or {}).get("short"),
                "home_goals": (item.get("goals") or {}).get("home"),
                "away_goals": (item.get("goals") or {}).get("away"),
                "venue_name": (raw_fixture.get("venue") or {}).get("name"),
                "venue_city": (raw_fixture.get("venue") or {}).get("city"),
            }
            changed_fields = [key for key, value in values.items() if getattr(current, key) != value]
            if changed_fields:
                changes.append({
                    "fixture_id": fixture_id,
                    "league_id": league_id,
                    "before_status": current.status,
                    "after_status": values["status"],
                    "before_fixture_date": current.fixture_date.isoformat(),
                    "after_fixture_date": kickoff.isoformat(),
                })
                pending_updates.append((fixture_id, values))

    if args.write and pending_updates:
        with engine.begin() as connection:
            for fixture_id, values in pending_updates:
                connection.execute(update(fixtures).where(fixtures.c.fixture_id == fixture_id).values(**values))

    with engine.connect() as connection:
        validation = {
            "past_ns_beyond_six_hours": connection.execute(text(
                "SELECT count(*) FROM fixtures WHERE fixture_date < now() - interval '6 hours' AND status = 'NS'"
            )).scalar_one(),
            "future_final": connection.execute(text(
                "SELECT count(*) FROM fixtures WHERE fixture_date > now() AND status IN ('FT', 'AET', 'PEN')"
            )).scalar_one(),
            "duplicate_natural_fixture_groups": connection.execute(text(
                "SELECT count(*) FROM (SELECT fixture_date, home_team_id, away_team_id FROM fixtures GROUP BY 1,2,3 HAVING count(*) > 1) duplicates"
            )).scalar_one(),
        }

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "write" if args.write else "dry-run",
        "from_date": args.from_date.isoformat(),
        "to_date": args.to_date.isoformat(),
        "country": args.country,
        "scopes": len(scopes),
        "provider_requests": client.requests_made,
        "provider_statuses": dict(sorted(provider_statuses.items())),
        "changed_existing_fixtures": len(changes),
        "changes": changes,
        "provider_failures": client.failures,
        "validation": validation,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "changes"}, indent=2))
    validation_failed = any(validation.values())
    return 2 if args.write and validation_failed else 1 if client.failures else 0


if __name__ == "__main__":
    sys.exit(main())
