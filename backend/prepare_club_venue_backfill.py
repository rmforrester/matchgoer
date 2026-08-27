"""Read-only CLUB_VENUE approval-set validation and dry-run reporting.

There is deliberately no database write mode in this tool.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import bindparam, create_engine, text
from sqlalchemy.engine import make_url


AUDIT_VERSION = "club-venue-backfill-v2"
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
APPROVAL_FIELDS = (
    "team_id", "team_name", "venue_id", "venue_name", "relationship_type",
    "status", "audit_version", "approval_state", "latest_fixture_season",
    "latest_home_fixture_count", "latest_fixture_venue_ids",
    "all_fixture_venue_ids", "identity_sha256",
)


class SafetyError(RuntimeError):
    """Raised when approval or database state fails closed."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def identity_hash(row: dict[str, Any]) -> str:
    identity = {key: str(row[key]).strip() for key in APPROVAL_FIELDS if key != "identity_sha256"}
    encoded = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def normalized(value: Any) -> str:
    return " ".join(str(value or "").casefold().split())


def load_approvals(path: Path, expected_sha256: str) -> list[dict[str, str]]:
    actual = sha256_file(path)
    if actual.casefold() != expected_sha256.casefold():
        raise SafetyError(f"approval SHA-256 mismatch: expected {expected_sha256}, got {actual}")
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    if tuple(rows[0].keys()) != APPROVAL_FIELDS if rows else True:
        raise SafetyError("approval columns do not match the v2 contract")
    errors: list[str] = []
    team_ids: set[str] = set()
    pairs: set[tuple[str, str]] = set()
    for index, row in enumerate(rows, 2):
        if row["team_id"] in team_ids:
            errors.append(f"row {index}: duplicate team_id {row['team_id']}")
        team_ids.add(row["team_id"])
        pair = (row["team_id"], row["venue_id"])
        if pair in pairs:
            errors.append(f"row {index}: duplicate team/venue {pair}")
        pairs.add(pair)
        if row["team_id"] in {"1832", "9010"}:
            errors.append(f"row {index}: excluded team {row['team_id']} is present")
        if row["relationship_type"] != "HOME" or row["status"] != "CURRENT":
            errors.append(f"row {index}: only HOME/CURRENT is permitted")
        if row["audit_version"] != AUDIT_VERSION or row["approval_state"] != "APPROVED":
            errors.append(f"row {index}: approval metadata is invalid")
        if identity_hash(row) != row["identity_sha256"]:
            errors.append(f"row {index}: identity SHA-256 mismatch")
    if len(rows) != 250:
        errors.append(f"expected 250 approved rows, got {len(rows)}")
    if errors:
        raise SafetyError("; ".join(errors))
    return rows


@dataclass
class Snapshot:
    teams: dict[int, dict[str, Any]]
    venues: dict[int, dict[str, Any]]
    fixture_evidence: dict[int, list[dict[str, Any]]]
    venue_team_usage: dict[int, set[int]]
    existing: list[dict[str, Any]]
    content_counts: dict[int, tuple[int, int]]


