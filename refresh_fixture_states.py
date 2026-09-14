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

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / "backend" / ".env")

RETRYABLE_STATUSES = frozenset({"NS", "TBD", "1H", "HT", "2H", "ET", "BT", "P", "SUSP", "INT", "PST"})
DURABLE_COMPLETED_STATUSES = frozenset({"FT", "AET", "PEN"})
TERMINAL_SPECIAL_STATUSES = frozenset({"CANC", "ABD", "AWD", "WO"})
TERMINAL_STATUSES = DURABLE_COMPLETED_STATUSES | TERMINAL_SPECIAL_STATUSES
ALLOWED_FIELDS = ("fixture_date", "status", "home_goals", "away_goals")
CLASSIFICATIONS = (
    "WOULD_UPDATE_TO_FINAL", "WOULD_UPDATE_RESCHEDULED", "WOULD_UPDATE_OTHER_ALLOWED_STATE",
    "PROVIDER_STILL_UNRESOLVED", "NO_CHANGE", "IDENTITY_MISMATCH", "PROVIDER_MISSING",
    "PROVIDER_DUPLICATE", "TERMINAL_CONFLICT_REVIEW",
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Reconcile existing Matchgoer fixtures from API-Football")
    result.add_argument("--nightly", action="store_true")
    result.add_argument("--lookback-days", type=int, default=30)
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


def classify_candidate(candidate: Any, provider_rows: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any] | None]:
    result = manifest_base(candidate)
    if not provider_rows:
        result.update(classification="PROVIDER_MISSING", reason="Provider returned no row for requested fixture ID")
        return result, None
    if len(provider_rows) != 1:
        result.update(classification="PROVIDER_DUPLICATE", reason=f"Provider returned {len(provider_rows)} rows for requested fixture ID")
        return result, None
    item = provider_rows[0]
    values = provider_values(item)
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
    changed = [field for field in ALLOWED_FIELDS if (utc_datetime(getattr(candidate, field)) if field == "fixture_date" else getattr(candidate, field)) != values[field]]
    result["proposed_changed_fields"] = changed
    if candidate.status in TERMINAL_STATUSES and changed:
        result.update(classification="TERMINAL_CONFLICT_REVIEW", reason="Stored terminal fixture disagrees with provider")
        return result, None
    if values["status"] not in RETRYABLE_STATUSES | TERMINAL_STATUSES:
        result.update(classification="PROVIDER_STILL_UNRESOLVED", reason=f"Unsupported provider status {values['status']!r}; no mutation proposed", proposed_changed_fields=[])
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


def validate_plan(candidates: list[Any], manifest: list[dict[str, Any]], updates: dict[int, dict[str, Any]], natural_keys: dict[tuple[Any, int, int], set[int]]) -> dict[str, Any]:
    ids = [row.fixture_id for row in candidates]
    problems: list[str] = []
    if len(ids) != len(set(ids)):
        problems.append("candidate IDs are not unique")
    if len(manifest) != len(ids) or {row["fixture_id"] for row in manifest} != set(ids):
        problems.append("manifest does not cover the frozen candidate set")
    by_id = {row.fixture_id: row for row in candidates}
    for fixture_id, values in updates.items():
        if fixture_id not in by_id:
            problems.append(f"update {fixture_id} is outside frozen candidates")
            continue
        if set(values) != set(ALLOWED_FIELDS):
            problems.append(f"update {fixture_id} contains fields outside allowed scope")
        row = by_id[fixture_id]
        owners = natural_keys.get((values["fixture_date"], row.home_team_id, row.away_team_id), set())
        conflicts = owners - {fixture_id}
        if conflicts:
            problems.append(f"update {fixture_id} would duplicate natural key owned by {sorted(conflicts)}")
        provider_state = next(item for item in manifest if item["fixture_id"] == fixture_id)
        if any(values[field] != (utc_datetime(provider_state[f"provider_{field}"]) if field == "fixture_date" else provider_state[f"provider_{field}"]) for field in ALLOWED_FIELDS):
            problems.append(f"update {fixture_id} differs from its provider manifest")
    return {"passed": not problems, "problems": problems, "frozen_candidate_count": len(ids), "planned_update_count": len(updates), "idempotent": not problems}


