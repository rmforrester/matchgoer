"""Hash-bound, atomic publisher for reviewed DECIDE publication candidates."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import create_engine, text

from database_target import ExpectedDatabaseTarget, verify_database_target

SUBJECT_CATEGORIES = {
    "TEAM_PAIR": {"SIGNIFICANT_RIVALRY"},
    "VENUE": {"FOOTBALL_LANDMARK", "UNIQUE_SETTING", "CLASSIC_GROUND"},
    "TEAM": {"EXCEPTIONAL_SUPPORT"},
}
FACT_FIELDS = (
    "subject_type", "team_a_id", "team_b_id", "venue_id", "team_id",
    "attribute_key", "label", "explanation", "publication_status", "confidence",
    "lead_priority", "effective_from", "effective_to", "reviewed_at", "reviewed_by",
)
EVIDENCE_FIELDS = (
    "fact_id", "source_title", "source_url", "evidence_note", "disposition",
    "retrieved_at", "reviewed_at", "review_status",
)
MUTABLE_TABLES = {"decision_facts", "decision_evidence"}
TARGET_TABLES = ("teams", "venues", "decision_facts", "decision_evidence")
TARGET_COLUMNS = (("teams", "team_id"), ("venues", "venue_id"), ("decision_facts", "subject_type"), ("decision_evidence", "fact_id"))


class PublicationError(RuntimeError):
    pass


def digest(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest().upper()


def load_candidate(path: str | Path, expected_sha256: str) -> tuple[dict, str]:
    actual = digest(path)
    if actual != expected_sha256.upper():
        raise PublicationError("candidate SHA-256 mismatch")
    candidate = json.loads(Path(path).read_text(encoding="utf-8"))
    validate_candidate(candidate)
    return candidate, actual


def _required_text(row: dict, key: str, limit: int | None = None) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value.strip():
        raise PublicationError(f"missing or blank {key}")
    if limit is not None and len(value) > limit:
        raise PublicationError(f"{key} exceeds schema limit")
    return value


def _iso_datetime(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        raise PublicationError(f"missing {field}")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PublicationError(f"invalid {field}") from exc


def validate_candidate(candidate: dict) -> None:
    # The original v1 contract predates an explicit version field. Future v1
    # candidates may state schema_version=1 without changing its meaning.
    if candidate.get("schema_version", 1) != 1:
        raise PublicationError("unsupported DECIDE candidate schema_version")
    if candidate.get("catalogue_status") != "APPROVED_NOT_YET_PUBLISHED":
        raise PublicationError("candidate is not approved for publication preparation")
    facts = candidate.get("facts")
    if not isinstance(facts, list) or candidate.get("fact_count") != len(facts) or not facts:
        raise PublicationError("candidate fact_count/list mismatch")
    stable_keys: set[str] = set()
    identities: set[tuple] = set()
    evidence_identities: set[tuple] = set()
    for row in facts:
        key = _required_text(row, "stable_editorial_key", 200)
        if key in stable_keys:
            raise PublicationError("duplicate candidate stable editorial key")
        stable_keys.add(key)
        subject_type = row.get("subject_type")
        category = row.get("attribute_key")
        if subject_type not in SUBJECT_CATEGORIES or category not in SUBJECT_CATEGORIES[subject_type]:
            raise PublicationError("invalid DECIDE subject/category combination")
        ids = {name: row.get(name) for name in ("team_a_id", "team_b_id", "venue_id", "team_id")}
        if subject_type == "TEAM_PAIR":
            if not all(isinstance(ids[name], int) and ids[name] > 0 for name in ("team_a_id", "team_b_id")):
                raise PublicationError("rivalry requires two canonical team IDs")
            if ids["team_a_id"] >= ids["team_b_id"]:
                raise PublicationError("rivalry IDs must be distinct and canonical-order")
            if ids["venue_id"] is not None or ids["team_id"] is not None:
                raise PublicationError("malformed rivalry identity")
            owner = (ids["team_a_id"], ids["team_b_id"])
        elif subject_type == "TEAM":
            if not isinstance(ids["team_id"], int) or ids["team_id"] <= 0 or any(ids[name] is not None for name in ("team_a_id", "team_b_id", "venue_id")):
                raise PublicationError("malformed team identity")
            owner = (ids["team_id"],)
        else:
            if not isinstance(ids["venue_id"], int) or ids["venue_id"] <= 0 or any(ids[name] is not None for name in ("team_a_id", "team_b_id", "team_id")):
                raise PublicationError("malformed venue identity")
            owner = (ids["venue_id"],)
        identity = (subject_type, owner, category)
        if identity in identities:
            raise PublicationError("duplicate candidate canonical fact identity")
        identities.add(identity)
        _required_text(row, "label", 120)
        _required_text(row, "explanation", 300)
        if row.get("publication_status") != "PUBLISHED" or row.get("confidence") not in {"HIGH", "MEDIUM", "LOW"} or row.get("lead_priority") not in {"LEAD", "NORMAL"}:
            raise PublicationError("invalid DECIDE publication metadata")
        _iso_datetime(row.get("reviewed_at"), "reviewed_at")
        _required_text(row, "reviewed_by", 160)
        evidence_url = _required_text(row, "evidence_url")
        sources = row.get("evidence_sources")
        if not isinstance(sources, list) or not sources or any(not isinstance(value, str) or not value.strip() for value in sources):
            raise PublicationError("accepted evidence_sources are required")
        if len(sources) != len(set(sources)):
            raise PublicationError("duplicate candidate evidence source")
        if " | ".join(sources) != evidence_url:
            raise PublicationError("evidence_url does not match retained evidence_sources")
        evidence_identity = (key, evidence_url)
        if evidence_identity in evidence_identities:
            raise PublicationError("duplicate candidate evidence")
        evidence_identities.add(evidence_identity)


def _date(value):
    return date.fromisoformat(value) if isinstance(value, str) and value else value


def _datetime(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) and value else value


def _scalar(value):
    return value.isoformat() if isinstance(value, (date, datetime)) else value


def _same(actual: dict, expected: dict, fields: tuple[str, ...]) -> bool:
    return all(_scalar(actual.get(field)) == _scalar(expected.get(field)) for field in fields)


def _fact_identity(row: dict) -> dict:
    return {name: row.get(name) for name in ("subject_type", "team_a_id", "team_b_id", "venue_id", "team_id", "attribute_key")}


def _expected_fact(row: dict) -> dict:
    return {
        **{field: row.get(field) for field in FACT_FIELDS},
        "effective_from": _date(row.get("effective_from")),
        "effective_to": _date(row.get("effective_to")),
        "reviewed_at": _datetime(row.get("reviewed_at")),
    }


def _expected_evidence(row: dict, fact_id: int) -> dict:
    reviewed = _datetime(row["reviewed_at"])
    return {
        "fact_id": fact_id,
        "source_title": row["stable_editorial_key"],
        "source_url": row["evidence_url"],
        "evidence_note": f"Accepted provenance retained for {row['stable_editorial_key']}.",
        "disposition": "SUPPORTS",
        "retrieved_at": reviewed.date(),
        "reviewed_at": reviewed,
        "review_status": "ACCEPTED",
    }


def _find_fact(connection, row: dict):
    return connection.execute(text("""
        SELECT * FROM decision_facts
        WHERE subject_type=:subject_type AND attribute_key=:attribute_key
          AND team_a_id IS NOT DISTINCT FROM :team_a_id
          AND team_b_id IS NOT DISTINCT FROM :team_b_id
          AND venue_id IS NOT DISTINCT FROM :venue_id
          AND team_id IS NOT DISTINCT FROM :team_id
    """), _fact_identity(row)).mappings().all()


def preflight(connection, candidate: dict) -> dict:
    counts = {"decision_facts": {"insert": 0, "reuse": 0, "conflict": 0}, "decision_evidence": {"insert": 0, "reuse": 0, "conflict": 0}}
    fact_ids: dict[str, int | None] = {}
    conflicts: list[dict] = []
    for row in candidate["facts"]:
        ids = [value for value in (row.get("team_a_id"), row.get("team_b_id"), row.get("team_id")) if value is not None]
        if ids:
            found = connection.execute(text("SELECT team_id FROM teams WHERE team_id=ANY(:ids)"), {"ids": ids}).scalars().all()
            if set(found) != set(ids):
                raise PublicationError(f"missing canonical team for {row['stable_editorial_key']}")
        if row.get("venue_id") is not None:
            found = connection.execute(text("SELECT venue_id FROM venues WHERE venue_id=:id"), {"id": row["venue_id"]}).scalars().all()
            if found != [row["venue_id"]]:
                raise PublicationError(f"missing canonical venue for {row['stable_editorial_key']}")
        matches = _find_fact(connection, row)
        if len(matches) > 1:
            raise PublicationError(f"ambiguous DECIDE fact identity: {row['stable_editorial_key']}")
        if not matches:
            fact_ids[row["stable_editorial_key"]] = None
            counts["decision_facts"]["insert"] += 1
        elif _same(matches[0], _expected_fact(row), FACT_FIELDS):
            fact_ids[row["stable_editorial_key"]] = matches[0]["fact_id"]
            counts["decision_facts"]["reuse"] += 1
        else:
            counts["decision_facts"]["conflict"] += 1
            conflicts.append({"stable_editorial_key": row["stable_editorial_key"], "class": "FACT_CONTENT_CONFLICT"})
            continue
        fact_id = fact_ids[row["stable_editorial_key"]]
        if fact_id is None:
            claimed = connection.execute(
                text("SELECT * FROM decision_evidence WHERE source_title=:source_title"),
                {"source_title": row["stable_editorial_key"]},
            ).mappings().all()
            if claimed:
                counts["decision_evidence"]["conflict"] += 1
                conflicts.append({"stable_editorial_key": row["stable_editorial_key"], "class": "EVIDENCE_STABLE_KEY_ALREADY_OWNED"})
            else:
                counts["decision_evidence"]["insert"] += 1
            continue
        expected = _expected_evidence(row, fact_id)
        same_key = connection.execute(text("SELECT * FROM decision_evidence WHERE source_title=:source_title"), expected).mappings().all()
        exact = [value for value in same_key if _same(value, expected, EVIDENCE_FIELDS)]
        if len(exact) == 1 and len(same_key) == 1:
            counts["decision_evidence"]["reuse"] += 1
        elif same_key:
            counts["decision_evidence"]["conflict"] += 1
            conflicts.append({"stable_editorial_key": row["stable_editorial_key"], "class": "EVIDENCE_OWNERSHIP_OR_STATE_CONFLICT"})
        else:
            counts["decision_evidence"]["insert"] += 1
    if conflicts:
        raise PublicationError(f"DECIDE candidate conflicts: {conflicts}")
    return {"operations": counts, "fact_ids": fact_ids, "conflicts": [], "mutable_tables": sorted(MUTABLE_TABLES), "unrelated_mutations": 0}


def apply_candidate(connection, candidate: dict, plan: dict) -> list[str]:
    completed: list[str] = []
    for row in candidate["facts"]:
        key = row["stable_editorial_key"]
        fact_id = plan["fact_ids"][key]
        if fact_id is None:
            fact_id = connection.execute(text("""
                INSERT INTO decision_facts(
                    subject_type,team_a_id,team_b_id,venue_id,team_id,attribute_key,label,explanation,
                    publication_status,confidence,lead_priority,effective_from,effective_to,reviewed_at,reviewed_by
                ) VALUES(
                    :subject_type,:team_a_id,:team_b_id,:venue_id,:team_id,:attribute_key,:label,:explanation,
                    :publication_status,:confidence,:lead_priority,:effective_from,:effective_to,:reviewed_at,:reviewed_by
                ) RETURNING fact_id
            """), _expected_fact(row)).scalar_one()
            plan["fact_ids"][key] = fact_id
            completed.append("decision_facts")
        expected = _expected_evidence(row, fact_id)
        existing = connection.execute(text("SELECT * FROM decision_evidence WHERE source_title=:source_title"), expected).mappings().all()
        if not existing:
            connection.execute(text("""
                INSERT INTO decision_evidence(fact_id,source_title,source_url,evidence_note,disposition,retrieved_at,reviewed_at,review_status)
                VALUES(:fact_id,:source_title,:source_url,:evidence_note,:disposition,:retrieved_at,:reviewed_at,:review_status)
            """), expected)
            completed.append("decision_evidence")
    return completed


def _category_proof(connection, candidate: dict) -> dict:
    result = {}
    for category in sorted({row["attribute_key"] for row in candidate["facts"]}):
        row = next(value for value in candidate["facts"] if value["attribute_key"] == category)
        match = _find_fact(connection, row)
        result[category] = {"stable_editorial_key": row["stable_editorial_key"], "loaded": len(match) == 1 and match[0]["publication_status"] == "PUBLISHED"}
    if not all(item["loaded"] for item in result.values()):
        raise PublicationError("temporary serving/model reconciliation failed")
    return result


def execute(database_url: str, candidate: dict, candidate_sha256: str, mode: str, *, confirm_write: bool = False, failure_hook=None, expected_target=None, target_environment=None) -> dict:
    if mode == "write" and not confirm_write:
        raise PublicationError("write requires --confirm-write")
    if mode not in {"dry-run", "rollback-only", "write"}:
        raise PublicationError("unsupported execution mode")
    engine = create_engine(database_url, pool_pre_ping=True)
    completed: list[str] = []
    try:
        with engine.connect() as connection:
            target_receipt = None
            transaction = connection.begin()
            try:
                if mode == "dry-run":
                    connection.execute(text("SET TRANSACTION READ ONLY"))
                else:
                    connection.execute(text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"))
                if mode != "dry-run" or expected_target is not None:
                    target_receipt = verify_database_target(connection, expected_target, target_environment)
                baseline = {
                    "decision_facts": connection.execute(text("SELECT count(*) FROM decision_facts")).scalar_one(),
                    "decision_evidence": connection.execute(text("SELECT count(*) FROM decision_evidence")).scalar_one(),
                }
                plan = preflight(connection, candidate)
                if mode == "dry-run":
                    transaction.rollback()
                    return _receipt(candidate_sha256, mode, plan, baseline, "ROLLED_BACK_READ_ONLY", False, completed, target=target_receipt)
                completed = apply_candidate(connection, candidate, plan)
                if failure_hook:
                    failure_hook(connection)
                temporary_counts = {
                    "decision_facts": connection.execute(text("SELECT count(*) FROM decision_facts")).scalar_one(),
                    "decision_evidence": connection.execute(text("SELECT count(*) FROM decision_evidence")).scalar_one(),
                }
                second = preflight(connection, candidate)
                expected = {"decision_facts": {"insert": 0, "reuse": len(candidate["facts"]), "conflict": 0}, "decision_evidence": {"insert": 0, "reuse": len(candidate["facts"]), "conflict": 0}}
                if second["operations"] != expected:
                    raise PublicationError("temporary idempotence reconciliation failed")
                serving = _category_proof(connection, candidate)
                if mode == "rollback-only":
                    transaction.rollback(); outcome, persistent = "INTENTIONAL_ROLLBACK", False
                else:
                    transaction.commit(); outcome, persistent = "COMMITTED", True
                return _receipt(candidate_sha256, mode, plan, baseline, outcome, persistent, completed, temporary_counts, second["operations"], serving, target_receipt)
            except Exception:
                if transaction.is_active:
                    transaction.rollback()
                raise
    except Exception as exc:
        return {"status":"FAIL","candidate_sha256":candidate_sha256,"execution_mode":mode,"exception_type":type(exc).__name__,"exception_message":str(exc),"transaction_outcome":"ROLLED_BACK","persistent_mutation":False,"completed_logical_operations":completed}


def _receipt(sha, mode, plan, baseline, outcome, persistent, completed, temporary_counts=None, idempotence=None, serving=None, target=None):
    return {"status":"PASS","candidate_sha256":sha,"execution_mode":mode,"database_target":target,"baseline":baseline,"operations":plan["operations"],"conflicts":plan["conflicts"],"mutable_tables":plan["mutable_tables"],"unrelated_mutations":plan["unrelated_mutations"],"temporary_counts":temporary_counts,"temporary_idempotence":idempotence,"serving_model_proof":serving,"transaction_outcome":outcome,"persistent_mutation":persistent,"completed_logical_operations":completed}


def load_database_url(env_path: str | Path) -> str:
    for line in Path(env_path).read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("DATABASE_URL="):
            value = line.split("=", 1)[1].strip().strip('"').strip("'")
            if value:
                return value
    raise PublicationError("DATABASE_URL is absent")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--mode", choices=("dry-run", "rollback-only", "write"), default="dry-run")
    parser.add_argument("--confirm-write", action="store_true")
    parser.add_argument("--receipt")
    parser.add_argument("--expected-database")
    parser.add_argument("--expected-schema", default="public")
    parser.add_argument("--expected-environment")
    parser.add_argument("--target-environment")
    args = parser.parse_args()
    candidate, actual_sha = load_candidate(args.candidate, args.expected_sha256)
    database_url = load_database_url(args.env_file)
    expected = ExpectedDatabaseTarget(args.expected_database, args.expected_schema, args.expected_environment, TARGET_TABLES, TARGET_COLUMNS) if args.expected_database and args.expected_environment else None
    result = execute(database_url, candidate, actual_sha, args.mode, confirm_write=args.confirm_write, expected_target=expected, target_environment=args.target_environment)
    payload = json.dumps(result, indent=2, default=str, sort_keys=True) + "\n"
    if args.receipt:
        Path(args.receipt).write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
