"""Narrow transactional rollback for the reviewed 250-row CLUB_VENUE set."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from sqlalchemy import bindparam, create_engine, inspect, text
from sqlalchemy.engine import Connection

from apply_club_venue_backfill import (EXPECTED_APPROVAL_SHA256, PROTECTED_TABLES, approved_rows,
                                       ensure_database_scope, table_counts)
from prepare_club_venue_backfill import SafetyError, load_approvals, sha256_file


def require_rollback_confirmation(rollback: bool, confirm_rollback: bool) -> None:
    if not rollback or not confirm_rollback:
        missing = "--rollback" if not rollback else "--confirm-rollback"
        raise SafetyError(f"rollback refused: {missing} is required")


def referencing_children(connection: Connection, club_venue_ids: list[int]) -> dict[str, int]:
    found: dict[str, int] = {}
    inspector = inspect(connection)
    for table in inspector.get_table_names(schema="public"):
        for foreign_key in inspector.get_foreign_keys(table, schema="public"):
            if foreign_key.get("referred_table") != "club_venues": continue
            columns = foreign_key.get("constrained_columns") or []
            if len(columns) != 1: raise SafetyError(f"unsupported child foreign key shape: {table}")
            quoted_table = connection.dialect.identifier_preparer.quote(table)
            quoted_column = connection.dialect.identifier_preparer.quote(columns[0])
            query = text(f"SELECT count(*) FROM {quoted_table} WHERE {quoted_column} IN :ids").bindparams(bindparam("ids", expanding=True))
            count = connection.execute(query, {"ids": club_venue_ids}).scalar_one()
            if count: found[table] = count
    return found


def execute_rollback(database_url: str, approvals: list[dict[str, str]]) -> dict:
    engine = create_engine(database_url, pool_pre_ping=True)
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"))
            before = table_counts(connection)
            rows = approved_rows(connection, approvals)
            expected = {(int(row["team_id"]), int(row["venue_id"])) for row in approvals}
            actual = {(row["team_id"], row["venue_id"]) for row in rows}
            if len(rows) != 250 or actual != expected: raise SafetyError("rollback requires the exact approved 250 relationships")
            if any(row["relationship_type"] != "HOME" or row["status"] != "CURRENT" or row["valid_from"] is not None or row["valid_until"] is not None for row in rows):
                raise SafetyError("approved relationship shape has drifted")
            ids = [row["club_venue_id"] for row in rows]
            children = referencing_children(connection, ids)
            if children: raise SafetyError(f"rollback refused: protected children exist {children}")
            delete = text("DELETE FROM club_venues WHERE club_venue_id IN :ids").bindparams(bindparam("ids", expanding=True))
            result = connection.execute(delete, {"ids": ids})
            if result.rowcount != 250: raise SafetyError(f"rollback deleted {result.rowcount}, expected 250")
            after = table_counts(connection)
            if after["club_venues"] != before["club_venues"] - 250: raise SafetyError("rollback club_venues delta mismatch")
            for table in PROTECTED_TABLES:
                if after[table] != before[table]: raise SafetyError(f"rollback changed protected table {table}")
            if approved_rows(connection, approvals): raise SafetyError("approved relationships remain after rollback")
            transaction.commit()
        except Exception:
            if transaction.is_active: transaction.rollback()
            raise
    return {"deleted": 250, "club_venues_before": before["club_venues"], "club_venues_after": after["club_venues"],
            "all_other_table_deltas": 0, "protected_children": 0}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approval-file", type=Path, required=True)
    parser.add_argument("--expected-approval-sha256", default=EXPECTED_APPROVAL_SHA256)
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    parser.add_argument("--rollback", action="store_true")
    parser.add_argument("--confirm-rollback", action="store_true")
    parser.add_argument("--allow-remote-write", action="store_true")
    args = parser.parse_args()
    if not args.database_url: raise SafetyError("DATABASE_URL or --database-url is required")
    if args.expected_approval_sha256.casefold() != EXPECTED_APPROVAL_SHA256.casefold(): raise SafetyError("unexpected approval hash argument")
    require_rollback_confirmation(args.rollback, args.confirm_rollback)
    approvals = load_approvals(args.approval_file, EXPECTED_APPROVAL_SHA256)
    url, host_class = ensure_database_scope(args.database_url, args.allow_remote_write, True)
    result = execute_rollback(url.render_as_string(hide_password=False), approvals)
    result.update({"host_class": host_class, "approval_sha256": sha256_file(args.approval_file)})
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
