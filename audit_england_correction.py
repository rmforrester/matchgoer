"""Read-only exact correction plan for England 2026 fixture contamination."""

from __future__ import annotations

import json
from collections import defaultdict

from sqlalchemy import create_engine, text

from config.leagues import ENGLAND_PYRAMID_2026
from ingest_leagues import resolve_scope
from ingestion.api_football import ApiFootballClient
from ingestion.environment import ROOT, api_football_key, database_url


REPORT = ROOT / "reports" / "ingestion" / "england-correction-plan-2026.json"


def main() -> int:
    client = ApiFootballClient(api_football_key(), ROOT / ".cache" / "api-football")
    supported = []
    correct: dict[int, dict] = {}
    for configured in ENGLAND_PYRAMID_2026:
        scope = resolve_scope(client, configured)
        coverage = client.league_for_season(scope.league_id, 2026) if scope.league_id else []
        available = bool(coverage and any(x.get("league", {}).get("id") == scope.league_id for x in coverage))
        fixtures = client.fixtures(scope.league_id, 2026) if available else []
        supported.append({"competition": scope.display_name, "league_id": scope.league_id,
                          "available": available, "fixture_count": len(fixtures)})
        for item in fixtures:
            fixture_id = item["fixture"]["id"]
            correct[fixture_id] = {"league_id": item["league"]["id"], "league_name": item["league"]["name"]}

    engine = create_engine(database_url(), connect_args={"connect_timeout": 10})
    with engine.connect() as connection:
        current_rows = [dict(row) for row in connection.execute(text("""
            SELECT fixture_id, league_id, league_name, home_team, away_team
            FROM fixtures WHERE country = 'England' AND season = 2026
        """)).mappings()]
        current = {row["fixture_id"]: row for row in current_rows}
        incorrect = [row for row in current_rows if row["fixture_id"] not in correct]
        wrong_assignment = [row for row in current_rows if row["fixture_id"] in correct and
                            (row["league_id"] != correct[row["fixture_id"]]["league_id"] or
                             row["league_name"] != correct[row["fixture_id"]]["league_name"])]
        missing = sorted(set(correct) - set(current))
        affected_ids = [row["fixture_id"] for row in incorrect]
        dependency_counts = {"interested_fixtures": 0, "away_day_reviews": 0}
        dependency_rows = {"interested_fixtures": [], "away_day_reviews": []}
        if affected_ids:
            for table in dependency_counts:
                rows = [dict(row) for row in connection.execute(
                    text(f"SELECT * FROM {table} WHERE fixture_id = ANY(:ids)"), {"ids": affected_ids}
                ).mappings()]
                dependency_rows[table] = rows
                dependency_counts[table] = len(rows)
        fixture_review_total = connection.execute(text(
            "SELECT count(*) FROM away_day_reviews WHERE fixture_id IS NOT NULL"
        )).scalar_one()
        interest_total = connection.execute(text("SELECT count(*) FROM interested_fixtures")).scalar_one()

    by_stored_league: dict[str, int] = defaultdict(int)
    for row in incorrect:
        by_stored_league[f"{row['league_id']}|{row['league_name']}"] += 1
    report = {
        "current_england_2026_rows": len(current), "correct_supported_fixture_ids": len(correct),
        "incorrect_rows_not_in_correct_responses": len(incorrect),
        "wrong_league_assignment_rows": len(wrong_assignment), "missing_correct_rows": len(missing),
        "incorrect_rows_by_stored_league": dict(by_stored_league),
        "supported_and_unavailable_competitions": supported,
        "correction_plan": {
            "delete_fixture_ids": sorted(affected_ids), "update_wrong_assignment_fixture_ids": sorted(row["fixture_id"] for row in wrong_assignment),
            "insert_missing_fixture_ids": missing,
            "then_upsert_supported_leagues": [row["league_id"] for row in supported if row["available"]],
            "do_not_import_unavailable_leagues": [row["league_id"] for row in supported if not row["available"]],
        },
        "dependency_safety": {"affected_dependency_counts": dependency_counts,
                              "affected_dependency_rows": dependency_rows,
                              "all_fixture_linked_reviews": fixture_review_total,
                              "all_fixture_interests": interest_total},
        "incorrect_row_sample": incorrect[:20],
        "api_requests": client.requests_made, "api_cache_hits": client.cache_hits, "api_errors": client.failures,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key not in {"correction_plan", "incorrect_row_sample"}}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
