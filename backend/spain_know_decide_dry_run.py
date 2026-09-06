"""Read the frozen Spain artifacts and reconcile them without hosted writes.

Uses the France publication architecture. Never regenerates reviewed CSVs.
"""
from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
import os
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports/spain"
KNOW = REPORTS / "spain-know-publication-inventory-20260906.csv"
DECIDE = REPORTS / "spain-decide-reconciliation-20260906.csv"
REMEDIATION = REPORTS / "spain-club-venue-remediation-dry-run-20260906.csv"
CATALOGUE = ROOT / "reports/decide/decide-five-country-reconciliation-20260903.csv"
EXPECTED_ARTIFACTS = {
    KNOW: "665DA96BEBB2975D2ECBBEE2D9DB00E08DA9E7BCFAB312F0C5F2F4F4CE1E6596",
    DECIDE: "6C995556C74D39209E30AB3BB018C0CCF97D3470D6F6604C10C6D0F7C39938B7",
    REMEDIATION: "2E2D179345AC2D71A34F5111FDA5982CB54146DAA63EF269FFA25A7686E1DB3C",
}
CATEGORIES = {"SIGNIFICANT_RIVALRY": 21, "CLASSIC_GROUND": 11,
              "FOOTBALL_LANDMARK": 6, "UNIQUE_SETTING": 2, "EXCEPTIONAL_SUPPORT": 12}
ENTRY_TEAMS = {529, 9580, 9692, 8157, 545}
GREAT_SUPPORT = {531, 543, 536, 728, 727, 4665, 731, 718, 544, 724, 535, 5254}
EXCEPTIONS = {728: 23276, 9571: 23568, 9585: 23570, 543: 23271, 529: 23260, 532: 23263}
ANDORRA_FIXTURES = [1569872,1569894,1569915,1569928,1569960,1569983,1570003,
    1570025,1570047,1570071,1570102,1570124,1570147,1570180,1570202,1570223,
    1570236,1570258,1570267,1570289,1570311]
BTM_FIELDS = ("display_name", "supporting_line", "maps_destination", "classification",
              "audience", "pre_match_status", "business_status", "pre_match_confidence",
              "display_order", "btm_evidence_url", "btm_evidence_classification")


