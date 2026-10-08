"""Controlled nightly reconciliation of existing fixture lifecycle data."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import date, datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys
from typing import Any, Iterable

from dotenv import load_dotenv
from sqlalchemy import MetaData, Table, and_, create_engine, select, update

from ingestion.api_football import ApiFootballClient
from ingestion.pipeline import TerraceTalkImporter

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / "backend" / ".env")

RETRYABLE_STATUSES = frozenset({"NS", "TBD", "1H", "HT", "2H", "ET", "BT", "P", "SUSP", "INT", "PST"})
DURABLE_COMPLETED_STATUSES = frozenset({"FT", "AET", "PEN"})
TERMINAL_SPECIAL_STATUSES = frozenset({"CANC", "ABD", "AWD", "WO"})
TERMINAL_STATUSES = DURABLE_COMPLETED_STATUSES | TERMINAL_SPECIAL_STATUSES
ALLOWED_FIELDS = ("fixture_date", "status", "home_goals", "away_goals", "venue_id")
HOLD_CONFIG = ROOT / "config" / "fixture_reconciliation_holds.json"
REVIEW_HOLDS = {int(row["fixture_id"]): row for row in json.loads(HOLD_CONFIG.read_text(encoding="utf-8"))["holds"] if row["review_status"] != "RELEASED_AFTER_MANUAL_REVIEW"}
CLASSIFICATIONS = (
    "WOULD_UPDATE_TO_FINAL", "WOULD_UPDATE_RESCHEDULED", "WOULD_UPDATE_OTHER_ALLOWED_STATE",
    "PROVIDER_STILL_UNRESOLVED", "NO_CHANGE", "IDENTITY_MISMATCH", "PROVIDER_MISSING",
    "PROVIDER_DUPLICATE", "TERMINAL_CONFLICT_REVIEW", "PROVIDER_MALFORMED", "MANUAL_REVIEW_HOLD",
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Reconcile existing Matchgoer fixtures from API-Football")
    result.add_argument("--nightly", action="store_true")
    result.add_argument("--lookback-days", type=int, default=30)
    result.add_argument("--lookahead-days", type=int, default=30)
    result.add_argument("--max-requests", type=int, default=int(os.getenv("FIXTURE_REFRESH_MAX_REQUESTS", "750")))
    result.add_argument("--as-of", type=date.fromisoformat, help="UTC cutoff date; defaults to today UTC")
    result.add_argument("--country")
    result.add_argument("--write", action="store_true")
    result.add_argument("--confirm-write", action="store_true")
    result.add_argument("--report", type=Path, default=ROOT / "reports" / "fixture-refresh-latest.json")
    return result


def chunks(values: list[int], size: int = 20) -> Iterable[list[int]]:
    for start in range(0, len(values), size):
        yield values[start:start + size]


def utc_datetime(value: str | datetime) -> datetime:
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def expanded_refresh_enabled():
    value = os.getenv("ENABLE_EXPANDED_FIXTURE_REFRESH", "false").strip().lower()
    if value not in {"true", "false", ""}:
        raise SystemExit("ENABLE_EXPANDED_FIXTURE_REFRESH must be TRUE or FALSE; refusing execution")
    return value == "true"


def refresh_window(day, lookback=30, lookahead=30):
    today = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc)
    return today - timedelta(days=lookback), today + timedelta(days=lookahead + 1)


def resolve_venue(candidate, item, venues, refs, aliases):
    """Read-only mapping: no speculative venues or canonical metadata changes."""
    old = getattr(candidate, "venue_id", None)
    raw = (item.get("fixture") or {}).get("venue") or {}
    pid = raw.get("id")
    if not pid:
        return old, "MISSING"
    ids = {r["venue_id"] for r in refs if r["provider"] == "api_football" and r["provider_venue_id"] == pid and not r.get("valid_to")}
    ids.update(v["venue_id"] for v in venues if v.get("provider_venue_id") == pid)
    if len(ids) != 1:
        return old, "AMBIGUOUS" if ids else "UNKNOWN"
    target = next((v for v in venues if v["venue_id"] in ids), None)
    if target is None:
        return old, "UNKNOWN"
    normalize = TerraceTalkImporter._normalize_venue_identity_name
    names = {normalize(target.get("name") or "")}
    names.update(normalize(a["name"]) for a in aliases if a["venue_id"] == target["venue_id"] and not a.get("valid_to"))
    if not raw.get("name") or normalize(raw["name"]) not in names:
        return old, "DISPUTED"
    if raw.get("city") and target.get("city") and normalize(raw["city"]) != normalize(target["city"]):
        return old, "DISPUTED"
    if getattr(candidate, "country", None) and target.get("country") and normalize(candidate.country) != normalize(target["country"]):
        return old, "DISPUTED"
    if target.get("latitude") is None or target.get("longitude") is None:
        return old, "UNRESOLVED_DIRECTIONS"
    return target["venue_id"], "MATCHED"


def provider_values(item: dict[str, Any]) -> dict[str, Any]:
    raw = item.get("fixture") or {}
    return {
        "fixture_date": utc_datetime(raw["date"]),
        "status": (raw.get("status") or {}).get("short"),
        "home_goals": (item.get("goals") or {}).get("home"),
        "away_goals": (item.get("goals") or {}).get("away"),
    }


def provider_identity(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "fixture_id": (item.get("fixture") or {}).get("id"),
        "league_id": (item.get("league") or {}).get("id"),
        "season": (item.get("league") or {}).get("season"),
        "home_team_id": ((item.get("teams") or {}).get("home") or {}).get("id"),
        "away_team_id": ((item.get("teams") or {}).get("away") or {}).get("id"),
    }


def manifest_base(candidate: Any) -> dict[str, Any]:
    return {
        "fixture_id": candidate.fixture_id, "league_id": candidate.league_id, "season": candidate.season,
        "home_team": candidate.home_team, "away_team": candidate.away_team,
        "stored_fixture_date": utc_datetime(candidate.fixture_date).isoformat(), "provider_fixture_date": None,
        "stored_status": candidate.status, "provider_status": None,
        "stored_home_goals": candidate.home_goals, "stored_away_goals": candidate.away_goals,
        "provider_home_goals": None, "provider_away_goals": None,
        "proposed_changed_fields": [], "identity_check_result": "NOT_CHECKED",
    }


def classify_candidate(candidate: Any, provider_rows: list[dict[str, Any]], venue_context=None, expanded=True) -> tuple[dict[str, Any], dict[str, Any] | None]:
    result = manifest_base(candidate)
    if candidate.fixture_id in REVIEW_HOLDS:
        result["manual_hold"] = REVIEW_HOLDS[candidate.fixture_id]
    if not provider_rows:
        result.update(classification="PROVIDER_MISSING", reason="Provider returned no row for requested fixture ID")
        return result, None
    if len(provider_rows) != 1:
        result.update(classification="PROVIDER_DUPLICATE", reason=f"Provider returned {len(provider_rows)} rows for requested fixture ID")
        return result, None
    item = provider_rows[0]
    try:
        values = provider_values(item)
        identity = provider_identity(item)
    except (KeyError, ValueError, TypeError, AttributeError):
        result.update(classification="PROVIDER_MALFORMED", reason="Malformed provider record")
        return result, None
    try:
        if any(value is not None and (type(value) is not int or value < 0) for value in (values["home_goals"], values["away_goals"])):
            raise ValueError("Invalid goal values")
        values["venue_id"], venue_result = resolve_venue(candidate, item, *venue_context) if expanded and venue_context else (getattr(candidate, "venue_id", None), "DISABLED" if not expanded else "NOT_CHECKED")
    except (KeyError, ValueError, TypeError, AttributeError):
        result.update(classification="PROVIDER_MALFORMED", reason="Malformed provider goals or venue")
        return result, None
    result.update(stored_venue_id=getattr(candidate, "venue_id", None), provider_venue_id=values["venue_id"], venue_mapping=venue_result, raw_provider_venue=(item.get("fixture") or {}).get("venue"))
    result.update(
        provider_fixture_date=values["fixture_date"].isoformat(), provider_status=values["status"],
        provider_home_goals=values["home_goals"], provider_away_goals=values["away_goals"],
    )
    identity = provider_identity(item)
    expected = {key: getattr(candidate, key) for key in identity}
    mismatches = {key: {"stored": expected[key], "provider": identity[key]} for key in identity if expected[key] != identity[key]}
    if mismatches:
        result.update(identity_check_result="FAIL", classification="IDENTITY_MISMATCH", reason="Provider identity did not match stored fixture", identity_mismatches=mismatches)
        return result, None
    result["identity_check_result"] = "PASS"
    if candidate.fixture_id in REVIEW_HOLDS:
        result.update(classification="MANUAL_REVIEW_HOLD", reason=REVIEW_HOLDS[candidate.fixture_id]["reason"], manual_hold=REVIEW_HOLDS[candidate.fixture_id])
        return result, None
    if not expanded:
        values.pop("venue_id")
    changed = [field for field in values if (utc_datetime(getattr(candidate, field)) if field == "fixture_date" else getattr(candidate, field, None)) != values[field]]
    result["proposed_changed_fields"] = changed
    if candidate.status in TERMINAL_STATUSES and changed:
        result.update(classification="TERMINAL_CONFLICT_REVIEW", reason="Stored terminal fixture disagrees with provider")
        return result, None
    if values["status"] not in RETRYABLE_STATUSES | TERMINAL_STATUSES:
        result.update(classification="PROVIDER_MALFORMED", reason=f"Unsupported provider status {values['status']!r}; no mutation proposed", proposed_changed_fields=[])
        return result, None
    if candidate.status in TERMINAL_STATUSES:
        result.update(classification="NO_CHANGE", reason="Stored terminal fixture agrees with provider")
        return result, None
    if not changed:
        classification = "PROVIDER_STILL_UNRESOLVED" if values["status"] in RETRYABLE_STATUSES else "NO_CHANGE"
        result.update(classification=classification, reason="Provider remains unresolved" if classification == "PROVIDER_STILL_UNRESOLVED" else "Provider and stored state agree")
        return result, None
    if "fixture_date" in changed:
        classification, reason = "WOULD_UPDATE_RESCHEDULED", "Provider supplied a changed kickoff date"
    elif values["status"] in DURABLE_COMPLETED_STATUSES:
        classification, reason = "WOULD_UPDATE_TO_FINAL", "Provider supplied a durable completed state"
    else:
        classification, reason = "WOULD_UPDATE_OTHER_ALLOWED_STATE", "Provider supplied an allowed lifecycle change"
    result.update(classification=classification, reason=reason)
    return result, values


def validate_plan(candidates: list[Any], manifest: list[dict[str, Any]], updates: dict[int, dict[str, Any]], natural_keys: dict[tuple[Any, int, int], set[int]], expanded=True) -> dict[str, Any]:
    ids = [row.fixture_id for row in candidates]
    problems: list[str] = []
    if len(ids) != len(set(ids)):
        problems.append("candidate IDs are not unique")
    if len(manifest) != len(ids) or {row["fixture_id"] for row in manifest} != set(ids):
        problems.append("manifest does not cover the frozen candidate set")
    by_id = {row.fixture_id: row for row in candidates}
    proposed_keys = {}
    for fixture_id, values in updates.items():
        if fixture_id in REVIEW_HOLDS:
            problems.append(f"update {fixture_id} is explicitly held for manual review")
        if fixture_id not in by_id:
            problems.append(f"update {fixture_id} is outside frozen candidates")
            continue
        if set(values) != (set(ALLOWED_FIELDS) if expanded else set(ALLOWED_FIELDS) - {"venue_id"}):
            problems.append(f"update {fixture_id} contains fields outside allowed scope")
            continue
        row = by_id[fixture_id]
        proposed_key = (values["fixture_date"], row.home_team_id, row.away_team_id)
        if proposed_key in proposed_keys:
            problems.append(f"proposed updates {fixture_id} and {proposed_keys[proposed_key]} collide")
        proposed_keys[proposed_key] = fixture_id
        owners = natural_keys.get((values["fixture_date"], row.home_team_id, row.away_team_id), set())
        conflicts = owners - {fixture_id}
        if conflicts:
            problems.append(f"update {fixture_id} would duplicate natural key owned by {sorted(conflicts)}")
        provider_state = next(item for item in manifest if item["fixture_id"] == fixture_id)
        if any(values[field] != (utc_datetime(provider_state[f"provider_{field}"]) if field == "fixture_date" else provider_state[f"provider_{field}"]) for field in values):
            problems.append(f"update {fixture_id} differs from its provider manifest")
    return {"passed": not problems, "problems": problems, "frozen_candidate_count": len(ids), "planned_update_count": len(updates), "idempotent": not problems}


def fixture_snapshot(connection, fixtures):
    """Capture every column so excluded rows and editorial fields are protected."""
    rows = list(connection.execute(select(fixtures)).mappings())
    snapshot = {row["fixture_id"]: dict(row) for row in rows}
    for row in snapshot.values():
        if row["fixture_date"] is not None:
            row["fixture_date"] = utc_datetime(row["fixture_date"])
    if len(snapshot) != len(rows):
        raise RuntimeError("Duplicate fixture IDs during reconciliation")
    return snapshot


def reconcile_final_state(connection, fixtures, before, updates):
    after = fixture_snapshot(connection, fixtures)
    if set(after) != set(before):
        raise RuntimeError("Fixture insertion or deletion during reconciliation")
    changed = set()
    for fixture_id, original in before.items():
        expected = dict(original)
        expected.update(updates.get(fixture_id, {}))
        if after[fixture_id] != expected:
            raise RuntimeError(f"Unexpected final fixture state for {fixture_id}")
        if after[fixture_id] != original:
            changed.add(fixture_id)
    intended = {fixture_id for fixture_id, values in updates.items()
                if any(before[fixture_id][field] != value for field, value in values.items())}
    if changed != intended or set(updates) & set(REVIEW_HOLDS):
        raise RuntimeError("Updated fixture IDs differ from approved plan")


def main() -> int:
    args = parser().parse_args()
    expanded = expanded_refresh_enabled()
    if not args.nightly:
        raise SystemExit("Use --nightly for bounded reconciliation")
    if args.lookahead_days < 0 or args.max_requests < 1:
        raise SystemExit("lookahead must be nonnegative and max requests positive")
    if args.lookback_days < 1:
        raise SystemExit("--lookback-days must be positive")
    if args.write and not args.confirm_write:
        raise SystemExit("--write requires --confirm-write after reviewing a dry run")
    database_url = os.getenv("DATABASE_URL")
    api_key = os.getenv("API_FOOTBALL_KEY") or os.getenv("API_SPORTS_KEY")
    if not database_url or not api_key:
        raise SystemExit("DATABASE_URL and API_FOOTBALL_KEY/API_SPORTS_KEY must be configured")
    engine = create_engine(database_url, connect_args={} if args.write else {"options": "-c default_transaction_read_only=on"})
    fixtures = Table("fixtures", MetaData(), autoload_with=engine)
    cutoff_day = args.as_of or datetime.now(timezone.utc).date()
    cutoff = datetime.combine(cutoff_day, datetime.min.time(), tzinfo=timezone.utc)
    start, end = refresh_window(cutoff_day, args.lookback_days, args.lookahead_days)
    if not expanded:
        end = cutoff
    query = select(
        fixtures.c.fixture_id, fixtures.c.fixture_date, fixtures.c.status, fixtures.c.home_goals, fixtures.c.away_goals,
        fixtures.c.league_id, fixtures.c.season, fixtures.c.home_team_id, fixtures.c.away_team_id, fixtures.c.home_team, fixtures.c.away_team, fixtures.c.venue_id, fixtures.c.country,
    ).where(fixtures.c.fixture_date >= start, fixtures.c.fixture_date < end, fixtures.c.status.in_(sorted(RETRYABLE_STATUSES)))
    if args.country:
        query = query.where(fixtures.c.country == args.country)
    with engine.connect() as connection:
        candidates = list(connection.execute(query.order_by(fixtures.c.fixture_id)))
        venues = list(connection.execute(select(Table("venues", MetaData(), autoload_with=connection))).mappings()) if expanded else []
        refs = list(connection.execute(select(Table("venue_provider_refs", MetaData(), autoload_with=connection))).mappings()) if expanded else []
        aliases = list(connection.execute(select(Table("venue_names", MetaData(), autoload_with=connection))).mappings()) if expanded else []
        natural_rows = connection.execute(select(fixtures.c.fixture_id, fixtures.c.fixture_date, fixtures.c.home_team_id, fixtures.c.away_team_id)).all()
        older_rows = connection.execute(
            select(fixtures.c.status).where(fixtures.c.fixture_date < start, fixtures.c.status.in_(sorted(RETRYABLE_STATUSES)))
        ).all()
    natural_keys: dict[tuple[Any, int, int], set[int]] = {}
    for row in natural_rows:
        natural_keys.setdefault((utc_datetime(row.fixture_date), row.home_team_id, row.away_team_id), set()).add(row.fixture_id)
    client = ApiFootballClient(api_key, ROOT / ".cache" / "api-football-refresh")
    responses: dict[int, list[dict[str, Any]]] = {row.fixture_id: [] for row in candidates}
    budget_exceeded = (len(candidates) + 19) // 20 > args.max_requests
    for batch in ([] if budget_exceeded else chunks(list(responses))):
        try:
            items = client.fixtures_by_ids(batch)
        except (RuntimeError, ValueError, TypeError):
            continue
        for item in items:
            if not isinstance(item, dict):
                client.failures.append("Malformed response record")
                continue
            if not isinstance(item.get("fixture"), dict):
                client.failures.append("Malformed fixture envelope")
                continue
            fixture_id = item["fixture"].get("id")
            if fixture_id in responses:
                responses[fixture_id].append(item)
    manifest, updates = [], {}
    for candidate in candidates:
        item, values = classify_candidate(candidate, responses[candidate.fixture_id], (venues, refs, aliases), expanded=expanded)
        manifest.append(item)
        if values is not None:
            updates[candidate.fixture_id] = values
    validation = validate_plan(candidates, manifest, updates, natural_keys, expanded=expanded)
    if budget_exceeded:
        validation["passed"] = False
        validation["problems"].append("Request ceiling exceeded; no provider calls made")
    incomplete = any(row["venue_mapping"] not in {"MATCHED", "MISSING", "DISABLED"} for row in manifest if "venue_mapping" in row) or any(row["classification"] in {"PROVIDER_MISSING", "PROVIDER_DUPLICATE", "IDENTITY_MISMATCH", "PROVIDER_MALFORMED", "TERMINAL_CONFLICT_REVIEW", "MANUAL_REVIEW_HOLD"} for row in manifest)
    if args.write:
        if client.failures or not validation["passed"]:
            args.write = False  # Emit a failure receipt; never write an unsafe plan
    write_error = None
    if args.write:
        try:
                by_id = {row.fixture_id: row for row in candidates}
                with engine.begin() as connection:
                    # Serialize fixture writers until final readback and COMMIT.
                    if connection.dialect.name == "postgresql":
                        connection.exec_driver_sql("LOCK TABLE fixtures IN SHARE ROW EXCLUSIVE MODE")
                    preimage = fixture_snapshot(connection, fixtures)
                    for candidate in candidates:
                        current = preimage.get(candidate.fixture_id)
                        if current is None or any(current[field] != (utc_datetime(value) if field == "fixture_date" else value)
                                                  for field, value in candidate._mapping.items()):
                            raise RuntimeError(f"Fixture preimage changed for {candidate.fixture_id}")
                    for fixture_id, values in updates.items():
                        if fixture_id in REVIEW_HOLDS:
                            raise RuntimeError(f"Held fixture {fixture_id} cannot be written")
                        before = by_id[fixture_id]
                        guard = and_(fixtures.c.fixture_id == fixture_id, fixtures.c.fixture_date == before.fixture_date, fixtures.c.status == before.status,
                                     fixtures.c.home_team_id == before.home_team_id, fixtures.c.away_team_id == before.away_team_id,
                                     fixtures.c.league_id == before.league_id, fixtures.c.season == before.season,
                                     fixtures.c.venue_id.is_(None) if before.venue_id is None else fixtures.c.venue_id == before.venue_id,
                                     fixtures.c.home_goals.is_(None) if before.home_goals is None else fixtures.c.home_goals == before.home_goals,
                                     fixtures.c.away_goals.is_(None) if before.away_goals is None else fixtures.c.away_goals == before.away_goals)
                        if connection.execute(update(fixtures).where(guard).values(**values)).rowcount != 1:
                            raise RuntimeError(f"Concurrent fixture change detected for {fixture_id}; transaction rolled back")
                    reconcile_final_state(connection, fixtures, preimage, updates)
        except Exception as error:
            write_error = type(error).__name__
            args.write = False
    counts = Counter(row["classification"] for row in manifest)
    field_counts = Counter(field for row in manifest if row["fixture_id"] in updates for field in row["proposed_changed_fields"])
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(), "mode": "write" if args.write else "dry-run", "policy": "nightly",
        "expanded_refresh_enabled": expanded, "write_error": write_error, "complete": not incomplete and not client.failures and not write_error and validation["passed"], "window_start": start.isoformat(), "window_end_exclusive": end.isoformat(), "lookahead_days": args.lookahead_days if expanded else 0, "max_requests": args.max_requests,
        "as_of": cutoff_day.isoformat(), "lookback_days": args.lookback_days, "country": args.country,
        "candidates": len(candidates), "provider_requests": client.requests_made,
        "classification_counts": {key: counts[key] for key in CLASSIFICATIONS}, "proposed_fixture_rows_changed": len(updates),
        "field_change_counts": {field: field_counts[field] for field in ALLOWED_FIELDS},
        "expected_remaining_stale_cohort": sum(row["provider_status"] in RETRYABLE_STATUSES or row["classification"] in {"PROVIDER_MISSING", "PROVIDER_DUPLICATE", "IDENTITY_MISMATCH"} for row in manifest),
        "older_unresolved_outside_lookback": {"total": len(older_rows), "by_status": dict(sorted(Counter(row.status for row in older_rows).items()))},
        "provider_failures": client.failures, "validation": validation, "manifest": manifest,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "manifest"}, indent=2))
    return 1 if (expanded and incomplete) or write_error or client.failures or not validation["passed"] else 0


if __name__ == "__main__":
    sys.exit(main())
