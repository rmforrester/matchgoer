"""Audit and backfill venue visits from the legacy AwayDayReview coupling.

Dry-run is the default. Writes require both --write and --confirm-write, and are
refused when fixture/venue reconciliation or planned uniqueness is ambiguous.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, inspect, text

from ingestion.environment import ROOT, database_url


REVIEW_SQL = text("""
    SELECT r.review_id, r.user_id, r.venue_id, r.fixture_id, r.visit_date,
           r.recommend, r.overall_score, r.atmosphere_score, r.pubs_score,
           r.getting_there_score, r.facilities_score, r.created_at,
           f.fixture_id AS matched_fixture_id, f.venue_id AS fixture_venue_id
    FROM away_day_reviews r
    LEFT JOIN fixtures f ON f.fixture_id = r.fixture_id
    ORDER BY r.review_id
""")


def as_date(value: date | datetime | None) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    return value


def classify_review(row: dict[str, Any]) -> str:
    reviewed_values = (
        row["recommend"], row["atmosphere_score"], row["pubs_score"],
        row["getting_there_score"], row["facilities_score"],
    )
    if all(value is None for value in reviewed_values):
        return "blank"
    if all(value is not None for value in reviewed_values):
        return "completed"
    return "partial"


def audit(connection) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    rows = [dict(row) for row in connection.execute(REVIEW_SQL).mappings()]
    classifications = Counter(classify_review(row) for row in rows)
    plans: list[dict[str, Any]] = []
    exceptions: list[dict[str, Any]] = []
    inconsistencies: list[dict[str, Any]] = []
    plan_keys: Counter[tuple[Any, ...]] = Counter()

    for row in rows:
        categories = [
            row["atmosphere_score"], row["pubs_score"],
            row["getting_there_score"], row["facilities_score"],
        ]
        completed_categories = [value for value in categories if value is not None]
        expected_overall = (
            round((sum(completed_categories) / len(completed_categories)) + 1e-9, 1)
            if completed_categories else None
        )
        if row["overall_score"] is not None and not completed_categories:
            inconsistencies.append({"review_id": row["review_id"], "type": "overall_without_categories"})
        elif row["overall_score"] is None and completed_categories:
            inconsistencies.append({"review_id": row["review_id"], "type": "categories_without_overall"})
        elif expected_overall is not None and abs(float(row["overall_score"]) - expected_overall) > 0.001:
            inconsistencies.append({
                "review_id": row["review_id"], "type": "overall_mismatch",
                "stored": float(row["overall_score"]), "calculated": expected_overall,
            })

        if row["fixture_id"] is not None:
            if row["matched_fixture_id"] is None:
                exceptions.append({"review_id": row["review_id"], "type": "missing_fixture", "fixture_id": row["fixture_id"]})
                continue
            if row["fixture_venue_id"] != row["venue_id"]:
                exceptions.append({
                    "review_id": row["review_id"], "type": "fixture_venue_mismatch",
                    "fixture_id": row["fixture_id"], "review_venue_id": row["venue_id"],
                    "fixture_venue_id": row["fixture_venue_id"],
                })
                continue
            visit_type = "fixture_linked"
            key = ("fixture", row["user_id"], row["fixture_id"])
        elif row["visit_date"] is not None:
            visit_type = "manual_dated"
            key = ("manual_dated", row["user_id"], row["venue_id"], as_date(row["visit_date"]))
        else:
            visit_type = "manual_undated"
            key = ("manual_undated", row["user_id"], row["venue_id"])
        plan_keys[key] += 1
        plans.append({
            "review_id": row["review_id"], "user_id": row["user_id"],
            "venue_id": row["venue_id"], "fixture_id": row["fixture_id"],
            "visit_date": as_date(row["visit_date"]), "source": "migration",
            "created_at": row["created_at"], "type": visit_type,
        })

    duplicate_plans = [
        {"key": [str(part) for part in key], "count": count}
        for key, count in plan_keys.items() if count > 1
    ]
    current_grounds = {(row["user_id"], row["venue_id"]) for row in rows}
    planned_grounds = {(plan["user_id"], plan["venue_id"]) for plan in plans}
    types = Counter(plan["type"] for plan in plans)
    report: dict[str, Any] = {
        "mode": "dry_run",
        "away_day_reviews": {
            "total": len(rows),
            "completed": classifications["completed"],
            "partial": classifications["partial"],
            "blank_visited_only": classifications["blank"],
            "with_fixture_id": sum(row["fixture_id"] is not None for row in rows),
            "with_visit_date_no_fixture": sum(row["fixture_id"] is None and row["visit_date"] is not None for row in rows),
            "undated": sum(row["fixture_id"] is None and row["visit_date"] is None for row in rows),
            "review_ids": [row["review_id"] for row in rows],
        },
        "planned_visits": {
            "total": len(plans),
            "fixture_linked": types["fixture_linked"],
            "manual_dated": types["manual_dated"],
            "manual_undated": types["manual_undated"],
        },
        "duplicate_plans": duplicate_plans,
        "reconciliation_exceptions": exceptions,
        "review_value_inconsistencies": inconsistencies,
        "grounds_reconciliation": {
            "current_user_venue_pairs": len(current_grounds),
            "planned_user_venue_pairs": len(planned_grounds),
            "missing_from_plan": sorted([list(item) for item in current_grounds - planned_grounds]),
            "unexpected_in_plan": sorted([list(item) for item in planned_grounds - current_grounds]),
        },
        "safe_to_backfill": not exceptions and not duplicate_plans and current_grounds == planned_grounds,
    }
    return report, plans


def backfill(connection, report: dict[str, Any], plans: list[dict[str, Any]]) -> None:
    if not report["safe_to_backfill"]:
        raise RuntimeError("Dry-run has reconciliation exceptions; refusing to backfill.")
    if "venue_visits" not in inspect(connection).get_table_names():
        raise RuntimeError("venue_visits does not exist; apply the reviewed table migration first.")

    before_review_ids = report["away_day_reviews"]["review_ids"]
    for plan in plans:
        connection.execute(text("""
            INSERT INTO venue_visits (
                user_id, venue_id, fixture_id, visit_date, source, created_at
            ) VALUES (
                :user_id, :venue_id, :fixture_id, :visit_date, :source,
                COALESCE(:created_at, now())
            )
            ON CONFLICT DO NOTHING
        """), plan)

    after_review_ids = list(connection.execute(text(
        "SELECT review_id FROM away_day_reviews ORDER BY review_id"
    )).scalars())
    visit_rows = [dict(row) for row in connection.execute(text("""
        SELECT visit_id, user_id, venue_id, fixture_id, visit_date, source
        FROM venue_visits ORDER BY visit_id
    """)).mappings()]
    visit_grounds = {(row["user_id"], row["venue_id"]) for row in visit_rows}
    current_grounds = {
        tuple(row) for row in connection.execute(text(
            "SELECT DISTINCT user_id, venue_id FROM away_day_reviews"
        )).all()
    }
    duplicate_fixture = connection.execute(text("""
        SELECT count(*) FROM (
            SELECT user_id, fixture_id FROM venue_visits WHERE fixture_id IS NOT NULL
            GROUP BY user_id, fixture_id HAVING count(*) > 1
        ) duplicates
    """)).scalar_one()
    duplicate_dated = connection.execute(text("""
        SELECT count(*) FROM (
            SELECT user_id, venue_id, visit_date FROM venue_visits
            WHERE fixture_id IS NULL AND visit_date IS NOT NULL
            GROUP BY user_id, venue_id, visit_date HAVING count(*) > 1
        ) duplicates
    """)).scalar_one()
    duplicate_undated = connection.execute(text("""
        SELECT count(*) FROM (
            SELECT user_id, venue_id FROM venue_visits
            WHERE fixture_id IS NULL AND visit_date IS NULL
            GROUP BY user_id, venue_id HAVING count(*) > 1
        ) duplicates
    """)).scalar_one()
    if before_review_ids != after_review_ids:
        raise RuntimeError("AwayDayReview IDs changed during backfill.")
    if current_grounds != visit_grounds:
        raise RuntimeError("Visit-derived My Grounds set does not reconcile.")
    if any((duplicate_fixture, duplicate_dated, duplicate_undated)):
        raise RuntimeError("Post-backfill visit uniqueness check failed.")
    report["mode"] = "write"
    report["post_backfill"] = {
        "venue_visits": len(visit_rows),
        "fixture_linked": sum(row["fixture_id"] is not None for row in visit_rows),
        "manual_dated": sum(row["fixture_id"] is None and row["visit_date"] is not None for row in visit_rows),
        "manual_undated": sum(row["fixture_id"] is None and row["visit_date"] is None for row in visit_rows),
        "review_count_unchanged": len(after_review_ids) == report["away_day_reviews"]["total"],
        "review_ids_unchanged": before_review_ids == after_review_ids,
        "current_ground_pairs": len(current_grounds),
        "visit_ground_pairs": len(visit_grounds),
        "missing_ground_pairs": sorted([list(item) for item in current_grounds - visit_grounds]),
        "unexpected_ground_pairs": sorted([list(item) for item in visit_grounds - current_grounds]),
        "duplicate_fixture_keys": duplicate_fixture,
        "duplicate_manual_dated_keys": duplicate_dated,
        "duplicate_manual_undated_keys": duplicate_undated,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--confirm-write", action="store_true")
    parser.add_argument(
        "--output", type=Path,
        default=ROOT / "reports" / "venue-visits-migration-2026-08-17.json",
    )
    args = parser.parse_args()
    if args.write != args.confirm_write:
        parser.error("Writes require both --write and --confirm-write.")

    engine = create_engine(database_url(), connect_args={"connect_timeout": 10})
    if args.write:
        with engine.begin() as connection:
            report, plans = audit(connection)
            backfill(connection, report, plans)
    else:
        with engine.connect() as connection:
            report, _ = audit(connection)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
