"""Transactional writer for the single reviewed 250-row CLUB_VENUE approval set."""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from pathlib import Path
from typing import Any, Callable

from sqlalchemy import bindparam, create_engine, text
from sqlalchemy.engine import Connection, make_url

from prepare_club_venue_backfill import LOCAL_HOSTS, SafetyError, evaluate, load_approvals, query_snapshot, sha256_file


EXPECTED_APPROVAL_COUNT = 250
EXPECTED_APPROVAL_SHA256 = "09027B5F78B38BDD88D2624095E48BE20BDD9E118D017AF0CAE55864D6EF4C4C"
PROTECTED_TABLES = (
    "teams", "venues", "fixtures", "pre_match_spots", "pre_match_spot_evidence",
    "venue_guide_facts", "users", "anonymous_sessions", "user_identities",
    "interested_fixtures", "fixture_meeting_intents", "match_board_posts",
    "social_events", "venue_visits", "away_day_reviews",
)


def require_write_confirmation(write: bool, confirm_write: bool) -> bool:
    if write != confirm_write:
        missing = "--write" if not write else "--confirm-write"
        raise SafetyError(f"write refused: {missing} is required")
    return write and confirm_write


def ensure_database_scope(database_url: str, allow_remote_write: bool, write_enabled: bool,
                          allow_remote_audit: bool = False) -> tuple[Any, str]:
    url = make_url(database_url)
    host_class = "local" if url.host in LOCAL_HOSTS else "remote"
    if host_class == "remote" and write_enabled and not allow_remote_write:
        raise SafetyError("remote write refused without --allow-remote-write")
    if host_class == "remote" and not write_enabled and not allow_remote_audit:
        raise SafetyError("remote dry run refused without --allow-remote-audit")
    if host_class == "local" and (allow_remote_write or allow_remote_audit):
        raise SafetyError("remote-intent flags are invalid for a local database")
    return url, host_class


def table_counts(connection: Connection) -> dict[str, int]:
    names = ("club_venues",) + PROTECTED_TABLES
    return {name: connection.execute(text(f'SELECT count(*) FROM "{name}"')).scalar_one() for name in names}


def audit_on_connection(connection: Connection, approvals: list[dict[str, str]]) -> tuple[dict[str, int], list[dict[str, Any]]]:
    snapshot, _ = query_snapshot(connection, approvals)
    results, drift = evaluate(approvals, snapshot)
    counts = Counter(item["classification"] for item in results)
    classifications = {name: counts[name] for name in ("INSERT", "SAFE_EXISTING", "REVIEW_REQUIRED", "BLOCKING_CONFLICT")}
    if drift or classifications != {"INSERT": 250, "SAFE_EXISTING": 0, "REVIEW_REQUIRED": 0, "BLOCKING_CONFLICT": 0}:
        raise SafetyError(f"pre-write audit failed closed: {classifications}; drift={len(drift)}")
    if snapshot.existing:
        raise SafetyError(f"pre-write audit requires club_venues=0, got {len(snapshot.existing)}")
    return classifications, results


def read_only_dry_run(database_url: str, approvals: list[dict[str, str]]) -> dict[str, Any]:
    engine = create_engine(database_url, pool_pre_ping=True)
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(text("SET TRANSACTION READ ONLY"))
            identity = connection.execute(text("SELECT current_database(), inet_server_addr()::text, inet_server_port()")) .one()
            classifications, _ = audit_on_connection(connection, approvals)
        finally:
            transaction.rollback()
    return {"database": identity[0], "server_address": identity[1], "server_port": identity[2],
            "classifications": classifications, "prospective_delta": {"club_venues": 250, "all_other_tables": 0},
            "database_writes": 0}


def approved_rows(connection: Connection, approvals: list[dict[str, str]]) -> list[dict[str, Any]]:
    team_ids = [int(row["team_id"]) for row in approvals]
    query = text("""
        SELECT club_venue_id, team_id, venue_id, relationship_type, status, valid_from, valid_until
        FROM club_venues WHERE team_id IN :ids ORDER BY team_id
    """).bindparams(bindparam("ids", expanding=True))
    return [dict(row) for row in connection.execute(query, {"ids": team_ids}).mappings()]