def main() -> int:
    args = parser().parse_args()
    if not args.nightly:
        raise SystemExit("Use --nightly for bounded reconciliation")
    if args.lookback_days < 1:
        raise SystemExit("--lookback-days must be positive")
    if args.write and not args.confirm_write:
        raise SystemExit("--write requires --confirm-write after reviewing a dry run")
    database_url = os.getenv("DATABASE_URL")
    api_key = os.getenv("API_FOOTBALL_KEY") or os.getenv("API_SPORTS_KEY")
    if not database_url or not api_key:
        raise SystemExit("DATABASE_URL and API_FOOTBALL_KEY/API_SPORTS_KEY must be configured")
    engine = create_engine(database_url)
    fixtures = Table("fixtures", MetaData(), autoload_with=engine)
    cutoff_day = args.as_of or datetime.now(timezone.utc).date()
    cutoff = datetime.combine(cutoff_day, datetime.min.time(), tzinfo=timezone.utc)
    start = cutoff - timedelta(days=args.lookback_days)
    query = select(
        fixtures.c.fixture_id, fixtures.c.fixture_date, fixtures.c.status, fixtures.c.home_goals, fixtures.c.away_goals,
        fixtures.c.league_id, fixtures.c.season, fixtures.c.home_team_id, fixtures.c.away_team_id, fixtures.c.home_team, fixtures.c.away_team,
    ).where(fixtures.c.fixture_date >= start, fixtures.c.fixture_date < cutoff, fixtures.c.status.in_(sorted(RETRYABLE_STATUSES)))
    if args.country:
        query = query.where(fixtures.c.country == args.country)
    with engine.connect() as connection:
        candidates = list(connection.execute(query.order_by(fixtures.c.fixture_id)))
        natural_rows = connection.execute(select(fixtures.c.fixture_id, fixtures.c.fixture_date, fixtures.c.home_team_id, fixtures.c.away_team_id)).all()
        older_rows = connection.execute(
            select(fixtures.c.status).where(fixtures.c.fixture_date < start, fixtures.c.status.in_(sorted(RETRYABLE_STATUSES)))
        ).all()
    natural_keys: dict[tuple[Any, int, int], set[int]] = {}
    for row in natural_rows:
        natural_keys.setdefault((utc_datetime(row.fixture_date), row.home_team_id, row.away_team_id), set()).add(row.fixture_id)
    client = ApiFootballClient(api_key, ROOT / ".cache" / "api-football-refresh")
    responses: dict[int, list[dict[str, Any]]] = {row.fixture_id: [] for row in candidates}
    for batch in chunks(list(responses)):
        try:
            items = client.fixtures_by_ids(batch)
        except RuntimeError:
            continue
        for item in items:
            fixture_id = (item.get("fixture") or {}).get("id")
            if fixture_id in responses:
                responses[fixture_id].append(item)
    manifest, updates = [], {}
    for candidate in candidates:
        item, values = classify_candidate(candidate, responses[candidate.fixture_id])
        manifest.append(item)
        if values is not None:
            updates[candidate.fixture_id] = values
    validation = validate_plan(candidates, manifest, updates, natural_keys)
    if args.write:
        if client.failures or not validation["passed"]:
            raise SystemExit("Refusing write because provider fetching or bounded validation failed")
        by_id = {row.fixture_id: row for row in candidates}
        with engine.begin() as connection:
            for fixture_id, values in updates.items():
                before = by_id[fixture_id]
                guard = and_(fixtures.c.fixture_id == fixture_id, fixtures.c.fixture_date == before.fixture_date, fixtures.c.status == before.status,
                             fixtures.c.home_goals.is_(None) if before.home_goals is None else fixtures.c.home_goals == before.home_goals,
                             fixtures.c.away_goals.is_(None) if before.away_goals is None else fixtures.c.away_goals == before.away_goals)
                if connection.execute(update(fixtures).where(guard).values(**values)).rowcount != 1:
                    raise RuntimeError(f"Concurrent fixture change detected for {fixture_id}; transaction rolled back")
    counts = Counter(row["classification"] for row in manifest)
    field_counts = Counter(field for row in manifest if row["fixture_id"] in updates for field in row["proposed_changed_fields"])
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(), "mode": "write" if args.write else "dry-run", "policy": "nightly",
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
    return 1 if client.failures or not validation["passed"] else 0


if __name__ == "__main__":
    sys.exit(main())
