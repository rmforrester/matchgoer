"""Reusable exact-set publisher for immutable KNOW publication candidates."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy import bindparam, create_engine, text

CONTENT_KEYS = ("venue_guide_facts", "pre_match_spots", "pre_match_spot_evidence")
BUSINESS_STATUSES = {"OPEN", "UNKNOWN", "CLOSED", "NOT_APPLICABLE"}
FACT_FIELDS = ("club_venue_id", "section", "topic", "content", "source_type", "source_label", "source_url",
               "reviewed_at", "confidence", "status", "review_after", "expires_at", "display_order")
SPOT_FIELDS = ("club_venue_id", "display_name", "classification", "audience", "supporting_line", "maps_destination",
               "confidence", "status", "business_status", "reviewed_at", "review_after", "display_order",
               "approved_at", "approved_by")
EVIDENCE_FIELDS = ("source_type", "source_url", "source_date", "disposition", "evidence_note", "review_status")


@dataclass(frozen=True)
class Candidate:
    pack: dict
    sha256: str
    version: str
    counts: dict[str, int]

    @property
    def mutations(self):
        return sum(self.counts.values())


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _identity_valid(row):
    value = dict(row)
    expected = value.pop("identity_sha256", None)
    return expected == hashlib.sha256(canonical(value).encode("utf-8")).hexdigest().upper()


def _date(value):
    if not value or isinstance(value, date):
        return value
    return date.fromisoformat(value + "-01" if len(value) == 7 else value)


def _datetime(value):
    return value if not value or isinstance(value, datetime) else datetime.fromisoformat(value)


def _scalar(value):
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    return value.isoformat() if isinstance(value, date) else value


def validate_pack(pack, expected_version):
    if pack.get("artifact_version") != expected_version:
        raise RuntimeError("artifact version mismatch")
    legacy_batch_1 = expected_version == "english-know-content-v1"
    if not legacy_batch_1 and pack.get("publication_state") != "PUBLICATION_CANDIDATE":
        raise RuntimeError("publication state mismatch")
    if not all(isinstance(pack.get(key), list) for key in ("clubs", *CONTENT_KEYS)):
        raise RuntimeError("candidate structure mismatch")
    clubs = pack["clubs"]
    if not clubs:
        raise RuntimeError("candidate must contain clubs")
    ownership = {(row.get("team_id"), row.get("club_venue_id"), row.get("venue_id")) for row in clubs}
    if len(ownership) != len(clubs) or None in {value for owner in ownership for value in owner}:
        raise RuntimeError("duplicate or incomplete club identity")
    if any(row.get("publication_eligibility", "PUBLICATION_ELIGIBLE") != "PUBLICATION_ELIGIBLE" for row in clubs):
        raise RuntimeError("ineligible club in publication candidate")
    owner_by_relationship = {row["club_venue_id"]: (row["team_id"], row["venue_id"]) for row in clubs}
    rows = [*pack["venue_guide_facts"], *pack["pre_match_spots"], *pack["pre_match_spot_evidence"]]
    if not all(_identity_valid(row) for row in rows):
        raise RuntimeError("per-row identity hash mismatch")
    for row in [*pack["venue_guide_facts"], *pack["pre_match_spots"]]:
        if owner_by_relationship.get(row.get("club_venue_id")) != (row.get("team_id"), row.get("venue_id")):
            raise RuntimeError("unsupported content owner")
    if any(row.get("confidence") not in {"high", "medium"} or row.get("status") != "current"
           for row in pack["venue_guide_facts"]):
        raise RuntimeError("unpublishable guide fact")
    if any(row.get("confidence") not in {"HIGH", "MEDIUM"} or row.get("status") != "CURRENT"
           or row.get("business_status") not in BUSINESS_STATUSES
           or not str(row.get("maps_destination", "")).strip() or not row.get("approved_at") or not row.get("approved_by")
           for row in pack["pre_match_spots"]):
        raise RuntimeError("unpublishable/unapproved pre-match spot")
    if any("RESEARCH_REQUIRED" in canonical(row) for row in rows):
        raise RuntimeError("research-required content present")
    fact_keys = [(row["club_venue_id"], row["topic"]) for row in pack["venue_guide_facts"]]
    spot_keys = [(row["club_venue_id"], row["display_name"].casefold()) for row in pack["pre_match_spots"]]
    if len(fact_keys) != len(set(fact_keys)):
        raise RuntimeError("duplicate guide topic")
    if len(spot_keys) != len(set(spot_keys)):
        raise RuntimeError("duplicate pre-match spot")
    spot_hashes = {row["identity_sha256"] for row in pack["pre_match_spots"]}
    evidence_owners = {row.get("spot_identity_sha256") for row in pack["pre_match_spot_evidence"]}
    if evidence_owners != spot_hashes:
        raise RuntimeError("orphan or missing pre-match spot evidence")
    return pack


def load_candidate(path, *, expected_sha256, expected_version):
    artifact = Path(path).resolve()
    if not artifact.is_file():
        raise RuntimeError(f"candidate missing: {artifact}")
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest().upper()
    if digest != expected_sha256.upper():
        raise RuntimeError(f"artifact hash mismatch: {digest}")
    pack = validate_pack(json.loads(artifact.read_text(encoding="utf-8")), expected_version)
    return Candidate(pack, digest, expected_version, {key: len(pack[key]) for key in CONTENT_KEYS})


def table_counts(connection):
    return {table: connection.execute(text(f'SELECT count(*) FROM "{table}"')).scalar_one()
            for table in ("club_venues", *CONTENT_KEYS)}


def verify_relationships(connection, candidate):
    clubs = candidate.pack["clubs"]
    ids = [row["club_venue_id"] for row in clubs]
    team_ids = [row["team_id"] for row in clubs]
    selected = connection.execute(text("""
        SELECT club_venue_id,team_id,venue_id,relationship_type,status,valid_from,valid_until
        FROM club_venues WHERE club_venue_id IN :ids ORDER BY club_venue_id
    """).bindparams(bindparam("ids", expanding=True)), {"ids": ids}).mappings().all()
    expected = {(row["club_venue_id"], row["team_id"], row["venue_id"]) for row in clubs}
    actual = {(row["club_venue_id"], row["team_id"], row["venue_id"]) for row in selected}
    if actual != expected:
        raise RuntimeError("CLUB_VENUE artifact identity mismatch")
    if any(row["relationship_type"] != "HOME" or row["status"] != "CURRENT"
           or (row["valid_from"] and row["valid_from"] > date.today())
           or (row["valid_until"] and row["valid_until"] < date.today()) for row in selected):
        raise RuntimeError("non-current/non-HOME/out-of-validity relationship")
    eligible = connection.execute(text("""
        SELECT team_id,count(*) AS count FROM club_venues
        WHERE team_id IN :team_ids AND relationship_type='HOME' AND status='CURRENT'
          AND (valid_from IS NULL OR valid_from <= CURRENT_DATE)
          AND (valid_until IS NULL OR valid_until >= CURRENT_DATE)
        GROUP BY team_id
    """).bindparams(bindparam("team_ids", expanding=True)), {"team_ids": team_ids}).mappings().all()
    if {row["team_id"]: row["count"] for row in eligible} != {team_id: 1 for team_id in team_ids}:
        raise RuntimeError("ambiguous/missing current HOME relationship")


def _actual_sets(connection, candidate):
    pack = candidate.pack
    ids = [row["club_venue_id"] for row in pack["clubs"]]
    facts = connection.execute(text(f"SELECT fact_id,{','.join(FACT_FIELDS)} FROM venue_guide_facts WHERE club_venue_id IN :ids")
                               .bindparams(bindparam("ids", expanding=True)), {"ids": ids}).mappings().all()
    spots = connection.execute(text(f"SELECT pre_match_spot_id,{','.join(SPOT_FIELDS)} FROM pre_match_spots WHERE club_venue_id IN :ids")
                               .bindparams(bindparam("ids", expanding=True)), {"ids": ids}).mappings().all()
    expected_hash = {(row["club_venue_id"], row["display_name"]): row["identity_sha256"] for row in pack["pre_match_spots"]}
    identity_by_id = {row["pre_match_spot_id"]: expected_hash[(row["club_venue_id"], row["display_name"])] for row in spots
                      if (row["club_venue_id"], row["display_name"]) in expected_hash}
    spot_ids = list(identity_by_id)
    evidence = [] if not spot_ids else connection.execute(text(f"SELECT pre_match_spot_id,{','.join(EVIDENCE_FIELDS)} FROM pre_match_spot_evidence WHERE pre_match_spot_id IN :ids")
        .bindparams(bindparam("ids", expanding=True)), {"ids": spot_ids}).mappings().all()
    actual_facts = {tuple(_scalar(row[field]) for field in FACT_FIELDS) for row in facts}
    expected_facts = {tuple(_scalar(_date(row[field]) if field in {"reviewed_at", "review_after", "expires_at"} else row[field]) for field in FACT_FIELDS) for row in pack["venue_guide_facts"]}
    actual_spots = {tuple(_scalar(row[field]) for field in SPOT_FIELDS) for row in spots}
    expected_spots = {tuple(_scalar(_datetime(row[field]) if field == "approved_at" else _date(row[field]) if field in {"reviewed_at", "review_after"} else row[field]) for field in SPOT_FIELDS) for row in pack["pre_match_spots"]}
    actual_evidence = {(identity_by_id[row["pre_match_spot_id"]],) + tuple(_scalar(row[field]) for field in EVIDENCE_FIELDS) for row in evidence}
    expected_evidence = {(row["spot_identity_sha256"],) + tuple(_scalar(_date(row[field]) if field == "source_date" else row[field]) for field in EVIDENCE_FIELDS) for row in pack["pre_match_spot_evidence"]}
    return facts, spots, evidence, (actual_facts, expected_facts, actual_spots, expected_spots, actual_evidence, expected_evidence)


def candidate_state(connection, candidate):
    verify_relationships(connection, candidate)
    facts, spots, evidence, sets = _actual_sets(connection, candidate)
    counts = (len(facts), len(spots), len(evidence))
    expected = tuple(candidate.counts[key] for key in CONTENT_KEYS)
    if counts == (0, 0, 0):
        return "ABSENT"
    if counts == expected and sets[0] == sets[1] and sets[2] == sets[3] and sets[4] == sets[5]:
        return "EXACTLY_PRESENT"
    raise RuntimeError(f"unexpected pre-existing conflicting content: facts={counts[0]} spots={counts[1]} evidence={counts[2]}")


def dry_run(database_url, candidate):
    engine = create_engine(database_url, pool_pre_ping=True)
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(text("SET TRANSACTION READ ONLY"))
            state = candidate_state(connection, candidate)
            current = table_counts(connection)
        finally:
            transaction.rollback()
    absent = state == "ABSENT"
    return {"candidate_state": state, "insert": {key: value if absent else 0 for key, value in candidate.counts.items()},
            "safe_existing": {key: 0 if absent else value for key, value in candidate.counts.items()},
            "updates": 0, "deletes": 0, "blocking": 0,
            "total_proposed_mutations": candidate.mutations if absent else 0,
            "existing_counts": current, "database_writes": 0}


def _insert(connection, candidate):
    pack = candidate.pack
    spot_ids = {}
    for row in pack["venue_guide_facts"]:
        connection.execute(text("""INSERT INTO venue_guide_facts
            (club_venue_id,section,topic,content,source_type,source_label,source_url,reviewed_at,confidence,status,review_after,expires_at,display_order)
            VALUES (:club_venue_id,:section,:topic,:content,:source_type,:source_label,:source_url,:reviewed_at,:confidence,:status,:review_after,:expires_at,:display_order)"""),
            {**row, "reviewed_at": _date(row["reviewed_at"]), "review_after": _date(row["review_after"]), "expires_at": _date(row["expires_at"])})
    for row in pack["pre_match_spots"]:
        spot_ids[row["identity_sha256"]] = connection.execute(text("""INSERT INTO pre_match_spots
            (club_venue_id,display_name,classification,audience,supporting_line,maps_destination,confidence,status,business_status,reviewed_at,review_after,display_order,approved_at,approved_by)
            VALUES (:club_venue_id,:display_name,:classification,:audience,:supporting_line,:maps_destination,:confidence,:status,:business_status,:reviewed_at,:review_after,:display_order,:approved_at,:approved_by)
            RETURNING pre_match_spot_id"""), {**row, "reviewed_at": _date(row["reviewed_at"]), "review_after": _date(row["review_after"]), "approved_at": _datetime(row["approved_at"])}).scalar_one()
    for row in pack["pre_match_spot_evidence"]:
        connection.execute(text("""INSERT INTO pre_match_spot_evidence
            (pre_match_spot_id,source_type,source_url,source_date,disposition,evidence_note,review_status)
            VALUES (:pre_match_spot_id,:source_type,:source_url,:source_date,:disposition,:evidence_note,:review_status)"""),
            {**row, "pre_match_spot_id": spot_ids[row["spot_identity_sha256"]], "source_date": _date(row["source_date"])})


def execute_write(database_url, candidate):
    preflight = dry_run(database_url, candidate)
    if preflight["candidate_state"] != "ABSENT":
        raise RuntimeError("write requires fully absent candidate state")
    engine = create_engine(database_url, pool_pre_ping=True)
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"))
            if candidate_state(connection, candidate) != "ABSENT":
                raise RuntimeError("in-transaction candidate state changed")
            before = table_counts(connection)
            _insert(connection, candidate)
            if candidate_state(connection, candidate) != "EXACTLY_PRESENT":
                raise RuntimeError("post-insert exact-set reconciliation failed")
            after = table_counts(connection)
            expected = {"club_venues": 0, **candidate.counts}
            if {key: after[key] - before[key] for key in before} != expected:
                raise RuntimeError("physical delta mismatch")
            transaction.commit()
        except Exception:
            if transaction.is_active:
                transaction.rollback()
            raise
    return {"preflight": preflight, "delta": expected, "candidate_state": "EXACTLY_PRESENT", "database_writes": candidate.mutations}


def execute_rollback(database_url, candidate):
    engine = create_engine(database_url, pool_pre_ping=True)
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"))
            try:
                state = candidate_state(connection, candidate)
            except RuntimeError as error:
                raise RuntimeError("rollback refused: candidate exact set has drifted or is absent") from error
            if state != "EXACTLY_PRESENT":
                raise RuntimeError("rollback refused: candidate exact set has drifted or is absent")
            facts, spots, evidence, _ = _actual_sets(connection, candidate)
            evidence_ids = connection.execute(text("SELECT evidence_id FROM pre_match_spot_evidence WHERE pre_match_spot_id IN :ids")
                .bindparams(bindparam("ids", expanding=True)), {"ids": [row["pre_match_spot_id"] for row in spots]}).scalars().all()
            connection.execute(text("DELETE FROM pre_match_spot_evidence WHERE evidence_id IN :ids").bindparams(bindparam("ids", expanding=True)), {"ids": evidence_ids})
            connection.execute(text("DELETE FROM pre_match_spots WHERE pre_match_spot_id IN :ids").bindparams(bindparam("ids", expanding=True)), {"ids": [row["pre_match_spot_id"] for row in spots]})
            connection.execute(text("DELETE FROM venue_guide_facts WHERE fact_id IN :ids").bindparams(bindparam("ids", expanding=True)), {"ids": [row["fact_id"] for row in facts]})
            if candidate_state(connection, candidate) != "ABSENT":
                raise RuntimeError("post-rollback candidate state mismatch")
            transaction.commit()
        except Exception:
            if transaction.is_active:
                transaction.rollback()
            raise
    return {"deleted": candidate.counts, "club_venues": 0, "updates": 0, "candidate_state": "ABSENT"}
