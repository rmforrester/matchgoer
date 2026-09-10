"""Local-only safety helpers for KNOW v1 database acceptance."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse

from sqlalchemy import create_engine, inspect, text


PROTECTED_TABLES = (
    "fixtures", "teams", "venues", "venue_names", "venue_provider_refs",
    "club_venues", "pre_match_spots", "pre_match_spot_evidence",
    "decision_facts", "decision_evidence", "venue_guide_facts",
    "matchday_tips", "away_day_reviews",
)
KNOW_TABLES = ("know_facts", "know_fact_evidence")


def _assert_local(database_url: str) -> None:
    host = (urlparse(database_url).hostname or "").casefold()
    if host not in {"localhost", "127.0.0.1", "::1"}:
        raise RuntimeError(f"KNOW v1 acceptance is local-only; refused host {host!r}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fingerprint(database_url: str, output_path: Path) -> dict:
    _assert_local(database_url)
    engine = create_engine(database_url, pool_pre_ping=True)
    result = {"generated_at": datetime.now(timezone.utc).isoformat(), "tables": {}}
    inspector = inspect(engine)
    existing = set(inspector.get_table_names())
    with engine.connect() as connection:
        transaction = connection.begin()
        connection.execute(text("SET TRANSACTION READ ONLY"))
        for table in (*PROTECTED_TABLES, *KNOW_TABLES):
            if table not in existing:
                result["tables"][table] = {"exists": False, "rows": 0, "sha256": None}
                continue
            columns = [column["name"] for column in inspector.get_columns(table)]
            primary_key = inspector.get_pk_constraint(table).get("constrained_columns") or columns
            quoted_columns = ", ".join(f'"{column}"' for column in columns)
            order = ", ".join(f'"{column}"' for column in primary_key)
            rows = connection.execute(text(f'SELECT {quoted_columns} FROM "{table}" ORDER BY {order}'))
            digest = hashlib.sha256()
            count = 0
            for row in rows:
                payload = json.dumps(dict(row._mapping), sort_keys=True, default=str, ensure_ascii=False)
                digest.update(payload.encode("utf-8")); digest.update(b"\n"); count += 1
            result["tables"][table] = {"exists": True, "rows": count, "sha256": digest.hexdigest()}
        transaction.rollback()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def backup(database_url: str, output_path: Path, pg_dump: Path) -> dict:
    _assert_local(database_url)
    parsed = urlparse(database_url)
    env = os.environ.copy()
    if parsed.password:
        env["PGPASSWORD"] = unquote(parsed.password)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [str(pg_dump), "--format=custom", "--no-owner", "--no-acl",
               "--host", parsed.hostname or "localhost", "--port", str(parsed.port or 5432),
               "--username", unquote(parsed.username or "postgres"), "--file", str(output_path),
               unquote(parsed.path.lstrip("/"))]
    subprocess.run(command, env=env, check=True, capture_output=True, text=True)
    receipt = {"path": str(output_path.resolve()), "bytes": output_path.stat().st_size,
               "sha256": _sha256(output_path), "created_at": datetime.now(timezone.utc).isoformat()}
    output_path.with_suffix(output_path.suffix + ".json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    return receipt


def schema_state(database_url: str) -> dict:
    _assert_local(database_url)
    engine = create_engine(database_url, pool_pre_ping=True)
    with engine.connect() as connection:
        recovery = connection.execute(text("SELECT pg_is_in_recovery()" )).scalar_one()
        tables = set(inspect(connection).get_table_names())
    return {"pg_is_in_recovery": recovery, "know_facts_exists": "know_facts" in tables,
            "know_fact_evidence_exists": "know_fact_evidence" in tables}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("backup", "fingerprint", "state"))
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--output")
    parser.add_argument("--pg-dump", default=r"C:\Program Files\PostgreSQL\18\bin\pg_dump.exe")
    args = parser.parse_args()
    if args.action == "backup":
        value = backup(args.database_url, Path(args.output), Path(args.pg_dump))
    elif args.action == "fingerprint":
        value = fingerprint(args.database_url, Path(args.output))
    else:
        value = schema_state(args.database_url)
    print(json.dumps(value, indent=2))


if __name__ == "__main__":
    main()