def reconcile_write(connection: Connection, approvals: list[dict[str, str]], before: dict[str, int]) -> dict[str, Any]:
    after = table_counts(connection)
    expected_pairs = {(int(row["team_id"]), int(row["venue_id"])) for row in approvals}
    rows = approved_rows(connection, approvals)
    actual_pairs = {(row["team_id"], row["venue_id"]) for row in rows}
    errors = []
    if after["club_venues"] - before["club_venues"] != 250: errors.append("club_venues delta is not +250")
    if len(rows) != 250 or actual_pairs != expected_pairs: errors.append("approved team/venue reconciliation mismatch")
    if any(row["relationship_type"] != "HOME" or row["status"] != "CURRENT" for row in rows): errors.append("unexpected relationship type/status")
    if any(row["valid_from"] is not None or row["valid_until"] is not None for row in rows): errors.append("validity dates were unexpectedly populated")
    if any(row["team_id"] in {1832, 9010} for row in rows): errors.append("excluded club was inserted")
    if connection.execute(text("SELECT count(*) FROM club_venues WHERE relationship_type IN ('TEMPORARY_HOME','GROUND_SHARE') OR status='HISTORICAL'")) .scalar_one(): errors.append("unexpected relationship vocabulary present")
    for table in PROTECTED_TABLES:
        if after[table] != before[table]: errors.append(f"unexpected {table} delta")
    ownership = connection.execute(text("""
        SELECT count(*) FILTER (WHERE venue_id IS NOT NULL AND club_venue_id IS NULL),
               count(*) FILTER (WHERE club_venue_id IS NOT NULL),
               count(*) FILTER (WHERE (venue_id IS NULL) = (club_venue_id IS NULL))
        FROM venue_guide_facts
    """)).one()
    hutnik = connection.execute(text("SELECT count(*) FROM venue_guide_facts WHERE venue_id=22950 AND club_venue_id IS NULL")).scalar_one()
    if ownership[1] != 0 or ownership[2] != 0 or hutnik != 11: errors.append("VenueGuideFact/Hutnik ownership changed")
    outside = connection.execute(text("SELECT count(*) FROM club_venues WHERE team_id NOT IN :ids").bindparams(bindparam("ids", expanding=True)),
                                 {"ids": [int(row["team_id"]) for row in approvals]}).scalar_one()
    if outside != before["club_venues"]: errors.append("unexpected relationship outside approval set")
    if errors: raise SafetyError("post-write reconciliation failed: " + "; ".join(errors))
    return {"inserted": len(rows), "approved_pairs": len(actual_pairs), "home_current": len(rows),
            "club_venues_after": after["club_venues"], "protected_table_deltas": {table: 0 for table in PROTECTED_TABLES},
            "hutnik_venue_owned_facts": hutnik}


def execute_write(database_url: str, approvals: list[dict[str, str]], after_inserts: Callable[[Connection], None] | None = None,
                  before_commit: Callable[[Connection], None] | None = None) -> dict[str, Any]:
    read_only_preflight = read_only_dry_run(database_url, approvals)
    engine = create_engine(database_url, pool_pre_ping=True)
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"))
            identity = connection.execute(text("SELECT current_database(), inet_server_addr()::text, inet_server_port()")) .one()
            classifications, _ = audit_on_connection(connection, approvals)
            before = table_counts(connection)
            insert = text("""
                INSERT INTO club_venues (team_id, venue_id, relationship_type, status, valid_from, valid_until)
                VALUES (:team_id, :venue_id, 'HOME', 'CURRENT', NULL, NULL)
            """)
            for row in approvals:
                connection.execute(insert, {"team_id": int(row["team_id"]), "venue_id": int(row["venue_id"])})
            if after_inserts: after_inserts(connection)
            reconciliation = reconcile_write(connection, approvals, before)
            if before_commit: before_commit(connection)
            transaction.commit()
        except Exception:
            if transaction.is_active: transaction.rollback()
            raise
    return {"database": identity[0], "server_address": identity[1], "server_port": identity[2],
            "read_only_preflight": read_only_preflight["classifications"],
            "in_transaction_reaudit": classifications, "reconciliation": reconciliation,
            "physical_delta": {"club_venues": 250, "updates": 0, "deletes": 0, "all_other_tables": 0}}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approval-file", type=Path, required=True)
    parser.add_argument("--expected-approval-sha256", default=EXPECTED_APPROVAL_SHA256)
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--confirm-write", action="store_true")
    parser.add_argument("--allow-remote-write", action="store_true")
    parser.add_argument("--allow-remote-audit", action="store_true")
    args = parser.parse_args()
    if not args.database_url: raise SafetyError("DATABASE_URL or --database-url is required")
    if args.expected_approval_sha256.casefold() != EXPECTED_APPROVAL_SHA256.casefold(): raise SafetyError("unexpected approval hash argument")
    approvals = load_approvals(args.approval_file, EXPECTED_APPROVAL_SHA256)
    should_write = require_write_confirmation(args.write, args.confirm_write)
    url, host_class = ensure_database_scope(args.database_url, args.allow_remote_write, should_write, args.allow_remote_audit)
    result = execute_write(url.render_as_string(hide_password=False), approvals) if should_write else read_only_dry_run(url.render_as_string(hide_password=False), approvals)
    result.update({"host_class": host_class, "approval_sha256": sha256_file(args.approval_file), "write": should_write})
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
