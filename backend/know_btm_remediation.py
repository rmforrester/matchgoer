"""Guarded, hash-bound remediation for already-published KNOW/BTM content."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone

from sqlalchemy import text
from provider_identity_guard import validate_provider_relationship_contract, verify_provider_relationship


CONTRACT_MODE = "KNOW_BTM_REMEDIATION_CANDIDATE_NO_WRITE"
OPS = {"KEEP", "UPDATE", "RETIRE", "REOWN", "INSERT"}
FACT_MUTABLE = {"team_id", "club_venue_id", "venue_id", "fixture_id", "module", "headline", "content", "display_order", "publication_status", "confidence", "claim_sensitivity", "reviewed_at", "review_after", "expires_at", "approved_at", "approved_by"}
SPOT_MUTABLE = {"club_venue_id", "display_name", "classification", "audience", "supporting_line", "maps_destination", "location_context", "confidence", "status", "business_status", "reviewed_at", "review_after", "display_order", "approved_at", "approved_by"}
FACT_SNAPSHOT = ("know_fact_id", "editorial_key", "team_id", "club_venue_id", "venue_id", "fixture_id", "module", "headline", "content", "display_order", "publication_status", "confidence", "claim_sensitivity", "reviewed_at", "review_after", "expires_at", "approved_at", "approved_by")
SPOT_SNAPSHOT = ("pre_match_spot_id", "club_venue_id", "display_name", "classification", "audience", "supporting_line", "maps_destination", "location_context", "confidence", "status", "business_status", "reviewed_at", "review_after", "display_order", "approved_at", "approved_by")
EVIDENCE_FIELDS = ("source_type", "source_title", "source_url", "source_date", "evidence_note", "disposition", "review_status", "contributor_user_id")
BTM_EVIDENCE_FIELDS = ("source_type", "source_url", "source_date", "disposition", "evidence_note", "contributor_user_id", "review_status")


def _scalar(value):
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    return value.isoformat() if isinstance(value, date) else value


def snapshot(row, fields):
    return {field: _scalar(row.get(field)) for field in fields}


def fingerprint(value: dict) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest().upper()


def _require(condition, message, error):
    if not condition:
        raise error(message)


def _validate_fact_subject(row, error):
    subjects = [row.get(k) for k in ("team_id", "club_venue_id", "venue_id", "fixture_id")]
    _require(sum(value is not None for value in subjects) == 1, "KNOW fact requires exactly one subject", error)
    module = row.get("module")
    if module in {"CLUB", "SUPPORTERS"}:
        _require(row.get("team_id") is not None, f"{module} KNOW fact requires team ownership", error)
    elif module == "MATCHDAY":
        _require(row.get("club_venue_id") is not None, "MATCHDAY KNOW fact requires club-venue ownership", error)


def validate(candidate: dict, error=RuntimeError) -> None:
    _require(candidate.get("schema_version") == 2 and candidate.get("mode") == CONTRACT_MODE, "unsupported remediation contract", error)
    for name in ("relationships", "know_operations", "btm_operations", "blocked_relationships"):
        _require(isinstance(candidate.get(name), list), f"invalid {name}", error)
    relationship_ids = set()
    for row in candidate["relationships"]:
        required = ("club_venue_id", "team_id", "team_name", "venue_id", "venue_name", "relationship_type", "status")
        _require(all(row.get(k) is not None for k in required), "incomplete relationship ownership", error)
        _require(row["club_venue_id"] not in relationship_ids, "duplicate relationship ownership", error)
        relationship_ids.add(row["club_venue_id"])
        validate_provider_relationship_contract(row, error)
    blocked = {int(x["club_venue_id"]) for x in candidate["blocked_relationships"]}
    _require(not blocked.intersection(relationship_ids), "blocked relationship included", error)
    seen = set()
    for row in candidate["know_operations"]:
        op = row.get("operation")
        _require(op in OPS, "unexpected KNOW operation", error)
        key = row.get("operation_key")
        _require(key and key not in seen, "duplicate or missing operation key", error); seen.add(key)
        _require(int(row.get("club_venue_id", 0)) in relationship_ids, "KNOW ownership outside candidate", error)
        if op == "INSERT":
            _require(isinstance(row.get("after"), dict) and not row.get("expected_before"), "INSERT must define only after", error)
        else:
            _require(isinstance(row.get("expected_before"), dict), "existing fact requires expected_before", error)
            _require(row.get("expected_before_sha256") == fingerprint(row["expected_before"]), "expected-before hash mismatch", error)
        changes = row.get("changes", {})
        _require(isinstance(changes, dict) and set(changes).issubset(FACT_MUTABLE), "invalid KNOW changes", error)
        if op == "RETIRE": _require(changes == {"publication_status": "ARCHIVED"}, "RETIRE must archive", error)
        if op == "KEEP": _require(not changes, "KEEP cannot change fields", error)
        if op == "REOWN": _require(bool(set(changes) & {"team_id", "club_venue_id", "venue_id", "fixture_id"}), "REOWN requires explicit ownership change", error)
        if op == "INSERT": _validate_fact_subject(row["after"], error)
        elif op in {"UPDATE", "REOWN"}: _validate_fact_subject({**row["expected_before"], **changes}, error)
        for ev in row.get("evidence", []):
            _require(ev.get("review_status") == "ACCEPTED" and ev.get("disposition") == "SUPPORTS", "replacement evidence must be accepted/supporting", error)
    for row in candidate["btm_operations"]:
        _require(row.get("operation") in OPS, "unexpected BTM operation", error)
        _require(int(row.get("club_venue_id", 0)) in relationship_ids, "BTM ownership outside candidate", error)
        _require(row.get("durability") != "MATCH_SPECIFIC", "fixture-scoped BTM unsupported by current schema", error)
    _require(not candidate["btm_operations"], "BTM remediation operations are not enabled because this candidate requires none", error)
    allowed = candidate.get("allowed_mutations", {})
    _require(set(allowed) == {"know_facts", "know_fact_evidence", "pre_match_spots", "pre_match_spot_evidence"}, "strict mutation boundary mismatch", error)
    expected = {
        "know_facts": sum(x["operation"] in {"UPDATE", "RETIRE", "REOWN", "INSERT"} for x in candidate["know_operations"]),
        "know_fact_evidence": sum(len(x.get("evidence", [])) for x in candidate["know_operations"]),
        "pre_match_spots": sum(x["operation"] in {"UPDATE", "RETIRE", "REOWN", "INSERT"} for x in candidate["btm_operations"]),
        "pre_match_spot_evidence": sum(len(x.get("evidence", [])) for x in candidate["btm_operations"]),
    }
    _require(all(int(allowed[k]) == v for k, v in expected.items()), "allowed mutation counts mismatch", error)


def _same(actual, expected, fields):
    return snapshot(actual, fields) == {k: _scalar(expected.get(k)) for k in fields}


def _desired(operation, fields):
    if operation["operation"] == "INSERT": return operation["after"]
    return {**operation["expected_before"], **operation.get("changes", {})}


def _verify_relationship(connection, row, error):
    actual = connection.execute(text("""SELECT cv.club_venue_id,cv.team_id,t.team_name,cv.venue_id,v.name venue_name,cv.relationship_type,cv.status
      FROM club_venues cv JOIN teams t ON t.team_id=cv.team_id JOIN venues v ON v.venue_id=cv.venue_id
      WHERE cv.club_venue_id=:id"""), {"id": row["club_venue_id"]}).mappings().one_or_none()
    _require(actual is not None and all(actual[k] == row[k] for k in actual.keys()), f"relationship ownership mismatch: {row['club_venue_id']}", error)


def preflight(connection, candidate: dict, error=RuntimeError):
    validate(candidate, error)
    for row in candidate["relationships"]:
        verify_provider_relationship(connection, row, error)
        _verify_relationship(connection, row, error)
    plan = {"know_facts": {"update": 0, "retire": 0, "reown": 0, "insert": 0, "keep": 0, "no_op": 0}, "know_fact_evidence": {"insert": 0, "reuse": 0, "preserve": 0}, "pre_match_spots": {"update": 0, "retire": 0, "reown": 0, "insert": 0, "keep": 0, "no_op": 0}, "pre_match_spot_evidence": {"insert": 0, "reuse": 0, "preserve": 0}}
    states = {"facts": {}, "spots": {}}
    for op in candidate["know_operations"]:
        row = connection.execute(text("SELECT * FROM know_facts WHERE know_fact_id=:id"), {"id": op.get("fact_id")}).mappings().one_or_none() if op["operation"] != "INSERT" else connection.execute(text("SELECT * FROM know_facts WHERE editorial_key=:key"), {"key": op["after"]["editorial_key"]}).mappings().one_or_none()
        desired = _desired(op, FACT_SNAPSHOT)
        comparison_fields = FACT_SNAPSHOT[1:] if op["operation"] == "INSERT" else FACT_SNAPSHOT
        if row is not None and _same(row, desired, comparison_fields):
            state="no_op"; fact_id=row["know_fact_id"]
        elif op["operation"] == "INSERT":
            _require(row is None, f"conflicting inserted fact: {op['operation_key']}", error); state="insert"; fact_id=None
        else:
            _require(row is not None, f"missing fact: {op['operation_key']}", error)
            actual=snapshot(row, FACT_SNAPSHOT)
            _require(fingerprint(actual)==op["expected_before_sha256"] and actual==op["expected_before"], f"expected-before conflict: {op['operation_key']}", error)
            state=op["operation"].lower(); fact_id=row["know_fact_id"]
        plan["know_facts"][state]+=1; states["facts"][op["operation_key"]]={"state":state,"fact_id":fact_id,"desired":desired}
        if fact_id is not None:
            existing=connection.execute(text("SELECT * FROM know_fact_evidence WHERE know_fact_id=:id"),{"id":fact_id}).mappings().all()
            plan["know_fact_evidence"]["preserve"] += len(existing)
        else: existing=[]
        for ev in op.get("evidence",[]):
            expected={**ev,"source_date":date.fromisoformat(ev["source_date"]) if ev.get("source_date") else None}
            if any(_same(x,expected,EVIDENCE_FIELDS) for x in existing): plan["know_fact_evidence"]["reuse"]+=1
            elif any(x["source_title"] == ev["source_title"] and x["source_url"] == ev.get("source_url") for x in existing):
                raise error(f"evidence conflict: {op['operation_key']}")
            else: plan["know_fact_evidence"]["insert"]+=1
    for op in candidate["btm_operations"]:
        row=connection.execute(text("SELECT * FROM pre_match_spots WHERE pre_match_spot_id=:id"),{"id":op.get("spot_id")}).mappings().one_or_none() if op["operation"]!="INSERT" else None
        desired=_desired(op,SPOT_SNAPSHOT)
        if row is not None and _same(row,desired,SPOT_SNAPSHOT): state="no_op"; spot_id=row["pre_match_spot_id"]
        elif op["operation"]=="INSERT": state="insert"; spot_id=None
        else:
            _require(row is not None,"missing BTM spot",error); actual=snapshot(row,SPOT_SNAPSHOT)
            _require(fingerprint(actual)==op["expected_before_sha256"] and actual==op["expected_before"],"BTM expected-before conflict",error)
            state=op["operation"].lower(); spot_id=row["pre_match_spot_id"]
        plan["pre_match_spots"][state]+=1; states["spots"][op["operation_key"]]={"state":state,"spot_id":spot_id,"desired":desired}
    return {"operations":plan,"states":states,"unrelated_mutations":{"teams":0,"fixtures":0,"venues":0,"club_venues":0,"provider_refs":0,"aliases":0,"coordinates":0,"decision":0,"deletes":0}}


def apply(connection, candidate, plan):
    completed=[]
    for op in candidate["know_operations"]:
        state=plan["states"]["facts"][op["operation_key"]]; desired=state["desired"]
        if state["state"] in {"update","retire","reown"}:
            changes=op["changes"]; sets=", ".join(f"{k}=:{k}" for k in changes)+", updated_at=CURRENT_TIMESTAMP"
            connection.execute(text(f"UPDATE know_facts SET {sets} WHERE know_fact_id=:fact_id"),{**changes,"fact_id":op["fact_id"]}); completed.append(f"know_facts:{state['state']}")
        elif state["state"]=="insert":
            cols=[k for k in desired if k!="know_fact_id"]; values=", ".join(f":{k}" for k in cols)
            state["fact_id"]=connection.execute(text(f"INSERT INTO know_facts ({', '.join(cols)}) VALUES ({values}) RETURNING know_fact_id"),desired).scalar_one(); completed.append("know_facts:insert")
        fact_id=state["fact_id"]
        for ev in op.get("evidence",[]):
            exists=connection.execute(text("SELECT 1 FROM know_fact_evidence WHERE know_fact_id=:id AND source_title=:title AND source_url IS NOT DISTINCT FROM :url"),{"id":fact_id,"title":ev["source_title"],"url":ev.get("source_url")}).scalar_one_or_none()
            if not exists:
                connection.execute(text("""INSERT INTO know_fact_evidence(know_fact_id,source_type,source_title,source_url,source_date,evidence_note,disposition,review_status,contributor_user_id)
                  VALUES(:know_fact_id,:source_type,:source_title,:source_url,:source_date,:evidence_note,:disposition,:review_status,:contributor_user_id)"""),{**ev,"know_fact_id":fact_id,"source_date":date.fromisoformat(ev["source_date"]) if ev.get("source_date") else None}); completed.append("know_fact_evidence:insert")
    return completed