def evaluate(approvals: list[dict[str, str]], snapshot: Snapshot) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    results: list[dict[str, Any]] = []
    drift: list[dict[str, Any]] = []
    approved_team_ids = {int(row["team_id"]) for row in approvals}
    approved_venue_usage: defaultdict[int, list[int]] = defaultdict(list)
    for row in approvals:
        approved_venue_usage[int(row["venue_id"])].append(int(row["team_id"]))

    for row in approvals:
        team_id, venue_id = int(row["team_id"]), int(row["venue_id"])
        reasons: list[str] = []
        team, venue = snapshot.teams.get(team_id), snapshot.venues.get(venue_id)
        if not team:
            reasons.append("MISSING_TEAM")
        else:
            if normalized(team["team_name"]) != normalized(row["team_name"]):
                reasons.append("TEAM_NAME_DRIFT")
            if team.get("venue_id") != venue_id:
                reasons.append("TEAM_VENUE_DRIFT")
        if not venue:
            reasons.append("MISSING_VENUE")
        elif normalized(venue["name"]) != normalized(row["venue_name"]):
            reasons.append("VENUE_NAME_DRIFT")

        evidence = snapshot.fixture_evidence.get(team_id, [])
        seasons = [item["season"] for item in evidence if item["season"] is not None]
        latest_season = max(seasons) if seasons else None
        latest = [item for item in evidence if item["season"] == latest_season]
        latest_ids = {item["venue_id"] for item in latest}
        nonnull_ids = latest_ids - {None}
        latest_count = sum(int(item["fixture_count"]) for item in latest)
        all_ids = {item["venue_id"] for item in evidence}
        expected_all = {int(value) for value in row["all_fixture_venue_ids"].split("|") if value and value != "NULL"}
        if latest_season is None:
            reasons.append("NO_HOME_FIXTURE_EVIDENCE")
        if None in latest_ids:
            reasons.append("MISSING_LATEST_FIXTURE_VENUE")
        if nonnull_ids != {venue_id}:
            reasons.append("AMBIGUOUS_OR_DRIFTED_FIXTURE_VENUE")
        if str(latest_season) != row["latest_fixture_season"] or latest_count != int(row["latest_home_fixture_count"]):
            reasons.append("LATEST_FIXTURE_SNAPSHOT_DRIFT")
        if {value for value in all_ids if value is not None} != expected_all:
            reasons.append("MOVE_OR_HISTORY_DRIFT")
        if len(approved_venue_usage[venue_id]) != 1:
            reasons.append("DUPLICATE_APPROVED_VENUE")
        other_teams = snapshot.venue_team_usage.get(venue_id, set()) - {team_id}
        if other_teams - approved_team_ids:
            reasons.append("NEW_SHARED_VENUE_USAGE")

        existing = [item for item in snapshot.existing if item["team_id"] == team_id]
        same = [item for item in existing if item["venue_id"] == venue_id and item["status"] == "CURRENT" and item["relationship_type"] == "HOME"]
        conflicting = [item for item in existing if item["status"] == "CURRENT" and item not in same]
        if conflicting:
            reasons.append("CONFLICTING_CURRENT_RELATIONSHIP")
        if len(same) > 1:
            reasons.append("DUPLICATE_CURRENT_RELATIONSHIP")
        content = sum(sum(snapshot.content_counts.get(int(item["club_venue_id"]), (0, 0))) for item in existing)
        if content:
            reasons.append("UNEXPECTED_EXISTING_CONTENT")

        if reasons:
            classification = "BLOCKING_CONFLICT" if any(reason.startswith(("MISSING_", "CONFLICTING", "DUPLICATE_CURRENT", "UNEXPECTED")) for reason in reasons) else "REVIEW_REQUIRED"
            drift.extend({"team_id": team_id, "venue_id": venue_id, "reason": reason} for reason in reasons)
        elif same:
            classification = "SAFE_EXISTING"
        elif existing:
            classification = "BLOCKING_CONFLICT"
            reasons.append("EXISTING_NONMATCHING_RELATIONSHIP")
            drift.append({"team_id": team_id, "venue_id": venue_id, "reason": reasons[-1]})
        else:
            classification = "INSERT"
        results.append({"team_id": team_id, "team_name": row["team_name"], "venue_id": venue_id,
                        "venue_name": row["venue_name"], "classification": classification,
                        "reasons": "|".join(reasons)})
    return results, drift


def query_snapshot(connection, approvals: list[dict[str, str]]) -> tuple[Snapshot, dict[str, Any]]:
    team_ids = [int(row["team_id"]) for row in approvals]
    venue_ids = [int(row["venue_id"]) for row in approvals]
    teams_query = text("SELECT team_id, team_name, venue_id FROM teams WHERE team_id IN :ids").bindparams(bindparam("ids", expanding=True))
    venues_query = text("SELECT venue_id, name FROM venues WHERE venue_id IN :ids").bindparams(bindparam("ids", expanding=True))
    fixtures_query = text("""
        SELECT home_team_id AS team_id, season, venue_id, count(*) AS fixture_count
        FROM fixtures WHERE home_team_id IN :ids
        GROUP BY home_team_id, season, venue_id ORDER BY home_team_id, season, venue_id
    """).bindparams(bindparam("ids", expanding=True))
    usage_query = text("SELECT venue_id, team_id FROM teams WHERE venue_id IN :ids").bindparams(bindparam("ids", expanding=True))
    teams = {row["team_id"]: dict(row) for row in connection.execute(teams_query, {"ids": team_ids}).mappings()}
    venues = {row["venue_id"]: dict(row) for row in connection.execute(venues_query, {"ids": venue_ids}).mappings()}
    fixture_evidence: defaultdict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in connection.execute(fixtures_query, {"ids": team_ids}).mappings():
        fixture_evidence[row["team_id"]].append(dict(row))
    usage: defaultdict[int, set[int]] = defaultdict(set)
    for row in connection.execute(usage_query, {"ids": venue_ids}).mappings():
        usage[row["venue_id"]].add(row["team_id"])
    existing = [dict(row) for row in connection.execute(text("SELECT club_venue_id, team_id, venue_id, relationship_type, status, valid_from, valid_until FROM club_venues")).mappings()]
    content_counts: dict[int, tuple[int, int]] = {}
    for row in connection.execute(text("""
        SELECT cv.club_venue_id, count(DISTINCT p.pre_match_spot_id) AS spots,
               count(DISTINCT f.fact_id) AS facts
        FROM club_venues cv
        LEFT JOIN pre_match_spots p ON p.club_venue_id = cv.club_venue_id
        LEFT JOIN venue_guide_facts f ON f.club_venue_id = cv.club_venue_id
        GROUP BY cv.club_venue_id
    """)).mappings():
        content_counts[row["club_venue_id"]] = (row["spots"], row["facts"])
    counts = {
        "teams": connection.execute(text("SELECT count(*) FROM teams")).scalar_one(),
        "venues": connection.execute(text("SELECT count(*) FROM venues")).scalar_one(),
        "fixtures": connection.execute(text("SELECT count(*) FROM fixtures")).scalar_one(),
        "club_venues": len(existing),
        "pre_match_spots": connection.execute(text("SELECT count(*) FROM pre_match_spots")).scalar_one(),
        "club_owned_venue_guide_facts": connection.execute(text("SELECT count(*) FROM venue_guide_facts WHERE club_venue_id IS NOT NULL")).scalar_one(),
    }
    return Snapshot(teams, venues, fixture_evidence, usage, existing, content_counts), counts