class SafetyError(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise SafetyError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest().upper()


def rows(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def identity(fact):
    return (fact["subject_type"], fact.get("team_a_id"), fact.get("team_b_id"),
            fact.get("venue_id"), fact.get("team_id"), fact["attribute_key"])


def validate(know, decide, remediation):
    require(len(know) == 42, "KNOW must contain 42 clubs")
    require(Counter(r["competition"] for r in know) == {"La Liga":20,"Segunda":22}, "league partition")
    require(len({int(r["canonical_team_id"]) for r in know}) == 42, "duplicate team")
    require(Counter(r["intentional_null"] for r in know) == {"False":18,"True":24}, "BTM partition")
    require({int(r["canonical_team_id"]) for r in know if r["entry_description"]} == ENTRY_TEAMS, "Entry set")
    by = {int(r["canonical_team_id"]):r for r in know}
    for tid, vid in EXCEPTIONS.items():
        require(by[tid]["canonical_venue_id"] == str(vid), f"approved exception {tid}")
    require(not by[8157]["canonical_venue_id"] and not by[8157]["provider_venue_id"], "Andorra new canonical exception")
    for r in know:
        route = urlsplit(r["ticket_url"])
        require(route.scheme == "https" and bool(route.hostname) and not route.username, "absolute HTTPS ticket route")
        require(r["ticket_topic"] == "Tickets" and r["ticket_source_type"] == "official", "ticket convention")
        if r["intentional_null"] == "True":
            require(not any(r[k] for k in BTM_FIELDS), f"residual NULL BTM: {r['editorial_subject']}")
        else:
            require(all(r[k] for k in BTM_FIELDS if k != "btm_evidence_url"), "incomplete BTM")
        if r["entry_description"]:
            require(r["entry_topic"] == "Entry" and r["entry_section"] == "tickets_entry"
                    and r["entry_source_type"] == "official" and r["entry_evidence_url"].startswith("https://"), "Entry mapping")
    require(len(decide) == 52 and Counter(r["category"] for r in decide) == CATEGORIES, "DECIDE category count")
    require(Counter(r["current_status"] for r in decide) == {"CURRENT":51,"DORMANT":1}, "DECIDE status partition")
    dormant = [r for r in decide if r["current_status"] == "DORMANT"]
    require(dormant[0]["editorial_subject"] == "Cádiz — Xerez" and dormant[0]["proposed_action"] == "DORMANT_NO_WRITE"
            and dormant[0]["resolution_type"] == "GENUINE_NOT_IN_CURRENT_INVENTORY", "dormant catalogue retention")
    keys = [(r["category"], tuple(ast.literal_eval(r["canonical_subject_ids"]))) for r in decide]
    require(len(set(keys)) == 52, "duplicate DECIDE natural key")
    require({ast.literal_eval(r["canonical_subject_ids"])[0] for r in decide
             if r["category"] == "EXCEPTIONAL_SUPPORT"} == GREAT_SUPPORT, "Great Support exact set")
    for r in remediation:
        tid = int(r["team_id"])
        require(tid in by and r["venue_id"] == by[tid]["canonical_venue_id"], "supporting remediation identity mismatch")
        require(r["relationship_type"] == "HOME" and r["status"] == "CURRENT", "supporting relationship convention")


def approved():
    for path, expected in EXPECTED_ARTIFACTS.items():
        require(path.is_file() and sha(path) == expected,
                f"BLOCKED — REVIEWED SPAIN ARTIFACT MISSING OR HASH MISMATCH: {path.name}")
    know, decide, remediation = rows(KNOW), rows(DECIDE), rows(REMEDIATION)
    validate(know, decide, remediation)
    # France precedent: existing catalogue supplies its established display copy.
    source = {(r["subject"],r["category"]):r for r in rows(CATALOGUE) if r["country"] == "Spain"}
    facts = []
    for r in decide:
        if r["current_status"] == "DORMANT":
            continue
        ids = ast.literal_eval(r["canonical_subject_ids"])
        category = r["category"]
        scope = "TEAM_PAIR" if category == "SIGNIFICANT_RIVALRY" else "TEAM" if category == "EXCEPTIONAL_SUPPORT" else "VENUE"
        s = source.get((r["editorial_subject"], category))
        if s:
            label, explanation, priority = s["editorial_label"], s["short_explanation"], s["lead_priority"]
        elif scope == "TEAM":
            label, explanation, priority = "Exceptional support", r["exception_note"], "LEAD"
        else:
            # Three newly approved rivalry rows retain the reviewed label and
            # the existing Spain rivalry display convention, without new prose.
            require(scope == "TEAM_PAIR", f"missing catalogue copy: {r['editorial_subject']}")
            label = r["exception_note"]
            explanation = next(v["short_explanation"] for v in source.values() if v["scope"] == "TEAM_PAIR")
            priority = "NORMAL"
        facts.append(dict(subject=r["editorial_subject"], subject_type=scope, attribute_key=category,
            team_a_id=ids[0] if scope == "TEAM_PAIR" else None,
            team_b_id=ids[1] if scope == "TEAM_PAIR" else None,
            venue_id=ids[0] if scope == "VENUE" else None, team_id=ids[0] if scope == "TEAM" else None,
            label=label, explanation=explanation, lead_priority=priority))
    require(len(facts) == 51 and len({identity(f) for f in facts}) == 51, "live DECIDE exact set")
    return know, decide, facts


def main():
    from backend.spain_know_decide_publication import run
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.environ.get("MATCHGOER_HOSTED_DATABASE_URL"))
    parser.add_argument("--allow-remote-audit", action="store_true")
    args = parser.parse_args()
    require(args.database_url and args.allow_remote_audit, "read-only hosted audit requires explicit --allow-remote-audit")
    result = run(args.database_url, False)
    path = REPORTS / "spain-know-decide-dry-run-20260906.json"
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str)+"\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=True, default=str))


if __name__ == "__main__":
    main()
