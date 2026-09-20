"""CLI entry point for the canonical Matchgoer league importer."""

import argparse
import json
import logging
import os
from pathlib import Path

from config.leagues import COVERAGE_PROFILES, LeagueScope
from ingestion.api_football import ApiFootballClient
from ingestion.environment import ROOT, api_football_key, database_url
from ingestion.pipeline import TerraceTalkImporter
from backend.database_target import ExpectedDatabaseTarget

INGESTION_TARGET_TABLES = ("fixtures", "venues", "teams", "venue_names", "venue_provider_refs", "team_identity_overrides")
INGESTION_TARGET_COLUMNS = (("fixtures", "fixture_id"), ("fixtures", "home_team_id"), ("teams", "team_id"), ("team_identity_overrides", "provider_team_id"))


def normalise(value: str) -> str:
    return " ".join(value.lower().replace("-", " ").split())


def resolve_scope(client: ApiFootballClient, scope: LeagueScope) -> LeagueScope:
    if scope.league_id is not None:
        return scope
    candidates = client.leagues_by_country(scope.country)
    wanted = {normalise(scope.display_name), *(normalise(alias) for alias in scope.aliases)}
    matches = [item for item in candidates if normalise(item.get("league", {}).get("name", "")) in wanted]
    if len(matches) == 1:
        return LeagueScope(scope.country, matches[0]["league"]["id"], scope.display_name, scope.provider_season, scope.display_season, scope.aliases)
    return scope


def main() -> int:
    parser = argparse.ArgumentParser(description="Matchgoer API-Football importer")
    parser.add_argument("--profile", choices=sorted(COVERAGE_PROFILES))
    parser.add_argument("--country")
    parser.add_argument("--league-id", type=int)
    parser.add_argument("--league-name")
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--display-season")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--confirm-write", action="store_true")
    parser.add_argument("--expected-database", default=os.environ.get("MATCHGOER_EXPECTED_DATABASE"))
    parser.add_argument("--expected-schema", default=os.environ.get("MATCHGOER_EXPECTED_SCHEMA", "public"))
    parser.add_argument("--expected-environment", default=os.environ.get("MATCHGOER_EXPECTED_ENVIRONMENT"))
    parser.add_argument("--target-environment", default=os.environ.get("MATCHGOER_TARGET_ENVIRONMENT"))
    parser.add_argument("--no-geocode", action="store_true")
    parser.add_argument("--cache-dir", type=Path, default=ROOT / ".cache" / "api-football")
    parser.add_argument("--report-dir", type=Path, default=ROOT / "reports" / "ingestion")
    args = parser.parse_args()
    if args.write and not args.confirm_write:
        parser.error("--write requires --confirm-write after dry-run review")
    if args.write and (not args.expected_database or not args.expected_environment or not args.target_environment):
        parser.error("write requires expected database and environment target fingerprint")
    if not args.profile and not (args.country and args.league_id and args.league_name):
        parser.error("provide --profile or --country, --league-id, and --league-name")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    client = ApiFootballClient(api_football_key(), args.cache_dir)
    expected_target = ExpectedDatabaseTarget(
        args.expected_database, args.expected_schema, args.expected_environment,
        INGESTION_TARGET_TABLES, INGESTION_TARGET_COLUMNS,
    ) if args.write else None
    importer = TerraceTalkImporter(
        client, database_url(), expected_target=expected_target,
        target_environment=args.target_environment if args.write else None,
    )
    scopes = COVERAGE_PROFILES[args.profile] if args.profile else (LeagueScope(args.country, args.league_id, args.league_name, args.season, args.display_season or str(args.season)),)
    reports = []
    for configured in scopes:
        scope = resolve_scope(client, configured)
        if scope.league_id is None:
            report = {"country": scope.country, "league": scope.display_name, "league_id": None, "provider_season": scope.provider_season, "display_season": scope.display_season, "season_available": False, "failed_api_requests": ["Competition name did not resolve uniquely from /leagues?country."]}
        else:
            result = importer.write_import(scope, geocode=not args.no_geocode) if args.write else importer.dry_run(scope)
            report = result.serializable()
        reports.append(report)
        print(json.dumps(report, indent=2))
    args.report_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{'write' if args.write else 'dry-run'}-{args.profile or args.league_id}-{args.season}.json"
    (args.report_dir / filename).write_text(json.dumps(reports, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
