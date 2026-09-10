"""Hash-bound, local-only publisher for frozen KNOW v1 editorial manifests."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy import create_engine, text

SUBJECTS = ("team_id", "club_venue_id", "venue_id", "fixture_id")
MODULES = {"CLUB", "SUPPORTERS", "MATCHDAY", "DONT_MISS", "GOOD_TO_KNOW"}


def canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def identity_sha256(row: dict) -> str:
    value = dict(row); value.pop("identity_sha256", None)
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest().upper()


def validate_manifest(pack: dict) -> dict:
    if pack.get("artifact_version") != "matchgoer-know-v1-publication":
        raise RuntimeError("artifact version mismatch")
    if pack.get("publication_state") != "FROZEN_PUBLICATION_CANDIDATE":
        raise RuntimeError("publication state mismatch")
    facts, evidence = pack.get("facts"), pack.get("evidence")
    if not isinstance(facts, list) or not isinstance(evidence, list) or not facts:
        raise RuntimeError("manifest facts/evidence structure is invalid")
    keys = {row.get("editorial_key") for row in facts}
    if None in keys or len(keys) != len(facts):
        raise RuntimeError("duplicate or missing editorial key")
    if any(row.get("identity_sha256") != identity_sha256(row) for row in [*facts, *evidence]):
        raise RuntimeError("row identity hash mismatch")
    for row in facts:
        if sum(row.get(key) is not None for key in SUBJECTS) != 1:
            raise RuntimeError("fact must have exactly one subject")
        if row.get("module") not in MODULES or not str(row.get("content", "")).strip():
            raise RuntimeError("invalid module/content")
        if row["module"] in {"CLUB", "SUPPORTERS"} and row.get("team_id") is None:
            raise RuntimeError("club/supporter fact must be team-owned")
        if row["module"] == "MATCHDAY" and row.get("club_venue_id") is None:
            raise RuntimeError("matchday fact must be club-venue-owned")
        if row.get("publication_status") != "PUBLISHED" or row.get("confidence") not in {"HIGH", "MEDIUM"}:
            raise RuntimeError("manifest contains an unpublishable fact")
        if not row.get("approved_at") or not str(row.get("approved_by", "")).strip():
            raise RuntimeError("manifest contains an unapproved fact")
    evidence_by_key = {key: [] for key in keys}
    for row in evidence:
        key = row.get("fact_editorial_key")
        if key not in evidence_by_key:
            raise RuntimeError("orphan evidence")
        if row.get("review_status") == "ACCEPTED" and row.get("disposition") == "SUPPORTS":
            evidence_by_key[key].append(row)
    for row in facts:
        accepted = evidence_by_key[row["editorial_key"]]
        minimum = 2 if row.get("claim_sensitivity") == "SENSITIVE" else 1
        distinct = {(x.get("source_type"), x.get("source_title"), x.get("source_url")) for x in accepted}
        if len(distinct) < minimum:
            raise RuntimeError(f"evidence policy failed: {row['editorial_key']}")
    return pack


def load_manifest(path: str, expected_sha256: str) -> tuple[dict, str]:
    artifact = Path(path).resolve()
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest().upper()
    if digest != expected_sha256.upper():
        raise RuntimeError("manifest checksum mismatch")
    return validate_manifest(json.loads(artifact.read_text(encoding="utf-8"))), digest


def require_local(database_url: str) -> None:
    host = (urlparse(database_url).hostname or "").casefold()
    if host not in {"localhost", "127.0.0.1", "::1"}:
        raise RuntimeError("KNOW v1 publisher is local-only")


FACT_FIELDS = ("editorial_key", *SUBJECTS, "module", "headline", "content", "display_order",
               "publication_status", "confidence", "claim_sensitivity", "reviewed_at", "review_after",
               "expires_at", "approved_at", "approved_by")
EVIDENCE_FIELDS = ("fact_editorial_key", "source_type", "source_title", "source_url", "source_date",
                   "evidence_note", "disposition", "review_status", "contributor_user_id")


def _scalar(value):
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    return value.isoformat() if isinstance(value, date) else value


def _state(connection, pack: dict) -> str:
    keys = [row["editorial_key"] for row in pack["facts"]]
    facts = connection.execute(text(f"SELECT {','.join(FACT_FIELDS)} FROM know_facts WHERE editorial_key = ANY(:keys)"), {"keys": keys}).mappings().all()
    if not facts:
        return "ABSENT"
    actual_facts = {tuple(_scalar(row[key]) for key in FACT_FIELDS) for row in facts}
    expected_facts = {tuple(_scalar(_dates(row).get(key)) for key in FACT_FIELDS) for row in pack["facts"]}
    evidence = connection.execute(text("""SELECT f.editorial_key fact_editorial_key,e.source_type,e.source_title,e.source_url,
        e.source_date,e.evidence_note,e.disposition,e.review_status,e.contributor_user_id
        FROM know_fact_evidence e JOIN know_facts f ON f.know_fact_id=e.know_fact_id
        WHERE f.editorial_key = ANY(:keys)"""), {"keys": keys}).mappings().all()
    actual_evidence = {tuple(_scalar(row[key]) for key in EVIDENCE_FIELDS) for row in evidence}
    expected_evidence = {tuple(_scalar(_dates(row).get(key)) for key in EVIDENCE_FIELDS) for row in pack["evidence"]}
    if actual_facts == expected_facts and actual_evidence == expected_evidence:
        return "EXACTLY_PRESENT"
    raise RuntimeError("manifest editorial keys exist with conflicting fact or evidence state")


def dry_run(database_url: str, pack: dict) -> dict:
    require_local(database_url)
    engine = create_engine(database_url, pool_pre_ping=True)
    with engine.connect() as connection:
        transaction = connection.begin()
        connection.execute(text("SET TRANSACTION READ ONLY"))
        state = _state(connection, pack)
        transaction.rollback()
    present = state == "EXACTLY_PRESENT"
    return {"state": state, "fact_inserts": 0 if present else len(pack["facts"]),
            "evidence_inserts": 0 if present else len(pack["evidence"]), "updates": 0, "deletes": 0}


def _dates(row: dict) -> dict:
    result = dict(row)
    for key in ("reviewed_at", "review_after", "expires_at", "source_date"):
        if result.get(key): result[key] = date.fromisoformat(result[key])
    if result.get("approved_at"): result["approved_at"] = datetime.fromisoformat(result["approved_at"])
    return result


def publish(database_url: str, pack: dict) -> dict:
    preflight = dry_run(database_url, pack)
    if preflight["state"] == "EXACTLY_PRESENT": return {**preflight, "idempotent": True}
    engine = create_engine(database_url, pool_pre_ping=True)
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"))
            ids = {}
            for raw in pack["facts"]:
                row = _dates(raw)
                ids[row["editorial_key"]] = connection.execute(text("""INSERT INTO know_facts
                    (editorial_key,team_id,club_venue_id,venue_id,fixture_id,module,headline,content,display_order,
                     publication_status,confidence,claim_sensitivity,reviewed_at,review_after,expires_at,approved_at,approved_by)
                    VALUES (:editorial_key,:team_id,:club_venue_id,:venue_id,:fixture_id,:module,:headline,:content,:display_order,
                     :publication_status,:confidence,:claim_sensitivity,:reviewed_at,:review_after,:expires_at,:approved_at,:approved_by)
                    RETURNING know_fact_id"""), row).scalar_one()
            for raw in pack["evidence"]:
                row = _dates(raw); row["know_fact_id"] = ids[row["fact_editorial_key"]]
                connection.execute(text("""INSERT INTO know_fact_evidence
                    (know_fact_id,source_type,source_title,source_url,source_date,evidence_note,disposition,review_status,contributor_user_id)
                    VALUES (:know_fact_id,:source_type,:source_title,:source_url,:source_date,:evidence_note,:disposition,:review_status,:contributor_user_id)"""), row)
            transaction.commit()
        except Exception:
            transaction.rollback(); raise
    return {**preflight, "state": "EXACTLY_PRESENT", "idempotent": False}


def rollback(database_url: str, pack: dict) -> dict:
    require_local(database_url)
    if dry_run(database_url, pack)["state"] != "EXACTLY_PRESENT":
        raise RuntimeError("rollback requires exact manifest state")
    engine = create_engine(database_url, pool_pre_ping=True)
    keys = [row["editorial_key"] for row in pack["facts"]]
    with engine.begin() as connection:
        deleted = connection.execute(text("DELETE FROM know_facts WHERE editorial_key = ANY(:keys)"), {"keys": keys}).rowcount
    return {"facts_deleted": deleted, "evidence_deleted_by_cascade": len(pack["evidence"])}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--execute", choices=("publish", "rollback"))
    parser.add_argument("--confirm-local-write", action="store_true")
    args = parser.parse_args()
    pack, digest = load_manifest(args.manifest, args.expected_sha256)
    if args.execute and not args.confirm_local_write:
        raise RuntimeError("write requires --confirm-local-write")
    result = publish(args.database_url, pack) if args.execute == "publish" else rollback(args.database_url, pack) if args.execute == "rollback" else dry_run(args.database_url, pack)
    print(json.dumps({"manifest_sha256": digest, **result}, indent=2, default=str))


if __name__ == "__main__": main()