def write_reports(output: Path, results: list[dict[str, Any]], drift: list[dict[str, Any]], metadata: dict[str, Any]) -> None:
    output.mkdir(parents=True, exist_ok=True)
    counts = Counter(row["classification"] for row in results)
    report = {**metadata, "classifications": {key: counts[key] for key in ("INSERT", "SAFE_EXISTING", "REVIEW_REQUIRED", "BLOCKING_CONFLICT")},
              "prospective_delta": {"club_venues_inserts": counts["INSERT"], "updates": 0, "deletes": 0,
                                      "pre_match_spots": 0, "pre_match_spot_evidence": 0, "venue_guide_facts": 0},
              "database_writes": 0, "go": not drift and counts["INSERT"] + counts["SAFE_EXISTING"] == 250}
    (output / "dry-run-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    with (output / "drift-report.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=("team_id", "venue_id", "reason")); writer.writeheader(); writer.writerows(drift)
    conflicts = [row for row in results if row["classification"] != "INSERT" and row["classification"] != "SAFE_EXISTING"]
    with (output / "conflict-report.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=("team_id", "team_name", "venue_id", "venue_name", "classification", "reasons")); writer.writeheader(); writer.writerows(conflicts)
    summary = f"""# CLUB_VENUE backfill dry run

- Database: `{metadata['database_name']}` ({metadata['host_class']})
- Approval file SHA-256: `{metadata['approval_sha256']}`
- INSERT: **{counts['INSERT']}**
- SAFE_EXISTING: **{counts['SAFE_EXISTING']}**
- REVIEW_REQUIRED: **{counts['REVIEW_REQUIRED']}**
- BLOCKING_CONFLICT: **{counts['BLOCKING_CONFLICT']}**
- Prospective physical delta: **{counts['INSERT']} club_venues inserts; zero other rows, updates or deletes**
- DATABASE WRITES: **0**
- Decision: **{'GO' if report['go'] else 'NO-GO'}**
"""
    (output / "dry-run-summary.md").write_text(summary, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approval-file", type=Path, required=True)
    parser.add_argument("--expected-approval-sha256", required=True)
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--allow-remote-audit", action="store_true")
    args = parser.parse_args()
    if not args.database_url:
        raise SafetyError("DATABASE_URL or --database-url is required")
    approvals = load_approvals(args.approval_file, args.expected_approval_sha256)
    url = make_url(args.database_url)
    host_class = "local" if url.host in LOCAL_HOSTS else "remote"
    if host_class == "remote" and not args.allow_remote_audit:
        raise SafetyError("remote database audit requires --allow-remote-audit")
    engine = create_engine(url, pool_pre_ping=True)
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(text("SET TRANSACTION READ ONLY"))
            identity = connection.execute(text("SELECT current_database(), inet_server_addr()::text, inet_server_port()")).one()
            snapshot, db_counts = query_snapshot(connection, approvals)
        finally:
            transaction.rollback()
    results, drift = evaluate(approvals, snapshot)
    metadata = {"audit_version": AUDIT_VERSION, "approval_sha256": sha256_file(args.approval_file),
                "database_name": identity[0], "host_class": host_class, "server_address": identity[1],
                "server_port": identity[2], "database_counts": db_counts,
                "read_only_proof": "engine.connect(); SET TRANSACTION READ ONLY; SELECT only; explicit rollback"}
    write_reports(args.output_dir, results, drift, metadata)
    counts = Counter(row["classification"] for row in results)
    print(f"Database: {identity[0]} ({host_class})")
    print(f"Approval SHA-256: {metadata['approval_sha256']}")
    for label in ("INSERT", "SAFE_EXISTING", "REVIEW_REQUIRED", "BLOCKING_CONFLICT"):
        print(f"{label}: {counts[label]}")
    print("DATABASE WRITES: 0")
    return 0 if not drift and counts["INSERT"] + counts["SAFE_EXISTING"] == 250 else 2


if __name__ == "__main__":
    raise SystemExit(main())
