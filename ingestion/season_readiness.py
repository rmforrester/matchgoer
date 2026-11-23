"""Manual, read-only season coverage report. Never imports or activates scopes."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy import MetaData, Table, create_engine, select

from config.leagues import (COVERAGE_PROFILES, NEW_FIXTURE_DISCOVERY_SCOPES,
                           SEASON_READINESS_WATCHLIST, SeasonWatch)
from ingestion.api_football import ApiFootballClient
from ingestion.coordinates import valid_coordinates
from ingestion.environment import ROOT, api_football_key, database_url
from ingestion.team_identity import (CanonicalTeam, TeamIdentityOverride,
                                     resolve_team_identity)
from ingestion.venue_identity import CanonicalVenues
from ingestion.pipeline import TerraceTalkImporter


class InventoryError(ValueError):
    pass


def fresh(client, endpoint, max_requests, **params):
    """Bypass stale caches; do not interpret partial inventories as absence."""
    if client.requests_made >= max_requests:
        raise InventoryError("REQUEST_BUDGET_EXHAUSTED")
    if client.requests_made and not client.highlights_quota_available():
        raise InventoryError("QUOTA_HEADROOM_UNAVAILABLE")
    rows = client.get(endpoint, use_cache=False, **params)
    payload = json.loads(client._cache_path(endpoint, params).read_text(encoding="utf-8"))
    if (not isinstance(rows, list) or payload.get("errors")
            or type(payload.get("results")) is not int or payload["results"] != len(rows)
            or payload.get("paging") != {"current": 1, "total": 1}):
        raise InventoryError("INCOMPLETE_PROVIDER_INVENTORY")
    return rows


def snapshot(engine, watchlist):
    """Read public canonical metadata only; database-enforced read-only session."""
    with engine.connect() as c:
        if c.dialect.name == "postgresql":
            c.exec_driver_sql("SET TRANSACTION READ ONLY")
        elif c.dialect.name == "sqlite":
            c.exec_driver_sql("PRAGMA query_only=ON")
        else:
            raise InventoryError("UNSUPPORTED_READ_ONLY_DATABASE")
        meta = MetaData()
        result = {}
        for name in ("fixtures", "teams", "venues", "venue_provider_refs", "venue_names",
                     "team_identity_overrides"):
            table = Table(name, meta, autoload_with=c)
            query = select(table)
            if name == "fixtures":
                query = query.where(table.c.league_id.in_([w.league_id for w in watchlist]))
            result[name] = [dict(r) for r in c.execute(query).mappings()]
        return result


def utc_day(value):
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise InventoryError("FIXTURE_TIMEZONE_MISSING")
    return parsed.astimezone(timezone.utc).date().isoformat()


def assess(watch, season, fixtures, roster, stored, continuity_evidence=()):
    teams = {r["team_id"]: CanonicalTeam(r["team_id"], r["team_name"]) for r in stored["teams"]}
    overrides = [TeamIdentityOverride(**{k: r[k] for k in (
        "provider", "provider_team_id", "league_id", "season", "canonical_team_id",
        "expected_provider_name", "review_status")}) for r in stored["team_identity_overrides"]]
    venues = {v["venue_id"]: v for v in stored["venues"]}
    identity = CanonicalVenues({v["venue_id"]: v["canonical_venue_id"] for v in venues.values()
                               if v.get("canonical_venue_id") is not None})
    normalize = TerraceTalkImporter._normalize_venue_identity_name
    existing = {r["fixture_id"]: r for r in stored["fixtures"]}
    prior = {r[k] for r in stored["fixtures"] if r["league_id"] == watch.league_id
             and r["season"] == watch.previous_season for k in ("home_team_id", "away_team_id")}
    names = {}
    for r in roster:
        tid, name = r["team"]["id"], r["team"]["name"]
        if type(tid) is not int or tid <= 0 or not name or tid in names:
            raise InventoryError("INVALID_ROSTER")
        names[tid] = name
    results, canonical_ids = {}, set()
    for tid, name in names.items():
        resolved = resolve_team_identity(provider="api_football", provider_team_id=tid,
            observed_name=name, league_id=watch.league_id, season=season,
            canonical_team=teams.get(tid), overrides=overrides)
        cid = resolved.canonical_team_id
        mapped = cid in teams if cid is not None else False
        if mapped:
            canonical_ids.add(cid)
        results[tid] = dict(provider_team_id=tid, canonical_team_id=cid if mapped else None,
            mapping=resolved.outcome.value,
            continuity="RETURNING" if mapped and cid in prior else "NEW_OR_PROMOTED_CANDIDATE")
    reviewed = []
    for item in continuity_evidence:
        if item.get("league_id") != watch.league_id or item.get("season") != season:
            continue
        if (item.get("classification") not in {"CONFIRMED_WITHDRAWN", "CONFIRMED_REBRAND", "CONFIRMED_SUCCESSOR"}
                or item.get("reviewed") is not True or not str(item.get("source", "")).startswith("https://")
                or type(item.get("canonical_team_id")) is not int
                or item["canonical_team_id"] not in teams
                or any(host in urlparse(item.get("source", "")).netloc.lower()
                       for host in ("api-football", "api-sports"))):
            raise InventoryError("UNSUPPORTED_CONTINUITY_EVIDENCE")
        reviewed.append(item)
    rows, seen = [], set()
    for f in fixtures:
        fid, league = f["fixture"]["id"], f["league"]
        if (type(fid) is not int or fid <= 0 or fid in seen
                or type(league["id"]) is not int or type(league["season"]) is not int
                or league["id"] != watch.league_id or league["season"] != season):
            raise InventoryError("FIXTURE_SCOPE_OR_DUPLICATE_CONFLICT")
        seen.add(fid)
        day = utc_day(f["fixture"]["date"])
        participants = [f["teams"][side]["id"] for side in ("home", "away")]
        if participants[0] == participants[1] or any(t not in names for t in participants):
            raise InventoryError("PARTICIPANT_INVENTORY_INCOMPLETE")
        old = existing.get(fid)
        expected = [results[t]["canonical_team_id"] for t in participants]
        if old and (old["league_id"] != watch.league_id or old["season"] != season
                    or expected != [old["home_team_id"], old["away_team_id"]]):
            raise InventoryError("EXISTING_FIXTURE_IDENTITY_CONFLICT")
        event = f["fixture"].get("venue") or {}
        pid = event.get("id")
        candidates = set()
        if type(pid) is int and pid > 0:
            candidates.update(identity.canonical(v["venue_id"]) for v in venues.values()
                              if v.get("provider_venue_id") == pid)
            candidates.update(identity.canonical(r["venue_id"]) for r in stored["venue_provider_refs"]
                              if r["provider"] == "api_football" and r["provider_venue_id"] == pid
                              and not r.get("valid_to"))
        elif pid is not None:
            raise InventoryError("INVALID_PROVIDER_VENUE_ID")
        vid = next(iter(candidates)) if len(candidates) == 1 else None
        venue = venues.get(vid)
        state = "MISSING_EVENT_VENUE_MAPPING" if not candidates else "AMBIGUOUS_EVENT_VENUE"
        if venue:
            allowed = {normalize(venue["name"])} | {
                normalize(n["name"]) for n in stored["venue_names"]
                if identity.canonical(n["venue_id"]) == vid}
            if ((event.get("name") and normalize(event["name"]) not in allowed)
                    or (event.get("city") and normalize(event["city"]) != normalize(venue.get("city") or ""))):
                state = "EVENT_VENUE_CONFLICT"
            elif not valid_coordinates(venue.get("latitude"), venue.get("longitude")) or (
                    float(venue["latitude"]), float(venue["longitude"])) == (0, 0):
                state = "KNOWN_VENUE_MISSING_COORDINATES"
            else:
                state = "GEOGRAPHICALLY_READY"
        old_venue = venues.get(identity.canonical(old["venue_id"])) if old and old.get("venue_id") else None
        rows.append(dict(fixture_id=fid, date=day, imported=old is not None,
            canonical_venue_id=vid, venue_readiness=state,
            hosted_geographically_ready=bool(old_venue and valid_coordinates(old_venue.get("latitude"), old_venue.get("longitude"))
                                            and (float(old_venue["latitude"]), float(old_venue["longitude"])) != (0, 0)),
            missing_team_mappings=[t for t in participants if results[t]["canonical_team_id"] is None]))
    return dict(provider_fixture_count=len(rows), imported_count=sum(r["imported"] for r in rows),
        missing_fixture_ids=[r["fixture_id"] for r in rows if not r["imported"]], fixtures=rows,
        venue_readiness_counts=dict(Counter(r["venue_readiness"] for r in rows)),
        missing_canonical_team_ids=sorted(tid for tid, r in results.items() if r["canonical_team_id"] is None),
        clubs=list(results.values()), prior_clubs_missing_from_provider=sorted(prior-canonical_ids),
        reviewed_continuity=reviewed,
        coverage_note="A complete API response is not proof of a complete season schedule; compare official expected counts before publication.",
        continuity_note="Absence is not closure. New/promoted labels require independent confirmation; no automatic rebrand/successor inference.")


def report(client, engine, watchlist=SEASON_READINESS_WATCHLIST, *, max_requests=13, continuity_evidence=()):
    if max_requests < 1:
        raise ValueError("max_requests must be positive")
    stored = snapshot(engine, watchlist)
    output = dict(observed_at=datetime.now(timezone.utc).isoformat(), read_only=True,
                  competitions=[], errors=[], requests=0)
    countries = {}
    for w in watchlist:
        row = dict(league_id=w.league_id, competition=w.display_name, previous_season=w.previous_season,
                   seasons=[], phases=[], status="PROVIDER_NEXT_SEASON_ABSENT")
        output["competitions"].append(row)
        try:
            if w.country not in countries:
                countries[w.country] = fresh(client, "/leagues", max_requests, country=w.country)
            matches = [x for x in countries[w.country] if x["league"]["id"] == w.league_id]
            if len(matches) != 1:
                raise InventoryError("COMPETITION_METADATA_MISSING_OR_AMBIGUOUS")
            advertised = matches[0]["seasons"]
            if any(type(s.get("year")) is not int for s in advertised):
                raise InventoryError("MALFORMED_SEASON_METADATA")
            # A provider can extend/reuse a key across a calendar transition.
            # Metadata bounds nominate candidates; actual payload dates establish observations.
            years = sorted({s["year"] for s in advertised if s["year"] > w.previous_season
                or any(s.get("start") and s.get("end") and s["start"] < end and s["end"] >= start
                       for _, start, end in w.phases)})
            row["advertised_seasons"] = sorted({s["year"] for s in advertised})
            for year in years:
                fixtures = fresh(client, "/fixtures", max_requests, league=w.league_id, season=year)
                entry = dict(provider_season=year, newly_available=year > w.previous_season,
                             discovery_active=any(s.league_id == w.league_id and s.provider_season == year
                                                  for s in NEW_FIXTURE_DISCOVERY_SCOPES))
                if not fixtures:
                    entry.update(status="ADVERTISED_NO_FIXTURES", provider_fixture_count=0)
                else:
                    roster = fresh(client, "/teams", max_requests, league=w.league_id, season=year)
                    entry.update(assess(w, year, fixtures, roster, stored, continuity_evidence), status="PUBLISHED_REVIEW_REQUIRED")
                row["seasons"].append(entry)
            if years:
                row["status"] = "REVIEW_REQUIRED"
            for label, start, end in w.phases:
                keys = [s["provider_season"] for s in row["seasons"]
                        if any(start <= f["date"] < end for f in s.get("fixtures", []))]
                row["phases"].append(dict(name=label, provider_keys_observed=keys,
                    status="DATES_OBSERVED_REVIEW_REQUIRED" if keys else "PROVIDER_PHASE_UNVERIFIED"))
            if w.phases:
                row["fixtures_outside_phase_windows"] = [f["fixture_id"] for s in row["seasons"]
                    for f in s.get("fixtures", []) if not any(start <= f["date"] < end for _, start, end in w.phases)]
            row["discovery_scopes"] = [s.provider_season for s in NEW_FIXTURE_DISCOVERY_SCOPES if s.league_id == w.league_id]
            row["discovery_alert"] = any(s.get("provider_fixture_count", 0) and not s["discovery_active"] for s in row["seasons"])
        except (RuntimeError, ValueError, KeyError, TypeError, OSError) as exc:
            row["status"] = "UNVERIFIED_PROVIDER_OR_IDENTITY_ERROR"
            output["errors"].append(dict(league_id=w.league_id, category=str(exc) if isinstance(exc, InventoryError) else type(exc).__name__))
            # Do not retry an unavailable country endpoint for every watched league.
            countries.setdefault(w.country, [])
    output.update(requests=client.requests_made, quota=client.quota)
    return output


def summary(data):
    lines = ["SEASON READINESS — read-only; no ingestion or activation"]
    for row in data["competitions"]:
        lines.append(f"{row['league_id']} {row['competition']}: {row['status']}")
        for s in row["seasons"]:
            lines.append(f"  {s['provider_season']}: {s['status']}; fixtures={s.get('provider_fixture_count', 'unknown')}; missing={len(s.get('missing_fixture_ids', []))}; discovery={s['discovery_active']}")
            if "venue_readiness_counts" in s:
                lines.append(f"  Venues: {s['venue_readiness_counts']}; unmapped teams={len(s['missing_canonical_team_ids'])}; prior clubs absent={len(s['prior_clubs_missing_from_provider'])}")
    lines.append(f"Provider requests: {data['requests']}; unverified scopes: {len(data['errors'])}")
    return "\n".join(lines)+"\n"


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--profile", choices=sorted((*COVERAGE_PROFILES,"global-discovery")))
    p.add_argument("--league-id", type=int, action="append", help="Bound a configured readiness profile to explicit competition IDs")
    p.add_argument("--max-requests", type=int, default=13)
    p.add_argument("--continuity-evidence", type=Path,
                   help="Optional reviewed independent-source attestations; never an identity mapping or write instruction")
    p.add_argument("--output", type=Path, default=ROOT/"reports/ingestion/season-readiness.json")
    args = p.parse_args(argv)
    watch = SEASON_READINESS_WATCHLIST
    if args.profile == "global-discovery":
        from ingestion.global_discovery import load_registry
        registry = load_registry()
        watch = tuple(SeasonWatch(s['country'],s['league_id'],s['display_name'],s['provider_season'])
            for s in registry['scopes'] if s['review_status']=='REVIEWED')
    elif args.profile:
        configured = COVERAGE_PROFILES[args.profile]
        if any(s.league_id is None for s in configured):
            p.error("Report watchlists require explicit provider competition IDs")
        watch = tuple(SeasonWatch(s.country, s.league_id, s.display_name, s.provider_season) for s in configured)
    if args.league_id:
        requested=set(args.league_id)
        watch=tuple(w for w in watch if w.league_id in requested)
        if {w.league_id for w in watch} != requested:
            p.error("League IDs must belong to the selected reviewed readiness profile")
    client = ApiFootballClient(api_football_key(), ROOT/".cache/api-football-season-readiness")
    e = create_engine(database_url(), connect_args={"options": "-c default_transaction_read_only=on", "connect_timeout": 15})
    try:
        evidence = json.loads(args.continuity_evidence.read_text(encoding="utf-8")) if args.continuity_evidence else []
        if not isinstance(evidence, list):
            p.error("continuity evidence must be a JSON list")
        data = report(client, e, watch, max_requests=args.max_requests, continuity_evidence=evidence)
    finally:
        e.dispose()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, indent=2)+"\n", encoding="utf-8")
    args.output.with_suffix(".txt").write_text(summary(data), encoding="utf-8")
    print(summary(data), end="")
    return 1 if data["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
