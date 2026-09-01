"""Read-only coordinate-enrichment audit for cached API-Football venues."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from sqlalchemy import MetaData, create_engine, select

from config.leagues import COVERAGE_PROFILES, LeagueScope
from ingest_leagues import resolve_scope
from ingestion.api_football import ApiFootballClient
from ingestion.coordinates import NominatimCoordinateEnricher, valid_coordinates
from ingestion.environment import ROOT, api_football_key, database_url
from ingestion.pipeline import TerraceTalkImporter


DEFAULT_PROFILES = ("england-pyramid", "usa-priority", "sweden-priority")
DEFAULT_CHECKPOINT = ROOT / ".cache" / "nominatim" / "coordinate-dry-run-2026.json"
DEFAULT_REPORT = ROOT / "reports" / "ingestion" / "coordinate-dry-run-2026.json"
TERMINAL_STATUSES = {"geocoded", "unresolved", "ambiguous", "error"}


def load_json(path: Path, default: Any) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def save_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def scopes_from_cohort_report(path: Path, provider_season: int) -> tuple[LeagueScope, ...]:
    payload = load_json(path, {})
    summary = payload.get("summary", payload)
    rows = [*summary.get("safe", []), *summary.get("partial", [])]
    if not rows:
        raise ValueError(f"No safe/partial league cohort found in {path}")
    scopes = tuple(
        LeagueScope(
            str(row["country"]), int(row["league_id"]), str(row["league"]),
            provider_season, str(row.get("display_season") or "2026/27"),
        )
        for row in rows
    )
    identifiers = [scope.league_id for scope in scopes]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("Cohort report contains duplicate league IDs")
    return scopes


def configured_scopes(profiles: Iterable[str]) -> tuple[LeagueScope, ...]:
    return tuple(scope for profile in profiles for scope in COVERAGE_PROFILES[profile])


def collect_cohort(client: ApiFootballClient, importer: TerraceTalkImporter, scopes: Iterable[LeagueScope]):
    venues: dict[int, dict[str, Any]] = {}
    league_venues: dict[str, set[int]] = defaultdict(set)
    fixture_counts: dict[str, Counter[int]] = defaultdict(Counter)
    labels: dict[str, tuple[str, str, int]] = {}

    for configured in scopes:
        scope = resolve_scope(client, configured)
        if scope.league_id is None:
            raise ValueError(f"League ID did not resolve for {scope.country} / {scope.display_name}")
        key = str(scope.league_id)
        labels[key] = (scope.country, scope.display_name, scope.league_id)
        teams, fixtures, available = importer._records(scope)
        if not available:
            raise ValueError(f"Provider season unavailable for league {scope.league_id}")
        home_team_venues = importer._home_team_venues(teams)
        for item in [*teams, *fixtures]:
            raw = item.get("venue") or (item.get("fixture") or {}).get("venue") or {}
            venue = importer._venue_record(raw, scope.country)
            if venue:
                provider_id = int(venue["provider_venue_id"])
                venues.setdefault(provider_id, venue)
                league_venues[key].add(provider_id)
        for item in fixtures:
            fixture = item.get("fixture") or {}
            provider_id = (fixture.get("venue") or {}).get("id")
            if provider_id is None:
                home_id = (item.get("teams", {}).get("home") or {}).get("id")
                provider_id = home_team_venues.get(home_id)
            if provider_id is not None:
                fixture_counts[key][int(provider_id)] += 1
    return venues, league_venues, fixture_counts, labels


def read_hosted_coordinates(engine, provider_ids: set[int]):
    """Read existing coordinates only; never opens a write transaction."""
    metadata = MetaData()
    metadata.reflect(engine, only=["venues"])
    venues = metadata.tables["venues"]
    coordinates: dict[int, tuple[float | None, float | None]] = {}
    if not provider_ids:
        return coordinates
    with engine.connect() as connection:
        rows = connection.execute(
            select(venues.c.provider_venue_id, venues.c.latitude, venues.c.longitude)
            .where(venues.c.provider_venue_id.in_(provider_ids))
        )
        coordinates = {
            int(row.provider_venue_id): (row.latitude, row.longitude)
            for row in rows if row.provider_venue_id is not None
        }
    return coordinates


def audit_missing_venues(
    venues: dict[int, dict[str, Any]],
    hosted_coordinates: dict[int, tuple[float | None, float | None]],
    checkpoint: dict[str, dict[str, Any]],
    checkpoint_path: Path,
    enricher: NominatimCoordinateEnricher,
    max_venues: int | None = None,
) -> tuple[dict[int, str], int]:
    states: dict[int, str] = {}
    processed = 0
    for provider_id, venue in venues.items():
        if valid_coordinates(*hosted_coordinates.get(provider_id, (None, None))):
            states[provider_id] = "database"
            continue
        cached = checkpoint.get(str(provider_id))
        cached_is_terminal = cached and (
            cached.get("status") in {"unresolved", "ambiguous"}
            or cached.get("status") == "geocoded"
            and valid_coordinates(cached.get("latitude"), cached.get("longitude"))
        )
        if cached_is_terminal:
            states[provider_id] = str(cached["status"])
            continue
        if max_venues is not None and processed >= max_venues:
            states[provider_id] = "not_attempted"
            continue
        result = enricher.enrich(venue, strict_uniqueness=True)
        all_queries_failed = bool(result.errors) and len(result.errors) >= result.queries_attempted
        status = "geocoded" if result.source else "ambiguous" if result.ambiguous else "error" if all_queries_failed else "unresolved"
        checkpoint[str(provider_id)] = {
            "status": status,
            "provider_venue_id": provider_id,
            "venue": venue,
            "latitude": result.latitude,
            "longitude": result.longitude,
            "source": result.source,
            "matched_label": getattr(result, "matched_label", None),
            "osm_type": getattr(result, "osm_type", None),
            "osm_id": getattr(result, "osm_id", None),
            "acceptance_reason": getattr(result, "acceptance_reason", None),
            "queries_attempted": result.queries_attempted,
            "errors": list(result.errors),
        }
        save_json_atomic(checkpoint_path, checkpoint)
        states[provider_id] = status
        processed += 1
    return states, processed


def build_report(
    venues, league_venues, cached_fixture_counts, labels, hosted_coordinates,
    checkpoint, states, processed,
):
    missing = {venue_id for venue_id in venues if not valid_coordinates(*hosted_coordinates.get(venue_id, (None, None)))}
    resolved = {venue_id for venue_id in missing if states.get(venue_id) == "geocoded"}
    errors = sum(len(checkpoint.get(str(venue_id), {}).get("errors", [])) for venue_id in missing)
    projected_unlocked = sum(
        cached_fixture_counts[key][venue_id]
        for key, ids in league_venues.items()
        for venue_id in ids & resolved
    )
    affected = []
    for key, ids in league_venues.items():
        country, league, league_id = labels[key]
        league_missing, league_resolved = ids & missing, ids & resolved
        if not league_missing:
            continue
        affected.append({
            "country": country, "league": league, "league_id": league_id,
            "missing_venues_considered": len(league_missing),
            "auto_resolved": len(league_resolved),
            "unresolved": sum(states.get(venue_id) in {"unresolved", "ambiguous"} for venue_id in league_missing),
            "projected_fixtures_unlocked": sum(cached_fixture_counts[key][venue_id] for venue_id in league_resolved),
        })
    greece_ids = set().union(*(ids for key, ids in league_venues.items() if labels[key][0] == "Greece"))
    greece_missing, greece_resolved = greece_ids & missing, greece_ids & resolved
    athens_ids = {
        venue_id for venue_id in greece_missing
        if any(
            token in str(venues[venue_id].get("city") or "").casefold()
            for token in ("athens", "athina", "piraeus")
        )
    }
    return {
        "mode": "read_only_coordinate_audit",
        "summary": {
            "total_cohort_venues": len(venues),
            "already_coordinate_complete": len(venues) - len(missing),
            "coordinate_null_venues_considered": len(missing),
            "processed_this_run": processed,
            "AUTO_RESOLVED": len(resolved),
            "UNRESOLVED": sum(states.get(venue_id) == "unresolved" for venue_id in missing),
            "AMBIGUOUS": sum(states.get(venue_id) == "ambiguous" for venue_id in missing),
            "NOT_ATTEMPTED": sum(states.get(venue_id) == "not_attempted" for venue_id in missing),
            "errors": errors,
            "projected_fixtures_unlocked": projected_unlocked,
        },
        "countries_leagues_affected": affected,
        "error_venues": [
            {
                "provider_venue_id": venue_id,
                "name": venues[venue_id].get("name"),
                "errors": checkpoint.get(str(venue_id), {}).get("errors", []),
            }
            for venue_id in sorted(missing)
            if checkpoint.get(str(venue_id), {}).get("errors")
        ],
        "greece": {
            "total_missing_venues_considered": len(greece_missing),
            "resolved": len(greece_resolved),
            "unresolved": sum(states.get(venue_id) in {"unresolved", "ambiguous"} for venue_id in greece_missing),
            "projected_fixtures_unlocked": sum(
                cached_fixture_counts[key][venue_id]
                for key, ids in league_venues.items() if labels[key][0] == "Greece"
                for venue_id in ids & greece_resolved
            ),
        },
        "athens": {
            "missing_venues_considered": len(athens_ids),
            "resolved": len(athens_ids & resolved),
            "unresolved": sum(states.get(venue_id) in {"unresolved", "ambiguous"} for venue_id in athens_ids),
        },
        "safety": {"hosted_writes": 0, "identity_changes": 0},
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--cohort-report", type=Path)
    source.add_argument("--profiles", nargs="+", choices=sorted(COVERAGE_PROFILES), default=None)
    parser.add_argument("--provider-season", type=int, default=2026)
    parser.add_argument("--cache-dir", type=Path, default=ROOT / ".cache" / "api-football")
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--max-venues", type=int, help="Bounded wiring proof; omit for the full cohort")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    scopes = (
        scopes_from_cohort_report(args.cohort_report, args.provider_season)
        if args.cohort_report else configured_scopes(args.profiles or DEFAULT_PROFILES)
    )
    client = ApiFootballClient(api_football_key(), args.cache_dir)
    importer = TerraceTalkImporter(client, database_url())
    venues, league_venues, fixture_counts, labels = collect_cohort(client, importer, scopes)
    engine = create_engine(database_url(), connect_args={"connect_timeout": 10})
    hosted_coordinates = read_hosted_coordinates(engine, set(venues))
    checkpoint = load_json(args.checkpoint, {})
    states, processed = audit_missing_venues(
        venues, hosted_coordinates, checkpoint, args.checkpoint,
        NominatimCoordinateEnricher(), args.max_venues,
    )
    report = build_report(
        venues, league_venues, fixture_counts, labels, hosted_coordinates,
        checkpoint, states, processed,
    )
    save_json_atomic(args.report, report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
