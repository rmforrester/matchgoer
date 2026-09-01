"""Dry-run and apply only explicitly accepted coordinate results."""

from __future__ import annotations

import argparse
import json
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

from sqlalchemy import MetaData, create_engine, func, select

from ingestion.coordinates import valid_coordinates
from ingestion.environment import ROOT, database_url


DEFAULT_SOURCE = ROOT / "reports" / "ingestion" / "mvp-coordinate-gaps-2026.json"
DEFAULT_REPORT = ROOT / "reports" / "ingestion" / "write-reviewed-coordinates-2026.json"
DEFAULT_BASELINE = ROOT / "reports" / "ingestion" / "write-reviewed-coordinates-baseline-2026.json"
BREADTH_QA_WITHHELD_PROVIDER_VENUE_IDS = {774, 1759, 2524, 4006, 11595}
ATHENS_EXPECTED_READY = {19929, 19785, 7804}
ATHENS_EXPECTED_UNRESOLVED = {775, 20340}
COORDINATE_DB_QUANTUM = Decimal("0.000001")


def athens_expected_ready(provider_id: int, target_ids: set[int]) -> bool:
    return provider_id in ATHENS_EXPECTED_READY or provider_id in target_ids


def accepted_from_review_report(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "venue_id": int(item["venue"]["venue_id"]),
            "provider_venue_id": item["venue"].get("provider_venue_id"),
            "latitude": item["latitude"],
            "longitude": item["longitude"],
        }
        for item in payload["venues"] if item.get("status") == "accepted"
    ]


def accepted_from_checkpoint(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], list[int]]:
    accepted = []
    withheld = set(BREADTH_QA_WITHHELD_PROVIDER_VENUE_IDS)
    for raw_provider_id, result in payload.items():
        provider_id = int(raw_provider_id)
        if result.get("status") == "withheld":
            withheld.add(provider_id)
            continue
        if result.get("status") != "geocoded":
            continue
        if provider_id in withheld:
            continue
        if not valid_coordinates(result.get("latitude"), result.get("longitude")):
            raise ValueError(f"Invalid accepted coordinates for provider venue {provider_id}")
        accepted.append({
            "venue_id": None,
            "provider_venue_id": provider_id,
            "latitude": float(result["latitude"]),
            "longitude": float(result["longitude"]),
        })
    return accepted, sorted(withheld)


def resolve_provider_venue_ids(connection, venues, accepted: list[dict[str, Any]]) -> None:
    provider_ids = [item["provider_venue_id"] for item in accepted]
    if len(provider_ids) != len(set(provider_ids)):
        raise RuntimeError("Accepted input contains duplicate provider_venue_id values")
    rows = list(connection.execute(
        select(venues.c.venue_id, venues.c.provider_venue_id)
        .where(venues.c.provider_venue_id.in_(provider_ids))
    ))
    mapping: dict[int, list[int]] = {}
    for row in rows:
        mapping.setdefault(int(row.provider_venue_id), []).append(int(row.venue_id))
    invalid = {provider_id: mapping.get(provider_id, []) for provider_id in provider_ids if len(mapping.get(provider_id, [])) != 1}
    if invalid:
        raise RuntimeError(f"Provider venue IDs must resolve uniquely: {invalid}")
    for item in accepted:
        item["venue_id"] = mapping[item["provider_venue_id"]][0]


