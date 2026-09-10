"""Exact-set KNOW copy cleanup with local/hosted drift and mutation guards."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "reports/final-pre-beta-ux/know-copy-manifest.json"
ALLOWED_DATABASES = {"matchgoer_btm_v2_local_20260907"}


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str, ensure_ascii=False).encode()).hexdigest()


def rows(connection, statement: str, **params):
    return [dict(row) for row in connection.execute(text(statement), params).mappings()]


def fingerprint(connection, table: str) -> dict:
    data = rows(connection, f"select * from {table} order by 1")
    return {"rows": len(data), "sha256": digest(data)}


def run(database_url: str, write: bool, allow_hosted: bool = False) -> dict:
    parsed = urlparse(database_url)
    if not allow_hosted and (parsed.hostname not in {"localhost", "127.0.0.1", "::1"} or parsed.path.lstrip("/") not in ALLOWED_DATABASES):
        raise RuntimeError("local KNOW cleanup refused this database target")
    pack = json.loads(MANIFEST.read_text(encoding="utf-8"))
    updates = pack["updates"]
    keys = [item["editorial_key"] for item in updates]
    if len(keys) != len(set(keys)):
        raise RuntimeError("duplicate editorial key in manifest")
    engine = create_engine(database_url)
    with engine.connect() as connection:
        before = {table: fingerprint(connection, table) for table in ("know_facts", "know_fact_evidence")}
        current = rows(connection, """select editorial_key,content,module,team_id,club_venue_id,venue_id,fixture_id,
            publication_status from know_facts where editorial_key=any(:keys) order by editorial_key""", keys=keys)
        by_key = {row["editorial_key"]: row for row in current}
        if set(by_key) != set(keys):
            raise RuntimeError("manifest key set does not match database")
        mutations = []
        already_correct = []
        for item in updates:
            row = by_key[item["editorial_key"]]
            stable = {key: row[key] for key in ("module", "team_id", "club_venue_id", "venue_id", "fixture_id", "publication_status")}
            if stable != item["stable_identity"]:
                raise RuntimeError(f"stable identity drift: {item['editorial_key']}")
            if row["content"] == item["after"]:
                already_correct.append(item["editorial_key"])
            elif row["content"] == item["before"]:
                mutations.append(item)
            else:
                raise RuntimeError(f"content drift: {item['editorial_key']}")
        if write and mutations:
            try:
                for item in mutations:
                    result = connection.execute(text("update know_facts set content=:after where editorial_key=:key and content=:before"),
                                                {"after": item["after"], "key": item["editorial_key"], "before": item["before"]})
                    if result.rowcount != 1:
                        raise RuntimeError(f"bounded update failed: {item['editorial_key']}")
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        after = {table: fingerprint(connection, table) for table in ("know_facts", "know_fact_evidence")}
        if before["know_fact_evidence"] != after["know_fact_evidence"]:
            raise RuntimeError("KNOW evidence changed")
        expected_updates = len(mutations) if write else 0
        return {"mode": "write" if write else "dry-run", "manifest_sha256": digest(pack),
                "planned_updates": len(mutations), "already_correct": len(already_correct),
                "executed_updates": expected_updates, "before": before, "after": after}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--allow-hosted", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run(args.database_url, args.write, args.allow_hosted), indent=2))
