"""Hash-bound, atomic publisher for combined KNOW/BTM publication candidates."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import create_engine, text

from database_target import ExpectedDatabaseTarget, verify_database_target
from provider_identity_guard import validate_provider_relationship_contract, verify_provider_relationship
import know_btm_remediation as remediation
from editorial_contract import EditorialContractError, inspect_page, validate_review_metadata

REL_TYPES = {"HOME", "TEMPORARY_HOME", "GROUND_SHARE"}
REL_STATUSES = {"CURRENT", "HISTORICAL", "DRAFT"}
MODULES = {"CLUB", "SUPPORTERS", "MATCHDAY", "DONT_MISS", "GOOD_TO_KNOW"}
SPOT_CLASSES = {"SUPPORTER_SPOT", "CLUB_MATCHDAY_VENUE", "SUPPORTER_AREA"}
SOURCE_TYPES = {"OFFICIAL", "SUPPORTER_ORGANISATION", "LOCAL_MEDIA", "ACADEMIC", "BOOK", "INTERVIEW", "REDDIT", "FAN_FORUM", "MATCHGOER_SUPPORTER_SUBMISSION", "MATCHGOER_CORROBORATION", "EDITORIAL_RESEARCH", "OTHER"}
BTM_SOURCE_TYPES = SOURCE_TYPES - {"ACADEMIC", "BOOK", "INTERVIEW"}
COUNT_KEYS = ("club_venues", "know_facts", "know_fact_evidence", "pre_match_spots", "pre_match_spot_evidence", "venue_guide_facts")
UNRELATED = {"fixtures": 0, "venues": 0, "coordinates": 0, "provider_refs": 0, "aliases": 0, "deletes": 0}
TARGET_TABLES = ("teams", "venues", "club_venues", "know_facts", "know_fact_evidence", "pre_match_spots", "pre_match_spot_evidence", "venue_guide_facts")
TARGET_COLUMNS = (("teams", "team_id"), ("club_venues", "team_id"), ("know_facts", "editorial_key"), ("pre_match_spots", "club_venue_id"))


class PublicationError(RuntimeError):
    pass


def digest(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest().upper()


def load_candidate(path: str | Path, expected_sha256: str) -> tuple[dict, str]:
    actual = digest(path)
    if actual != expected_sha256.upper():
        raise PublicationError("candidate SHA-256 mismatch")
    candidate = json.loads(Path(path).read_text(encoding="utf-8"))
    if candidate.get("mode") == remediation.CONTRACT_MODE:
        remediation.validate(candidate, PublicationError)
    else:
        validate_candidate(candidate)
    return candidate, actual


def _unique(rows, key, label):
    values = [row.get(key) for row in rows]
    if None in values or len(values) != len(set(values)):
        raise PublicationError(f"duplicate or missing {label}")


def validate_candidate(c: dict) -> None:
    if c.get("schema_version") != 2 or c.get("mode") != "PUBLICATION_CANDIDATE_NO_WRITE":
        raise PublicationError("unsupported combined publication contract")
    required = ("relationships", "know_facts", "know_fact_evidence", "pre_match_spots", "pre_match_spot_evidence", "ticket_actions", "reviewed_btm_omissions", "secondary_withholds")
    if any(not isinstance(c.get(key), list) for key in required):
        raise PublicationError("candidate list structure is invalid")
    _unique(c["relationships"], "relationship_key", "relationship key")
    _unique(c["know_facts"], "editorial_key", "editorial key")
    _unique(c["pre_match_spots"], "spot_key", "spot key")
    _unique(c["ticket_actions"], "action_key", "ticket action key")
    relationships = {r["relationship_key"] for r in c["relationships"]}
    facts = {r["editorial_key"] for r in c["know_facts"]}
    spots = {r["spot_key"] for r in c["pre_match_spots"]}
    know_evidence_keys = [(r.get("fact_editorial_key"), r.get("source_title"), r.get("source_url")) for r in c["know_fact_evidence"]]
    btm_evidence_keys = [(r.get("spot_key"), r.get("source_type"), r.get("source_url"), r.get("source_date")) for r in c["pre_match_spot_evidence"]]
    if len(know_evidence_keys) != len(set(know_evidence_keys)) or len(btm_evidence_keys) != len(set(btm_evidence_keys)):
        raise PublicationError("duplicate evidence identity")
    for r in c["relationships"]:
        if not isinstance(r.get("team_id"), int) or not isinstance(r.get("venue_id"), int):
            raise PublicationError("relationship requires canonical team_id and venue_id")
        if r.get("relationship_type") not in REL_TYPES or r.get("status") not in REL_STATUSES:
            raise PublicationError("invalid relationship lifecycle")
        if not str(r.get("team_name", "")).strip() or not str(r.get("venue_name", "")).strip():
            raise PublicationError("relationship identity names are required")
        validate_provider_relationship_contract(r, PublicationError)
    for r in c["know_facts"]:
        if r.get("relationship_key") not in relationships or r.get("module") not in MODULES:
            raise PublicationError("invalid KNOW ownership/module")
        if r.get("publication_status") != "PUBLISHED" or r.get("confidence") not in {"HIGH", "MEDIUM"}:
            raise PublicationError("unpublishable KNOW fact")
        if r.get("claim_sensitivity") not in {"STANDARD", "SENSITIVE"} or r.get("durability") not in {"DURABLE", "SEASONAL", "MATCH_SPECIFIC"}:
            raise PublicationError("invalid KNOW lifecycle metadata")
        if not str(r.get("content", "")).strip() or not r.get("approved_at") or not str(r.get("approved_by", "")).strip():
            raise PublicationError("incomplete approved KNOW fact")
        owners = [name for name in ("team_id", "club_venue_id", "venue_id", "fixture_id") if r.get(name) is not None]
        if len(owners) != 1:
            raise PublicationError("KNOW fact requires exactly one canonical subject")
        if r["module"] in {"CLUB", "SUPPORTERS"} and owners != ["team_id"]:
            raise PublicationError("CLUB/SUPPORTERS facts require team_id ownership")
        if r["module"] == "MATCHDAY" and owners != ["club_venue_id"]:
            raise PublicationError("MATCHDAY facts require club_venue_id ownership")
        relationship = next(x for x in c["relationships"] if x["relationship_key"] == r["relationship_key"])
        if owners == ["team_id"] and r["team_id"] != relationship["team_id"]:
            raise PublicationError("KNOW team ownership contradicts relationship")
        if owners == ["club_venue_id"] and r["club_venue_id"] != "RELATIONSHIP":
            raise PublicationError("new relationship-owned KNOW facts must use RELATIONSHIP placeholder")
        try:
            validate_review_metadata(r.get("editorial_review", {}))
        except EditorialContractError as exc:
            raise PublicationError(f"invalid KNOW editorial review: {exc}") from exc
        if any(r["editorial_review"][key] for key in ("ui_duplicate", "know_duplicate", "btm_duplicate", "decide_duplicate")):
            raise PublicationError("publication-blocking KNOW duplicate")
    for r in c["know_fact_evidence"]:
        if r.get("fact_editorial_key") not in facts:
            raise PublicationError("KNOW evidence references missing fact")
        if r.get("source_type") not in SOURCE_TYPES or r.get("disposition") not in {"SUPPORTS", "CONTRADICTS"} or r.get("review_status") not in {"PENDING", "ACCEPTED", "REJECTED"}:
            raise PublicationError("invalid KNOW evidence")
    for r in c["pre_match_spots"]:
        if r.get("relationship_key") not in relationships or r.get("classification") not in SPOT_CLASSES:
            raise PublicationError("invalid BTM ownership/classification")
        if r.get("audience") not in {"HOME", "MIXED"} or r.get("status") not in {"DRAFT", "CURRENT", "NEEDS_REVIEW", "ARCHIVED"}:
            raise PublicationError("invalid BTM lifecycle")
        if r.get("business_status") not in {"OPEN", "UNKNOWN", "CLOSED", "NOT_APPLICABLE"} or r.get("confidence") not in {"HIGH", "MEDIUM", "LOW"}:
            raise PublicationError("invalid BTM status/confidence")
        if r.get("durability") not in {"DURABLE", "SEASONAL", "MATCH_SPECIFIC"} or not 1 <= int(r.get("display_order", 0)) <= 3:
            raise PublicationError("invalid BTM lifecycle metadata")
        if not r.get("approved_at") or not str(r.get("approved_by", "")).strip():
            raise PublicationError("BTM approval is required")
        try:
            validate_review_metadata(r.get("editorial_review", {}))
        except EditorialContractError as exc:
            raise PublicationError(f"invalid BTM editorial review: {exc}") from exc
        if any(r["editorial_review"][key] for key in ("ui_duplicate", "know_duplicate", "btm_duplicate", "decide_duplicate")):
            raise PublicationError("publication-blocking BTM duplicate")
    for r in c["pre_match_spot_evidence"]:
        if r.get("spot_key") not in spots:
            raise PublicationError("BTM evidence references missing spot")
        if r.get("source_type") not in BTM_SOURCE_TYPES or r.get("disposition") not in {"SUPPORTS", "CONTRADICTS"} or r.get("review_status") not in {"PENDING", "ACCEPTED", "REJECTED"}:
            raise PublicationError("invalid BTM evidence")
    for r in c["reviewed_btm_omissions"]:
        if r.get("relationship_key") not in relationships or r.get("status") != "OMISSION_REVIEWED":
            raise PublicationError("invalid reviewed BTM omission")
    for r in c["ticket_actions"]:
        if r.get("relationship_key") not in relationships or r.get("section") != "tickets_entry":
            raise PublicationError("invalid ticket action ownership/section")
        if r.get("source_type") != "official" or r.get("status") != "current" or r.get("confidence") not in {"high", "medium"}:
            raise PublicationError("ticket action requires current official evidence")
        if not str(r.get("topic", "")).strip() or not str(r.get("content", "")).strip():
            raise PublicationError("ticket action requires topic/content")
        url = str(r.get("source_url", ""))
        if not url.startswith("https://"):
            raise PublicationError("ticket action requires an HTTPS official destination")
        try:
            validate_review_metadata(r.get("editorial_review", {}))
        except EditorialContractError as exc:
            raise PublicationError(f"invalid ticket editorial review: {exc}") from exc
        if any(r["editorial_review"][key] for key in ("ui_duplicate", "know_duplicate", "btm_duplicate", "decide_duplicate")):
            raise PublicationError("publication-blocking ticket duplicate")
    page = inspect_page(c["know_facts"], [r.get("supporting_line", "") for r in c["pre_match_spots"]])
    if page["result"] != "PASS":
        raise PublicationError(f"editorial page contract failed: {page['failures']}")
    allowed = c.get("allowed_mutations", {})
    actual = {"club_venues": len(c["relationships"]), "know_facts": len(c["know_facts"]), "know_fact_evidence": len(c["know_fact_evidence"]), "pre_match_spots": len(c["pre_match_spots"]), "pre_match_spot_evidence": len(c["pre_match_spot_evidence"]), "venue_guide_facts": len(c["ticket_actions"])}
    if any(int(allowed.get(k, -1)) != v for k, v in actual.items()) or any(int(allowed.get(k, -1)) != 0 for k in UNRELATED):
        raise PublicationError("allowed mutation boundary does not match candidate")


def _date(v): return date.fromisoformat(v) if v else None
def _datetime(v): return datetime.fromisoformat(v) if v else None
def _scalar(v): return v.isoformat() if isinstance(v, (date, datetime)) else v


def _same(actual, expected, fields):
    return all(_scalar(actual.get(k)) == _scalar(expected.get(k)) for k in fields)


REL_FIELDS = ("team_id", "venue_id", "relationship_type", "status", "valid_from", "valid_until")
FACT_FIELDS = ("editorial_key", "team_id", "club_venue_id", "venue_id", "fixture_id", "module", "headline", "content", "display_order", "publication_status", "confidence", "claim_sensitivity", "reviewed_at", "review_after", "expires_at", "approved_at", "approved_by")
KNOW_EVIDENCE_FIELDS = ("source_type", "source_title", "source_url", "source_date", "evidence_note", "disposition", "review_status", "contributor_user_id")
SPOT_FIELDS = ("club_venue_id", "display_name", "classification", "audience", "supporting_line", "maps_destination", "location_context", "confidence", "status", "business_status", "reviewed_at", "review_after", "display_order", "approved_at", "approved_by")
BTM_EVIDENCE_FIELDS = ("source_type", "source_url", "source_date", "disposition", "evidence_note", "contributor_user_id", "review_status")
GUIDE_FIELDS = ("club_venue_id", "section", "topic", "content", "source_type", "source_label", "source_url", "reviewed_at", "confidence", "status", "review_after", "expires_at", "display_order")


def _expected_fact(row, cv_id):
    result = {**row, "reviewed_at": _date(row.get("reviewed_at")), "review_after": _date(row.get("review_after")), "expires_at": _date(row.get("expires_at")), "approved_at": _datetime(row.get("approved_at"))}
    if result.get("club_venue_id") == "RELATIONSHIP": result["club_venue_id"] = cv_id
    return result


def _expected_spot(row, cv_id):
    return {**row, "club_venue_id": cv_id, "reviewed_at": _date(row.get("reviewed_at")), "review_after": _date(row.get("review_after")), "approved_at": _datetime(row.get("approved_at"))}


def _expected_guide(row, cv_id):
    return {**row, "club_venue_id": cv_id, "reviewed_at": _date(row.get("reviewed_at")), "review_after": _date(row.get("review_after")), "expires_at": _date(row.get("expires_at"))}


def preflight(connection, c: dict) -> dict:
    counts = {k: {"insert": 0, "reuse": 0, "no_op": 0} for k in COUNT_KEYS}
    ids = {"relationships": {}, "facts": {}, "spots": {}}
    blocked, conflicts = [], []
    for r in c["relationships"]:
        verify_provider_relationship(connection, r, PublicationError)
        team = connection.execute(text("SELECT team_id,team_name,venue_id FROM teams WHERE team_id=:id"), {"id": r["team_id"]}).mappings().all()
        venue = connection.execute(text("SELECT venue_id,name,city,country FROM venues WHERE venue_id=:id"), {"id": r["venue_id"]}).mappings().all()
        if len(team) != 1 or team[0]["team_name"] != r["team_name"] or len(venue) != 1 or venue[0]["name"] != r["venue_name"]:
            raise PublicationError(f"team/venue identity mismatch: {r['relationship_key']}")
        rows = connection.execute(text("SELECT club_venue_id,team_id,venue_id,relationship_type,status,valid_from,valid_until FROM club_venues WHERE team_id=:id"), {"id": r["team_id"]}).mappings().all()
        exact = [x for x in rows if _same(x, {**r, "valid_from": None, "valid_until": None}, REL_FIELDS)]
        if exact:
            if len(exact) != 1: raise PublicationError("ambiguous identical club_venue")
            ids["relationships"][r["relationship_key"]] = exact[0]["club_venue_id"]; counts["club_venues"]["reuse"] += 1
        elif rows:
            raise PublicationError(f"conflicting club_venue: {r['relationship_key']}")
        else:
            ids["relationships"][r["relationship_key"]] = None; counts["club_venues"]["insert"] += 1
    for r in c["know_facts"]:
        row = connection.execute(text("SELECT * FROM know_facts WHERE editorial_key=:key"), {"key": r["editorial_key"]}).mappings().one_or_none()
        cv_id = ids["relationships"][r["relationship_key"]]
        if row is None: counts["know_facts"]["insert"] += 1
        elif cv_id is not None and _same(row, _expected_fact(r, cv_id), FACT_FIELDS):
            ids["facts"][r["editorial_key"]] = row["know_fact_id"]; counts["know_facts"]["no_op"] += 1
        else: raise PublicationError(f"conflicting KNOW fact: {r['editorial_key']}")
    for r in c["know_fact_evidence"]:
        fid = ids["facts"].get(r["fact_editorial_key"])
        if fid is None: counts["know_fact_evidence"]["insert"] += 1; continue
        rows = connection.execute(text("SELECT * FROM know_fact_evidence WHERE know_fact_id=:id"), {"id": fid}).mappings().all()
        expected = {**r, "source_date": _date(r.get("source_date"))}
        if any(_same(x, expected, KNOW_EVIDENCE_FIELDS) for x in rows): counts["know_fact_evidence"]["no_op"] += 1
        elif rows: raise PublicationError(f"conflicting KNOW evidence: {r['fact_editorial_key']}")
        else: counts["know_fact_evidence"]["insert"] += 1
    for r in c["pre_match_spots"]:
        cv_id = ids["relationships"][r["relationship_key"]]
        if cv_id is None: counts["pre_match_spots"]["insert"] += 1; continue
        rows = connection.execute(text("SELECT * FROM pre_match_spots WHERE club_venue_id=:id AND display_name=:name"), {"id": cv_id, "name": r["display_name"]}).mappings().all()
        expected = _expected_spot(r, cv_id)
        exact = [x for x in rows if _same(x, expected, SPOT_FIELDS)]
        if exact:
            if len(exact) != 1: raise PublicationError("ambiguous identical BTM spot")
            ids["spots"][r["spot_key"]] = exact[0]["pre_match_spot_id"]; counts["pre_match_spots"]["no_op"] += 1
        elif rows: raise PublicationError(f"conflicting BTM spot: {r['spot_key']}")
        else: counts["pre_match_spots"]["insert"] += 1
    for r in c["pre_match_spot_evidence"]:
        sid = ids["spots"].get(r["spot_key"])
        if sid is None: counts["pre_match_spot_evidence"]["insert"] += 1; continue
        rows = connection.execute(text("SELECT * FROM pre_match_spot_evidence WHERE pre_match_spot_id=:id"), {"id": sid}).mappings().all()
        expected = {**r, "source_date": _date(r.get("source_date"))}
        if any(_same(x, expected, BTM_EVIDENCE_FIELDS) for x in rows): counts["pre_match_spot_evidence"]["no_op"] += 1
        elif rows: raise PublicationError(f"conflicting BTM evidence: {r['spot_key']}")
        else: counts["pre_match_spot_evidence"]["insert"] += 1
    for r in c["ticket_actions"]:
        cv_id = ids["relationships"][r["relationship_key"]]
        if cv_id is None: counts["venue_guide_facts"]["insert"] += 1; continue
        rows = connection.execute(text("SELECT * FROM venue_guide_facts WHERE club_venue_id=:id AND section='tickets_entry' AND topic=:topic"), {"id": cv_id, "topic": r["topic"]}).mappings().all()
        exact = [x for x in rows if _same(x, _expected_guide(r, cv_id), GUIDE_FIELDS)]
        if exact:
            if len(exact) != 1: raise PublicationError("ambiguous identical ticket action")
            counts["venue_guide_facts"]["no_op"] += 1
        elif rows: raise PublicationError(f"conflicting ticket action: {r['action_key']}")
        else: counts["venue_guide_facts"]["insert"] += 1
    return {"operations": counts, "ids": ids, "reviewed_omissions": {"artifact_only": len(c["reviewed_btm_omissions"]), "persistent_operations": 0}, "blocked": blocked, "conflicts": conflicts, "unrelated_mutations": dict(UNRELATED)}


def _insert(connection, c, plan):
    done = []
    ids = plan["ids"]
    for r in c["relationships"]:
        if ids["relationships"][r["relationship_key"]] is None:
            ids["relationships"][r["relationship_key"]] = connection.execute(text("INSERT INTO club_venues(team_id,venue_id,relationship_type,status,valid_from,valid_until) VALUES(:team_id,:venue_id,:relationship_type,:status,NULL,NULL) RETURNING club_venue_id"), r).scalar_one(); done.append("club_venues")
    for r in c["know_facts"]:
        if r["editorial_key"] in ids["facts"]: continue
        x = _expected_fact(r, ids["relationships"][r["relationship_key"]])
        ids["facts"][r["editorial_key"]] = connection.execute(text("""INSERT INTO know_facts(editorial_key,team_id,club_venue_id,venue_id,fixture_id,module,headline,content,display_order,publication_status,confidence,claim_sensitivity,reviewed_at,review_after,expires_at,approved_at,approved_by) VALUES(:editorial_key,:team_id,:club_venue_id,:venue_id,:fixture_id,:module,:headline,:content,:display_order,:publication_status,:confidence,:claim_sensitivity,:reviewed_at,:review_after,:expires_at,:approved_at,:approved_by) RETURNING know_fact_id"""), x).scalar_one(); done.append("know_facts")
    for r in c["know_fact_evidence"]:
        connection.execute(text("""INSERT INTO know_fact_evidence(know_fact_id,source_type,source_title,source_url,source_date,evidence_note,disposition,review_status,contributor_user_id) VALUES(:know_fact_id,:source_type,:source_title,:source_url,:source_date,:evidence_note,:disposition,:review_status,:contributor_user_id) ON CONFLICT (know_fact_id,source_title,source_url) DO NOTHING"""), {**r, "know_fact_id": ids["facts"][r["fact_editorial_key"]], "source_date": _date(r.get("source_date"))}); done.append("know_fact_evidence")
    for r in c["pre_match_spots"]:
        if r["spot_key"] in ids["spots"]: continue
        x = _expected_spot(r, ids["relationships"][r["relationship_key"]])
        ids["spots"][r["spot_key"]] = connection.execute(text("""INSERT INTO pre_match_spots(club_venue_id,display_name,classification,audience,supporting_line,maps_destination,location_context,confidence,status,business_status,reviewed_at,review_after,display_order,approved_at,approved_by) VALUES(:club_venue_id,:display_name,:classification,:audience,:supporting_line,:maps_destination,:location_context,:confidence,:status,:business_status,:reviewed_at,:review_after,:display_order,:approved_at,:approved_by) RETURNING pre_match_spot_id"""), x).scalar_one(); done.append("pre_match_spots")
    for r in c["pre_match_spot_evidence"]:
        connection.execute(text("""INSERT INTO pre_match_spot_evidence(pre_match_spot_id,source_type,source_url,source_date,disposition,evidence_note,contributor_user_id,review_status) VALUES(:pre_match_spot_id,:source_type,:source_url,:source_date,:disposition,:evidence_note,:contributor_user_id,:review_status)"""), {**r, "pre_match_spot_id": ids["spots"][r["spot_key"]], "source_date": _date(r.get("source_date"))}); done.append("pre_match_spot_evidence")
    for r in c["ticket_actions"]:
        cv_id = ids["relationships"][r["relationship_key"]]
        existing = connection.execute(text("SELECT fact_id FROM venue_guide_facts WHERE club_venue_id=:id AND section='tickets_entry' AND topic=:topic"), {"id": cv_id, "topic": r["topic"]}).scalar_one_or_none()
        if existing is not None: continue
        x = _expected_guide(r, cv_id)
        connection.execute(text("""INSERT INTO venue_guide_facts(club_venue_id,section,topic,content,source_type,source_label,source_url,reviewed_at,confidence,status,review_after,expires_at,display_order) VALUES(:club_venue_id,:section,:topic,:content,:source_type,:source_label,:source_url,:reviewed_at,:confidence,:status,:review_after,:expires_at,:display_order)"""), x); done.append("venue_guide_facts")
    return done


def execute(database_url, candidate, candidate_sha256, mode, *, confirm_write=False, failure_hook=None, expected_target=None, target_environment=None):
    if mode == "write" and not confirm_write: raise PublicationError("write requires --confirm-write")
    if candidate.get("mode") == remediation.CONTRACT_MODE:
        return _execute_remediation(database_url, candidate, candidate_sha256, mode, failure_hook=failure_hook, expected_target=expected_target, target_environment=target_environment)
    engine = create_engine(database_url, pool_pre_ping=True)
    completed = []
    try:
        with engine.connect() as connection:
            target_receipt = None
            transaction = connection.begin()
            try:
                if mode == "dry-run": connection.execute(text("SET TRANSACTION READ ONLY"))
                else: connection.execute(text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"))
                if mode != "dry-run" or expected_target is not None:
                    target_receipt = verify_database_target(connection, expected_target, target_environment)
                plan = preflight(connection, candidate)
                if mode == "dry-run": transaction.rollback(); return _receipt(candidate_sha256, mode, plan, "ROLLED_BACK_READ_ONLY", False, completed, target=target_receipt)
                completed = _insert(connection, candidate, plan)
                if failure_hook: failure_hook(connection)
                post = preflight(connection, candidate)
                if any(post["operations"][k]["insert"] for k in COUNT_KEYS): raise PublicationError("post-write exact reconciliation failed")
                if mode == "rollback-only": transaction.rollback(); outcome, persistent = "INTENTIONAL_ROLLBACK", False
                else: transaction.commit(); outcome, persistent = "COMMITTED", True
                return _receipt(candidate_sha256, mode, plan, outcome, persistent, completed, post, target_receipt)
            except Exception:
                if transaction.is_active: transaction.rollback()
                raise
    except Exception as exc:
        return {"status": "FAIL", "candidate_sha256": candidate_sha256, "execution_mode": mode, "failing_operation_class": completed[-1] if completed else "PREFLIGHT", "exception_type": type(exc).__name__, "exception_message": str(exc), "transaction_outcome": "ROLLED_BACK", "persistent_mutation": False, "completed_logical_operations": completed}


def _execute_remediation(database_url, candidate, candidate_sha256, mode, *, failure_hook=None, expected_target=None, target_environment=None):
    engine = create_engine(database_url, pool_pre_ping=True)
    completed = []
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                if mode == "dry-run": connection.execute(text("SET TRANSACTION READ ONLY"))
                else: connection.execute(text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"))
                target = verify_database_target(connection, expected_target, target_environment) if expected_target is not None else None
                if mode != "dry-run" and expected_target is None:
                    raise PublicationError("mutation mode requires verified database target")
                plan = remediation.preflight(connection, candidate, PublicationError)
                if mode == "dry-run":
                    transaction.rollback()
                    return {"status":"PASS","candidate_sha256":candidate_sha256,"execution_mode":mode,"database_target":target,"operations":plan["operations"],"unrelated_mutations":plan["unrelated_mutations"],"transaction_outcome":"ROLLED_BACK_READ_ONLY","persistent_mutation":False,"completed_logical_operations":[]}
                completed = remediation.apply(connection, candidate, plan)
                if failure_hook: failure_hook(connection)
                post = remediation.preflight(connection, candidate, PublicationError)
                if any(v for group in post["operations"].values() for k,v in group.items() if k not in {"no_op","reuse","preserve","keep"}):
                    raise PublicationError("post-remediation idempotence failed")
                if mode == "rollback-only": transaction.rollback(); outcome,persistent="INTENTIONAL_ROLLBACK",False
                else: transaction.commit(); outcome,persistent="COMMITTED",True
                return {"status":"PASS","candidate_sha256":candidate_sha256,"execution_mode":mode,"database_target":target,"operations":plan["operations"],"post_state":post["operations"],"unrelated_mutations":plan["unrelated_mutations"],"transaction_outcome":outcome,"persistent_mutation":persistent,"completed_logical_operations":completed}
            except Exception:
                if transaction.is_active: transaction.rollback()
                raise
    except Exception as exc:
        return {"status":"FAIL","candidate_sha256":candidate_sha256,"execution_mode":mode,"failing_operation_class":completed[-1] if completed else "PREFLIGHT","exception_type":type(exc).__name__,"exception_message":str(exc),"transaction_outcome":"ROLLED_BACK","persistent_mutation":False,"completed_logical_operations":completed}


def _receipt(sha, mode, plan, outcome, persistent, completed, post=None, target=None):
    return {"status": "PASS", "candidate_sha256": sha, "execution_mode": mode, "database_target": target, "operations": plan["operations"], "reviewed_omissions": plan["reviewed_omissions"], "blocked": plan["blocked"], "conflicts": plan["conflicts"], "unrelated_mutations": plan["unrelated_mutations"], "transaction_outcome": outcome, "persistent_mutation": persistent, "completed_logical_operations": completed, "post_state": post["operations"] if post else None}


def main():
    p = argparse.ArgumentParser(); p.add_argument("--database-url", required=True); p.add_argument("--candidate", required=True); p.add_argument("--expected-sha256", required=True); p.add_argument("--mode", choices=("dry-run", "rollback-only", "write"), default="dry-run"); p.add_argument("--confirm-write", action="store_true"); p.add_argument("--receipt"); p.add_argument("--expected-database"); p.add_argument("--expected-schema", default="public"); p.add_argument("--expected-environment"); p.add_argument("--target-environment")
    a = p.parse_args(); candidate, sha = load_candidate(a.candidate, a.expected_sha256)
    expected = ExpectedDatabaseTarget(a.expected_database, a.expected_schema, a.expected_environment, TARGET_TABLES, TARGET_COLUMNS) if a.expected_database and a.expected_environment else None
    result = execute(a.database_url, candidate, sha, a.mode, confirm_write=a.confirm_write, expected_target=expected, target_environment=a.target_environment)
    payload = json.dumps(result, indent=2, default=str) + "\n"
    if a.receipt: Path(a.receipt).write_text(payload, encoding="utf-8")
    print(payload, end="")
    if result["status"] != "PASS": raise SystemExit(1)


if __name__ == "__main__": main()