def build_plan(accepted: list[dict[str, Any]], rows: dict[int, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    missing = [item["venue_id"] for item in accepted if item["venue_id"] not in rows]
    if missing:
        raise RuntimeError(f"Audited venues no longer exist: {missing}")
    planned = [
        item for item in accepted
        if rows[item["venue_id"]].latitude is None or rows[item["venue_id"]].longitude is None
    ]
    preserved = [item for item in accepted if item not in planned]
    return planned, preserved


def enforce_expected_updates(expected: int | None, actual: int) -> None:
    if expected is not None and actual != expected:
        raise RuntimeError(f"Expected exactly {expected} planned coordinate updates, found {actual}; refusing write")


def coordinates_match(actual_lat, actual_lon, expected_lat, expected_lon) -> bool:
    return (
        valid_coordinates(actual_lat, actual_lon)
        and stored_coordinate(actual_lat) == stored_coordinate(expected_lat)
        and stored_coordinate(actual_lon) == stored_coordinate(expected_lon)
    )


def stored_coordinate(value: Any) -> Decimal:
    return Decimal(str(value)).quantize(COORDINATE_DB_QUANTUM, rounding=ROUND_HALF_UP)


def baseline_coordinate(value: Any) -> str | None:
    """Return a deterministic JSON-safe representation of a NUMERIC coordinate."""
    return None if value is None else format(stored_coordinate(value), "f")


def baseline_coordinate_matches(actual: Any, baseline: Any) -> bool:
    if actual is None or baseline is None:
        return actual is None and baseline is None
    return stored_coordinate(actual) == stored_coordinate(baseline)


def verify_expected_coordinate_rows(accepted, mapped) -> None:
    invalid_mappings = {
        item["provider_venue_id"]: len(mapped.get(item["provider_venue_id"], []))
        for item in accepted if len(mapped.get(item["provider_venue_id"], [])) != 1
    }
    if invalid_mappings:
        raise RuntimeError(f"Provider venue IDs must resolve uniquely: {invalid_mappings}")
    wrong = [
        item["provider_venue_id"] for item in accepted
        if not coordinates_match(
            mapped[item["provider_venue_id"]][0].latitude,
            mapped[item["provider_venue_id"]][0].longitude,
            item["latitude"], item["longitude"],
        )
    ]
    if wrong:
        raise RuntimeError(f"Missing or unexpected applied coordinates for provider venues: {wrong}")


def apply_coordinate_plan(engine, venues, planned, expected_updates: int) -> int:
    enforce_expected_updates(expected_updates, len(planned))
    with engine.begin() as connection:
        updated = 0
        for item in planned:
            result = connection.execute(
                venues.update().where(
                    venues.c.venue_id == item["venue_id"],
                    (venues.c.latitude.is_(None) | venues.c.longitude.is_(None)),
                ).values(latitude=item["latitude"], longitude=item["longitude"])
            )
            updated += result.rowcount
        if updated != len(planned):
            raise RuntimeError(f"Expected {len(planned)} updates, got {updated}; rolling back")
    return updated


def load_cohort_leagues(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    summary = payload.get("summary", payload)
    rows = [*summary.get("safe", []), *summary.get("partial", [])]
    if not rows:
        raise RuntimeError(f"No breadth cohort leagues found in {path}")
    ids = [int(row["league_id"]) for row in rows]
    if len(ids) != len(set(ids)):
        raise RuntimeError("Breadth cohort contains duplicate league IDs")
    return rows


def capture_baseline(connection, venues, planned, withheld: list[int], path: Path) -> dict[str, Any]:
    planned_ids = {item["provider_venue_id"] for item in planned}
    provider_ids = sorted(set(
        [item["provider_venue_id"] for item in planned]
        + withheld + list(ATHENS_EXPECTED_READY | ATHENS_EXPECTED_UNRESOLVED)
    ))
    rows = list(connection.execute(
        select(
            venues.c.venue_id, venues.c.provider_venue_id, venues.c.name,
            venues.c.city, venues.c.country, venues.c.latitude, venues.c.longitude,
        ).where(venues.c.provider_venue_id.in_(provider_ids))
    ))
    payload = {
        "planned_provider_venue_ids": sorted(item["provider_venue_id"] for item in planned),
        "target_rows": {
            str(row.provider_venue_id): {
                "venue_id": int(row.venue_id), "name": row.name, "city": row.city,
                "country": row.country,
                "latitude": baseline_coordinate(row.latitude),
                "longitude": baseline_coordinate(row.longitude),
            }
            for row in rows
        },
        "venue_row_count": int(connection.execute(select(func.count()).select_from(venues)).scalar_one()),
    }
    mapped = {int(row.provider_venue_id): row for row in rows}
    missing = [provider_id for provider_id in provider_ids if provider_id not in mapped]
    if missing:
        raise RuntimeError(f"Baseline provider venues do not resolve uniquely: {missing}")
    unexpected_ready = [
        provider_id for provider_id in ATHENS_EXPECTED_UNRESOLVED
        if provider_id not in planned_ids
        if valid_coordinates(mapped[provider_id].latitude, mapped[provider_id].longitude)
    ]
    if unexpected_ready:
        raise RuntimeError(f"Expected unresolved Athens/Piraeus venues are already coordinate-ready: {unexpected_ready}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return payload


def reconcile(connection, venues, fixtures, accepted, withheld, baseline, cohort_rows) -> dict[str, Any]:
    provider_ids = [item["provider_venue_id"] for item in accepted]
    queried_provider_ids = sorted(set(
        provider_ids + withheld + list(ATHENS_EXPECTED_READY | ATHENS_EXPECTED_UNRESOLVED)
    ))
    rows = list(connection.execute(
        select(
            venues.c.venue_id, venues.c.provider_venue_id, venues.c.name,
            venues.c.city, venues.c.country, venues.c.latitude, venues.c.longitude,
        ).where(venues.c.provider_venue_id.in_(queried_provider_ids))
    ))
    mapped: dict[int, list[Any]] = {}
    for row in rows:
        mapped.setdefault(int(row.provider_venue_id), []).append(row)
    verify_expected_coordinate_rows(accepted, mapped)

    baseline_rows = baseline.get("target_rows", {})
    if set(baseline.get("planned_provider_venue_ids", [])) != set(provider_ids):
        raise RuntimeError("Applied provider venue IDs do not match the captured pre-write baseline")
    identity_changes = []
    for provider_id in queried_provider_ids:
        before = baseline_rows.get(str(provider_id))
        current = mapped.get(provider_id, [])
        if before is None or len(current) != 1:
            raise RuntimeError(f"Cannot reconcile baseline provider venue {provider_id}")
        row = current[0]
        if any(getattr(row, field) != before[field] for field in ("venue_id", "name", "city", "country")):
            identity_changes.append(provider_id)
    if identity_changes:
        raise RuntimeError(f"Venue identity fields changed: {identity_changes}")
    changed_outside_targets = []
    for provider_id in withheld:
        before = baseline_rows.get(str(provider_id))
        current = mapped.get(provider_id, [])
        if before is None or len(current) != 1:
            raise RuntimeError(f"Cannot reconcile withheld provider venue {provider_id}")
        row = current[0]
        if (
            not baseline_coordinate_matches(row.latitude, before["latitude"])
            or not baseline_coordinate_matches(row.longitude, before["longitude"])
        ):
            changed_outside_targets.append(provider_id)
    if changed_outside_targets:
        raise RuntimeError(f"Withheld provider venues changed: {changed_outside_targets}")
    current_count = int(connection.execute(select(func.count()).select_from(venues)).scalar_one())
    if current_count != baseline["venue_row_count"]:
        raise RuntimeError("Venue row count changed; inserts/deletes cannot be reconciled")

    target_ids = set(provider_ids)
    updated_by_country: dict[str, int] = {}
    for provider_id in target_ids:
        country = str(mapped[provider_id][0].country or "Unknown")
        updated_by_country[country] = updated_by_country.get(country, 0) + 1

    league_ids = [int(row["league_id"]) for row in cohort_rows]
    coverage_rows = connection.execute(
        select(
            fixtures.c.country, fixtures.c.league_id, fixtures.c.league_name,
            func.count().label("fixtures"),
            func.count().filter(
                venues.c.latitude.is_not(None), venues.c.longitude.is_not(None),
                venues.c.latitude.between(-90, 90), venues.c.longitude.between(-180, 180),
            ).label("location_discoverable"),
        ).select_from(fixtures.outerjoin(venues, fixtures.c.venue_id == venues.c.venue_id))
        .where(fixtures.c.league_id.in_(league_ids), fixtures.c.season == 2026)
        .group_by(fixtures.c.country, fixtures.c.league_id, fixtures.c.league_name)
        .order_by(fixtures.c.country, fixtures.c.league_id)
    )
    coverage = [
        {
            "country": row.country, "league": row.league_name, "league_id": int(row.league_id),
            "fixtures": int(row.fixtures), "location_discoverable_fixtures": int(row.location_discoverable),
            "location_discoverable_percent": round(100 * int(row.location_discoverable) / int(row.fixtures), 1),
        }
        for row in coverage_rows
    ]
    athens = {}
    for provider_id in sorted(ATHENS_EXPECTED_READY | ATHENS_EXPECTED_UNRESOLVED):
        current = mapped.get(provider_id, [])
        if len(current) != 1:
            raise RuntimeError(f"Athens/Piraeus provider venue {provider_id} does not resolve uniquely")
        row = current[0]
        ready = valid_coordinates(row.latitude, row.longitude)
        expected_ready = athens_expected_ready(provider_id, target_ids)
        if ready != expected_ready:
            raise RuntimeError(f"Unexpected Athens/Piraeus coordinate state for provider venue {provider_id}")
        athens[str(provider_id)] = {"name": row.name, "coordinate_ready": ready}
    return {
        "status": "PASS", "intended_coordinates_verified": len(accepted),
        "withheld_provider_venue_ids_unchanged": sorted(withheld),
        "venue_inserts": 0, "venue_deletes": 0, "identity_changes": 0,
        "updated_coordinate_count_by_country": dict(sorted(updated_by_country.items())),
        "breadth_country_fixture_coverage": coverage, "athens_piraeus": athens,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--source-kind", choices=("review-report", "provider-checkpoint"), default="review-report")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--cohort-report", type=Path)
    parser.add_argument("--expect-updates", type=int)
    parser.add_argument("--reconcile", action="store_true")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--confirm-write", action="store_true")
    args = parser.parse_args()
    if args.write and not args.confirm_write:
        parser.error("--write requires --confirm-write")
    if args.write and args.expect_updates is None:
        parser.error("--write requires --expect-updates")
    if args.reconcile and args.write:
        parser.error("--reconcile and --write are mutually exclusive")
    if args.reconcile and not args.cohort_report:
        parser.error("--reconcile requires --cohort-report")
    return args


def main() -> int:
    args = parse_args()
    payload = json.loads(args.source.read_text(encoding="utf-8"))
    if args.source_kind == "provider-checkpoint":
        accepted, withheld = accepted_from_checkpoint(payload)
    else:
        accepted, withheld = accepted_from_review_report(payload), []

    engine = create_engine(database_url(), connect_args={"connect_timeout": 10})
    metadata = MetaData()
    metadata.reflect(engine, only=["venues", "fixtures"] if args.reconcile else ["venues"])
    venues = metadata.tables["venues"]
    with engine.connect() as connection:
        if args.source_kind == "provider-checkpoint":
            resolve_provider_venue_ids(connection, venues, accepted)
        rows = {
            int(row.venue_id): row
            for row in connection.execute(
                select(venues.c.venue_id, venues.c.latitude, venues.c.longitude)
                .where(venues.c.venue_id.in_([item["venue_id"] for item in accepted]))
            )
        }
    planned, preserved = build_plan(accepted, rows)
    if args.reconcile:
        baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
        enforce_expected_updates(args.expect_updates, len(accepted))
        with engine.connect() as connection:
            report = reconcile(
                connection, venues, metadata.tables["fixtures"], accepted, withheld,
                baseline, load_cohort_leagues(args.cohort_report),
            )
        report.update({"source": str(args.source), "baseline": str(args.baseline), "written": False})
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0
    report = {
        "source": str(args.source),
        "source_kind": args.source_kind,
        "accepted_coordinates": len(accepted),
        "qa_withheld_provider_venue_ids": withheld,
        "planned_coordinate_updates": len(planned),
        "already_valid_preserved": len(preserved),
        "written": False,
        "venue_ids": [item["venue_id"] for item in planned],
        "provider_venue_ids": [item["provider_venue_id"] for item in planned],
        "inserts": 0,
        "deletes": 0,
        "identity_changes": 0,
    }
    if args.write:
        enforce_expected_updates(args.expect_updates, len(planned))
        with engine.connect() as connection:
            capture_baseline(connection, venues, planned, withheld, args.baseline)
        updated = apply_coordinate_plan(engine, venues, planned, args.expect_updates)
        report.update({"written": True, "coordinate_updates": updated})
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
