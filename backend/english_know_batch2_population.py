"""Shared safety controls for the immutable England KNOW Batch 2 population."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy import bindparam, create_engine, text

ROOT = Path(__file__).resolve().parents[1]
APPROVED_ARTIFACT = ROOT / "reports/research/english-know/v4/english-know-batch2-publication-candidate.json"
EXPECTED_SHA256 = "54B80A7268413FF7C7D6DD14DB22B4924B3DC758C0945685EA4926065870B2B1"
EXPECTED_VERSION = "english-know-content-v2-publication-candidate"
EXPECTED_COUNTS = {"venue_guide_facts": 30, "pre_match_spots": 18, "pre_match_spot_evidence": 30}
LIVE_BATCH1_TEAM_IDS = {33, 42, 1333, 1359, 4692, 7656, 8657, 8659}
EXCLUDED_TEAM_IDS = {1832, 9010}
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
WITHHELD_FACT_IDS = {
    "norwich-digital-entry", "portsmouth-ticket-route", "grimsby-ticket-portal",
    "salford-ticket-route", "altrincham-ticket-route", "fcum-ticket-route",
    "southend-ticket-route",
}
WITHHELD_SPOTS = {
    (1844, "Buck's Bar"), (7645, "Hanwell Town clubhouse bar"),
    (7745, "Town Bar (Clubhouse)"),
}
REMOVED_EVIDENCE_URLS = {
    "https://historicengland.org.uk/images-books/photos/item/FGE01/01/041/005",
    "https://www.footballnonsense.co.uk/victoria-park-hartlepool/",
    "https://torquayunited.com/supporter-information-boots-laces/",
    "https://thefsa.org.uk/wp-content/uploads/2026/01/5.FA-WNL-Supporters-Guide_Division-One-South-East.pdf",
}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def validate_identity(row):
    value = dict(row)
    expected = value.pop("identity_sha256", None)
    return expected == hashlib.sha256(canonical(value).encode("utf-8")).hexdigest().upper()


def parsed_date(value):
    if not value:
        return None
    if isinstance(value, date):
        return value
    if len(value) == 7:
        value += "-01"
    return date.fromisoformat(value)


def parsed_datetime(value):
    if not value or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)


def scalar(value):
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def _assert_reviewed_decisions(pack):
    facts = {row["source_item_id"]: row for row in pack["venue_guide_facts"]}
    spots = {(row["team_id"], row["display_name"]): row for row in pack["pre_match_spots"]}
    if set(facts) & WITHHELD_FACT_IDS:
        raise RuntimeError("withheld/rejected guide fact present")
    if set(spots) & WITHHELD_SPOTS:
        raise RuntimeError("withheld pre-match spot present")
    expected_spots = {
        (58, "SE16 Bus Bar"): ("SUPPORTER_SPOT", "HIGH"),
        (1355, "The Shepherds Crook"): ("SUPPORTER_SPOT", "HIGH"),
        (1366, "Corner Flag Supporters Club"): ("SUPPORTER_SPOT", "HIGH"),
        (1837, "The Turf"): ("SUPPORTER_SPOT", "HIGH"),
        (34, "St James’ STACK"): ("CLUB_MATCHDAY_VENUE", "HIGH"),
        (1343, "Bantams in the Courtyard FanZone"): ("CLUB_MATCHDAY_VENUE", "HIGH"),
    }
    for key, expected in expected_spots.items():
        row = spots.get(key)
        if not row or (row["classification"], row["confidence"]) != expected:
            raise RuntimeError(f"reviewed spot decision mismatch: {key}")
    evidence_urls = {row["source_url"] for row in pack["pre_match_spot_evidence"]}
    if evidence_urls & REMOVED_EVIDENCE_URLS:
        raise RuntimeError("obsolete/dead evidence present")
    hartlepool = spots[(1366, "Corner Flag Supporters Club")]
    hartlepool_sources = {
        row["source_url"] for row in pack["pre_match_spot_evidence"]
        if row["spot_identity_sha256"] == hartlepool["identity_sha256"]
    }
    if hartlepool_sources != {
        "https://www.hartlepoolunited.co.uk/club/supporters-association/",
        "https://www.hufcsupporterstrust.org.uk/fans-make-clubs",
    }:
        raise RuntimeError("Hartlepool evidence set mismatch")


def validate_pack(pack):
    if pack.get("artifact_version") != EXPECTED_VERSION or pack.get("publication_state") != "PUBLICATION_CANDIDATE":
        raise RuntimeError("artifact version/publication state mismatch")
    if len(pack.get("clubs", [])) != 25 or any(len(pack.get(name, [])) != count for name, count in EXPECTED_COUNTS.items()):
        raise RuntimeError("artifact record count mismatch")
    team_ids = {row["team_id"] for row in pack["clubs"]}
    if len(team_ids) != 25 or team_ids & LIVE_BATCH1_TEAM_IDS or team_ids & EXCLUDED_TEAM_IDS:
        raise RuntimeError("club identity/exclusion mismatch")
    rows = pack["venue_guide_facts"] + pack["pre_match_spots"] + pack["pre_match_spot_evidence"]
    if not all(validate_identity(row) for row in rows):
        raise RuntimeError("per-row identity hash mismatch")
    if any(row["team_id"] not in team_ids or row["club_venue_id"] not in {club["club_venue_id"] for club in pack["clubs"]}
           for row in pack["venue_guide_facts"] + pack["pre_match_spots"]):
        raise RuntimeError("unsupported content owner")
    if any(row["confidence"] not in {"high", "medium"} or row["status"] != "current" for row in pack["venue_guide_facts"]):
        raise RuntimeError("unpublishable guide fact")
    if any(row["confidence"] not in {"HIGH", "MEDIUM"} or row["status"] != "CURRENT"
           or not row["maps_destination"].strip() or not row.get("approved_at") or not row.get("approved_by")
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
    evidence_owners = {row["spot_identity_sha256"] for row in pack["pre_match_spot_evidence"]}
    if not evidence_owners <= spot_hashes or evidence_owners != spot_hashes:
        raise RuntimeError("orphan or unsupported evidence")
    _assert_reviewed_decisions(pack)
    return pack


def load_pack(path=None, *, test_only=False, expected_sha256=None):
    artifact = Path(path).resolve() if path else APPROVED_ARTIFACT.resolve()
    approved = APPROVED_ARTIFACT.resolve()
    if not test_only and artifact != approved:
        raise RuntimeError(f"real operation requires approved artifact path: {approved}")
    if not artifact.is_file():
        raise RuntimeError(f"approved artifact missing: {artifact}")
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest().upper()
    expected = expected_sha256 if test_only and expected_sha256 else EXPECTED_SHA256
    if digest != expected:
        raise RuntimeError(f"artifact hash mismatch: {digest}")
    return validate_pack(json.loads(artifact.read_text(encoding="utf-8"))), digest


FACT_FIELDS = ("club_venue_id", "section", "topic", "content", "source_type", "source_label", "source_url",
               "reviewed_at", "confidence", "status", "review_after", "expires_at", "display_order")
SPOT_FIELDS = ("club_venue_id", "display_name", "classification", "audience", "supporting_line", "maps_destination",
               "confidence", "status", "business_status", "reviewed_at", "review_after", "display_order",
               "approved_at", "approved_by")
EVIDENCE_FIELDS = ("source_type", "source_url", "source_date", "disposition", "evidence_note", "review_status")


def table_counts(connection):
    return {table: connection.execute(text(f'SELECT count(*) FROM "{table}"')).scalar_one()
            for table in ("club_venues", "venue_guide_facts", "pre_match_spots", "pre_match_spot_evidence")}


def verify_relationships(connection, pack):
    ids = [row["club_venue_id"] for row in pack["clubs"]]
    team_ids = [row["team_id"] for row in pack["clubs"]]
    selected = connection.execute(text("""
        SELECT club_venue_id,team_id,venue_id,relationship_type,status,valid_from,valid_until
        FROM club_venues WHERE club_venue_id IN :ids ORDER BY club_venue_id
    """).bindparams(bindparam("ids", expanding=True)), {"ids": ids}).mappings().all()
    expected = {(row["club_venue_id"], row["team_id"], row["venue_id"]) for row in pack["clubs"]}
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


def _actual_sets(connection, pack):
    ids = [row["club_venue_id"] for row in pack["clubs"]]
    facts = connection.execute(text(f"SELECT fact_id,{','.join(FACT_FIELDS)} FROM venue_guide_facts WHERE club_venue_id IN :ids")
                               .bindparams(bindparam("ids", expanding=True)), {"ids": ids}).mappings().all()
    spots = connection.execute(text(f"SELECT pre_match_spot_id,{','.join(SPOT_FIELDS)} FROM pre_match_spots WHERE club_venue_id IN :ids")
                               .bindparams(bindparam("ids", expanding=True)), {"ids": ids}).mappings().all()
    expected_hash = {(row["club_venue_id"], row["display_name"]): row["identity_sha256"] for row in pack["pre_match_spots"]}
    actual_hash = {(row["club_venue_id"], row["display_name"]): expected_hash.get((row["club_venue_id"], row["display_name"])) for row in spots}
    identity_by_id = {row["pre_match_spot_id"]: actual_hash[(row["club_venue_id"], row["display_name"])] for row in spots if actual_hash[(row["club_venue_id"], row["display_name"])]}
    spot_ids = list(identity_by_id)
    evidence = [] if not spot_ids else connection.execute(text(f"SELECT pre_match_spot_id,{','.join(EVIDENCE_FIELDS)} FROM pre_match_spot_evidence WHERE pre_match_spot_id IN :ids")
        .bindparams(bindparam("ids", expanding=True)), {"ids": spot_ids}).mappings().all()
    actual_facts = {tuple(scalar(row[field]) for field in FACT_FIELDS) for row in facts}
    expected_facts = {tuple(scalar(parsed_date(row[field]) if field in {"reviewed_at", "review_after", "expires_at"} else row[field]) for field in FACT_FIELDS) for row in pack["venue_guide_facts"]}
    actual_spots = {tuple(scalar(row[field]) for field in SPOT_FIELDS) for row in spots}
    expected_spots = {tuple(scalar(parsed_datetime(row[field]) if field == "approved_at" else parsed_date(row[field]) if field in {"reviewed_at", "review_after"} else row[field]) for field in SPOT_FIELDS) for row in pack["pre_match_spots"]}
    actual_evidence = {(identity_by_id[row["pre_match_spot_id"]],) + tuple(scalar(row[field]) for field in EVIDENCE_FIELDS) for row in evidence}
    expected_evidence = {(row["spot_identity_sha256"],) + tuple(scalar(parsed_date(row[field]) if field == "source_date" else row[field]) for field in EVIDENCE_FIELDS) for row in pack["pre_match_spot_evidence"]}
    return facts, spots, evidence, (actual_facts, expected_facts, actual_spots, expected_spots, actual_evidence, expected_evidence)


def candidate_state(connection, pack):
    verify_relationships(connection, pack)
    facts, spots, evidence, sets = _actual_sets(connection, pack)
    counts = (len(facts), len(spots), len(evidence))
    if counts == (0, 0, 0):
        return "ABSENT"
    if counts == (30, 18, 30) and sets[0] == sets[1] and sets[2] == sets[3] and sets[4] == sets[5]:
        return "EXACTLY_PRESENT"
    raise RuntimeError(f"unexpected pre-existing conflicting content: facts={counts[0]} spots={counts[1]} evidence={counts[2]}")


def dry_run(database_url, pack):
    engine = create_engine(database_url, pool_pre_ping=True)
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(text("SET TRANSACTION READ ONLY"))
            state = candidate_state(connection, pack)
            current = table_counts(connection)
        finally:
            transaction.rollback()
    absent = state == "ABSENT"
    return {
        "candidate_state": state,
        "insert": {name: count if absent else 0 for name, count in EXPECTED_COUNTS.items()},
        "safe_existing": {name: 0 if absent else count for name, count in EXPECTED_COUNTS.items()},
        "updates": 0, "deletes": 0, "blocking": 0,
        "total_proposed_mutations": 78 if absent else 0,
        "existing_counts": current, "database_writes": 0,
    }


def insert_candidate(connection, pack):
    spot_ids = {}
    for row in pack["venue_guide_facts"]:
        connection.execute(text("""INSERT INTO venue_guide_facts
            (club_venue_id,section,topic,content,source_type,source_label,source_url,reviewed_at,confidence,status,review_after,expires_at,display_order)
            VALUES (:club_venue_id,:section,:topic,:content,:source_type,:source_label,:source_url,:reviewed_at,:confidence,:status,:review_after,:expires_at,:display_order)"""),
            {**row, "reviewed_at": parsed_date(row["reviewed_at"]), "review_after": parsed_date(row["review_after"]), "expires_at": parsed_date(row["expires_at"])})
    for row in pack["pre_match_spots"]:
        spot_ids[row["identity_sha256"]] = connection.execute(text("""INSERT INTO pre_match_spots
            (club_venue_id,display_name,classification,audience,supporting_line,maps_destination,confidence,status,business_status,reviewed_at,review_after,display_order,approved_at,approved_by)
            VALUES (:club_venue_id,:display_name,:classification,:audience,:supporting_line,:maps_destination,:confidence,:status,:business_status,:reviewed_at,:review_after,:display_order,:approved_at,:approved_by)
            RETURNING pre_match_spot_id"""), {**row, "reviewed_at": parsed_date(row["reviewed_at"]), "review_after": parsed_date(row["review_after"]), "approved_at": parsed_datetime(row["approved_at"])}).scalar_one()
    for row in pack["pre_match_spot_evidence"]:
        connection.execute(text("""INSERT INTO pre_match_spot_evidence
            (pre_match_spot_id,source_type,source_url,source_date,disposition,evidence_note,review_status)
            VALUES (:pre_match_spot_id,:source_type,:source_url,:source_date,:disposition,:evidence_note,:review_status)"""),
            {**row, "pre_match_spot_id": spot_ids[row["spot_identity_sha256"]], "source_date": parsed_date(row["source_date"])})


def execute_write(database_url, pack):
    preflight = dry_run(database_url, pack)
    if preflight["candidate_state"] != "ABSENT":
        raise RuntimeError("write requires fully absent Batch 2 candidate state")
    engine = create_engine(database_url, pool_pre_ping=True)
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"))
            if candidate_state(connection, pack) != "ABSENT":
                raise RuntimeError("in-transaction candidate state changed")
            before = table_counts(connection)
            insert_candidate(connection, pack)
            if candidate_state(connection, pack) != "EXACTLY_PRESENT":
                raise RuntimeError("post-insert exact-set reconciliation failed")
            after = table_counts(connection)
            delta = {name: after[name] - before[name] for name in before}
            expected = {"club_venues": 0, **EXPECTED_COUNTS}
            if delta != expected:
                raise RuntimeError(f"physical delta mismatch: {delta}")
            transaction.commit()
        except Exception:
            if transaction.is_active:
                transaction.rollback()
            raise
    return {"preflight": preflight, "delta": expected, "candidate_state": "EXACTLY_PRESENT", "database_writes": 78}


def execute_rollback(database_url, pack):
    engine = create_engine(database_url, pool_pre_ping=True)
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"))
            try:
                state = candidate_state(connection, pack)
            except RuntimeError as error:
                raise RuntimeError("rollback refused: candidate exact set has drifted or is absent") from error
            if state != "EXACTLY_PRESENT":
                raise RuntimeError("rollback refused: candidate exact set has drifted or is absent")
            facts, spots, evidence, _ = _actual_sets(connection, pack)
            evidence_ids = connection.execute(text("SELECT evidence_id FROM pre_match_spot_evidence WHERE pre_match_spot_id IN :ids")
                .bindparams(bindparam("ids", expanding=True)), {"ids": [row["pre_match_spot_id"] for row in spots]}).scalars().all()
            connection.execute(text("DELETE FROM pre_match_spot_evidence WHERE evidence_id IN :ids").bindparams(bindparam("ids", expanding=True)), {"ids": evidence_ids})
            connection.execute(text("DELETE FROM pre_match_spots WHERE pre_match_spot_id IN :ids").bindparams(bindparam("ids", expanding=True)), {"ids": [row["pre_match_spot_id"] for row in spots]})
            connection.execute(text("DELETE FROM venue_guide_facts WHERE fact_id IN :ids").bindparams(bindparam("ids", expanding=True)), {"ids": [row["fact_id"] for row in facts]})
            if candidate_state(connection, pack) != "ABSENT":
                raise RuntimeError("post-rollback candidate state mismatch")
            transaction.commit()
        except Exception:
            if transaction.is_active:
                transaction.rollback()
            raise
    return {"deleted": EXPECTED_COUNTS, "club_venues": 0, "updates": 0, "candidate_state": "ABSENT"}
