"""Protected Spain publisher, mirroring the France serializable transaction path."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from backend.spain_know_decide_dry_run import (
    ANDORRA_FIXTURES, CATALOGUE, EXPECTED_ARTIFACTS, REPORTS, ROOT,
    SafetyError, approved, identity, require, sha,
)
from ingestion.provider_text import has_decodable_references, normalize_provider_text

REVIEWED, REVIEW_AFTER = date(2026,9,6), date(2027,3,6)
APPROVED_AT = datetime(2026,9,6,tzinfo=timezone.utc)
REVIEWER = "Matchgoer Spain editorial approval 2026-09-06"
NEW_VENUE = dict(name="Estadi de la FAF", address="Carretera de Vila 23–25, AD200 Encamp",
                 city="Encamp", country="Andorra", provider_venue_id=None,
                 capacity=None, latitude=None, longitude=None)
TABLE_KEYS = {"teams":"team_id", "venues":"venue_id", "fixtures":"fixture_id",
    "venue_names":"venue_name_id", "venue_provider_refs":"venue_provider_ref_id",
    "club_venues":"club_venue_id", "venue_guide_facts":"fact_id",
    "pre_match_spots":"pre_match_spot_id", "pre_match_spot_evidence":"evidence_id",
    "decision_facts":"fact_id", "decision_evidence":"evidence_id"}
LOCAL = {None,"","localhost","127.0.0.1","::1"}
TICKETS = REPORTS / "spain-ticket-preflight-20260906.json"
# Maintenance-only replacements established from each club's live official
# navigation. Frozen reviewed CSV bytes remain intact and hash-verifiable.
TICKET_MAINTENANCE = {
    4665: "https://abonados.realracingclub.es/",
    540: "https://www.rcdespanyol.com/es/proximos-partidos",
    720: "https://www.realvalladolid.es/ticketing",
    723: "https://tickets.udalmeriasad.com/",
    9593: "https://cesabadell.compralaentrada.com/",
}


def query(c, sql, **params):
    return [dict(r) for r in c.execute(text(sql), params).mappings()]


def same_content(actual, expected, context):
    differences = {k: {"expected":v,"actual":actual.get(k)} for k,v in expected.items() if actual.get(k) != v}
    require(not differences, f"contradictory {context}: {differences}")


def guide_values(r, entry=False):
    prefix = "entry" if entry else "ticket"
    return dict(section=r[f"{prefix}_section"], topic=r[f"{prefix}_topic"],
        content=r[f"{prefix}_description"], source_type=r[f"{prefix}_source_type"],
        source_label=r["editorial_subject"], source_url=r["entry_evidence_url"] if entry else TICKET_MAINTENANCE.get(int(r["canonical_team_id"]),r["ticket_url"]),
        reviewed_at=REVIEWED, confidence="high" if entry else r["ticket_confidence"],
        status="current" if entry else r["ticket_status"], review_after=REVIEW_AFTER,
        expires_at=None, display_order=2 if entry else 1)


def spot_values(r):
    return dict(display_name=r["display_name"], classification=r["classification"], audience=r["audience"],
        supporting_line=r["supporting_line"], maps_destination=r["maps_destination"],
        confidence=r["pre_match_confidence"], status=r["pre_match_status"], business_status=r["business_status"],
        reviewed_at=REVIEWED, review_after=REVIEW_AFTER, display_order=int(r["display_order"]),
        approved_at=APPROVED_AT, approved_by=REVIEWER)


def evidence_values(r):
    source = {"INDEPENDENT":"EDITORIAL_RESEARCH", "OFFICIAL":"OFFICIAL"}[r["btm_evidence_classification"]]
    return dict(source_type=source, source_url=r["btm_evidence_url"] or None, source_date=REVIEWED,
        disposition="SUPPORTS", evidence_note="Supports the reviewed Spain display name, location and supporter-context classification. "
        + f"Reviewed evidence classification: {r['btm_evidence_classification']}.", review_status="ACCEPTED")


def schema_violations(know,facts,columns):
    """Check reviewed content against actual hosted limits before any INSERT."""
    limits={(r["table_name"],r["column_name"]):r["character_maximum_length"] for r in columns}
    proposed=[]
    for r in know:
        subject=r["editorial_subject"]
        proposed.append(("venue_guide_facts",subject,guide_values(r)))
        if r["entry_description"]:
            proposed.append(("venue_guide_facts",subject,guide_values(r,True)))
        if r["intentional_null"]=="False":
            proposed.append(("pre_match_spots",subject,spot_values(r)))
            proposed.append(("pre_match_spot_evidence",subject,evidence_values(r)))
    proposed += [("decision_facts",f["subject"],f) for f in facts]
    proposed.append(("venues","FC Andorra",NEW_VENUE))
    violations=[]
    for table,subject,values in proposed:
        for field,value in values.items():
            limit=limits.get((table,field))
            if isinstance(value,str) and limit is not None and len(value)>limit:
                violations.append(dict(table=table,subject=subject,field=field,length=len(value),limit=limit))
    return violations


def validate_hosted_schema(c,know,facts):
    columns=query(c,"""SELECT table_name,column_name,character_maximum_length
        FROM information_schema.columns WHERE table_schema='public'
        AND character_maximum_length IS NOT NULL""")
    violations=schema_violations(know,facts,columns)
    require(not violations,f"BLOCKED — reviewed content exceeds hosted schema limits: {violations}")
    supporting=next(r for r in columns if r["table_name"]=="pre_match_spots" and r["column_name"]=="supporting_line")
    require(supporting["character_maximum_length"]==255,"approved BTM capacity must be exactly 255")


def html_plan(venues):
    changes = []
    before_keys, after_keys = {}, {}
    for r in venues:
        updated = dict(r)
        for field in ("city", "address"):
            before = r[field]
            after = normalize_provider_text(before)
            if before != after:
                changes.append(dict(venue_id=r["venue_id"], field=field, before=before, after=after))
                updated[field] = after
        for collection, value in ((before_keys,r),(after_keys,updated)):
            key = (value["name"], value["city"], value["country"])
            collection.setdefault(key, set()).add(value["venue_id"])
    collisions = [sorted(ids) for key,ids in after_keys.items() if len(ids)>1 and ids != before_keys.get(key)]
    require(not collisions, f"HTML identity collisions: {collisions}")
    return changes


def audit(c, know, reconciliation, facts, final=False):
    tids = [int(r["canonical_team_id"]) for r in know]
    teams = {r["team_id"]:r for r in query(c,"SELECT * FROM teams")}
    venues_list = query(c,"SELECT * FROM venues")
    venues = {r["venue_id"]:r for r in venues_list}
    refs = query(c,"SELECT * FROM venue_provider_refs")
    require(all(tid in teams for tid in tids), "missing KNOW canonical team")
    require({tid:teams[tid]["team_name"] for tid in (5262,5275)} == {5262:"FC Cartagena",5275:"Real Murcia"}, "Murcia/Cartagena identity drift")
    candidates = [v for v in venues_list if v["city"] == "Encamp" or v["name"] in ("Estadi de la FAF","Estadio de Encamp","Estadi de la FAF / Estadio de Encamp")]
    require(len(candidates) <= 1, "ambiguous Encamp canonical venue")
    encamp = candidates[0]["venue_id"] if candidates else -1
    if candidates:
        same_content(candidates[0], NEW_VENUE, "Encamp canonical venue")
        require(not any(r["venue_id"] == encamp for r in refs), "Encamp has unexpected provider reference")
    require(not final or encamp != -1, "missing final Encamp venue")
    same_content(venues[23567], dict(name="Estadi Nacional",city="Andorra la Vella",provider_venue_id=2618), "protected Estadi Nacional")
    for provider, vid in ((2618,23567),(1456,23269)):
        matches = [r for r in refs if r["provider"] == "api_football" and r["provider_venue_id"] == provider]
        require(len(matches)==1 and matches[0]["venue_id"]==vid and matches[0]["is_primary"], f"provider venue {provider} drift")
    expected = {int(r["canonical_team_id"]):int(r["canonical_venue_id"]) if r["canonical_venue_id"] else encamp for r in know}
    for r in know:
        tid,vid = int(r["canonical_team_id"]), expected[int(r["canonical_team_id"]) ]
        if tid == 8157:
            continue
        require(vid in venues, f"missing venue {vid}")
        matches = [p for p in refs if p["provider"]=="api_football" and p["provider_venue_id"]==int(r["provider_venue_id"])]
        require(len(matches)==1 and matches[0]["venue_id"]==vid and matches[0]["is_primary"], f"KNOW provider identity drift: {r['editorial_subject']}")
    current = query(c,"SELECT * FROM club_venues WHERE team_id=ANY(:ids) AND status='CURRENT'",ids=tids)
    present, missing = {}, []
    for tid,vid in expected.items():
        found = [r for r in current if r["team_id"]==tid]
        if not found:
            missing.append(dict(team_id=tid,venue_id=vid))
        else:
            require(len(found)==1 and found[0]["venue_id"]==vid and found[0]["relationship_type"]=="HOME", f"conflicting current relationship {tid}")
            present[tid]=found[0]["club_venue_id"]
    cv_ids = list(present.values())
    guides=query(c,"SELECT * FROM venue_guide_facts WHERE club_venue_id=ANY(:ids)",ids=cv_ids)
    spots=query(c,"SELECT * FROM pre_match_spots WHERE club_venue_id=ANY(:ids)",ids=cv_ids)
    evidence=query(c,"SELECT e.* FROM pre_match_spot_evidence e JOIN pre_match_spots s USING(pre_match_spot_id) WHERE s.club_venue_id=ANY(:ids)",ids=cv_ids)
    guide_missing,spot_missing,evidence_missing = [],[],[]
    for r in know:
        tid=int(r["canonical_team_id"]); cv=present.get(tid)
        expected_guides=[guide_values(r)]+([guide_values(r,True)] if r["entry_description"] else [])
        owned=[g for g in guides if g["club_venue_id"]==cv]
        require(all(g["topic"] in [v["topic"] for v in expected_guides] for g in owned), f"extra KNOW topic for {tid}")
        for values in expected_guides:
            found=[g for g in owned if g["topic"]==values["topic"]]
            require(len(found)<=1, f"duplicate guide topic {tid}")
            if found:
                same_content(found[0],values,f"guide {tid}/{values['topic']}")
            else:
                guide_missing.append(dict(team_id=tid,values=values))
        owned_spots=[s for s in spots if s["club_venue_id"]==cv]
        if r["intentional_null"]=="True":
            require(not owned_spots,f"intentional NULL BTM contains spots {tid}")
            continue
        require(len(owned_spots)<=1,f"duplicate BTM {tid}")
        if not owned_spots:
            spot_missing.append(dict(team_id=tid,values=spot_values(r),evidence=evidence_values(r)))
        else:
            same_content(owned_spots[0],spot_values(r),f"BTM {tid}")
            sid=owned_spots[0]["pre_match_spot_id"]
            found=[e for e in evidence if e["pre_match_spot_id"]==sid]
            require(len(found)<=1,f"unexpected evidence count {tid}")
            if found:
                same_content(found[0],evidence_values(r),f"BTM evidence {tid}")
            else:
                evidence_missing.append(dict(pre_match_spot_id=sid,values=evidence_values(r)))
    all_facts=query(c,"SELECT * FROM decision_facts")
    wanted={identity(f) for f in facts}
    # Include all Spain canonical subjects, so unrelated live Spain facts cannot
    # silently survive the exact-set acceptance check.
    # teams has no country column. Include the reviewed DECIDE-only opponents
    # (notably Hercules and Zaragoza), plus teams registered at Spanish venues.
    reviewed_teams={f[k] for f in facts for k in ("team_id","team_a_id","team_b_id") if f[k] is not None}
    spanish_teams={tid for tid,t in teams.items() if venues.get(t.get("venue_id"),{}).get("country")=="Spain"} | set(tids) | reviewed_teams
    spanish_venues={vid for vid,v in venues.items() if v["country"]=="Spain"}
    scoped=[f for f in all_facts if f["publication_status"]=="PUBLISHED" and
            (f["team_id"] in spanish_teams or f["venue_id"] in spanish_venues or
             (f["team_a_id"] in spanish_teams and f["team_b_id"] in spanish_teams))]
    require(all(identity(f) in wanted for f in scoped), "unapproved live Spain DECIDE fact")
    decide_missing=[]
    for f in facts:
        if f["subject_type"]=="TEAM_PAIR":
            require(f["team_a_id"] in teams and f["team_b_id"] in teams,"missing rivalry canonical identity")
        elif f["subject_type"]=="TEAM":
            require(f["team_id"] in teams,"missing Great Support team")
        else:
            require(f["venue_id"] in venues,"missing DECIDE venue")
        found=[a for a in all_facts if identity(a)==identity(f)]
        require(len(found)<=1,f"duplicate DECIDE {f['subject']}")
        if found:
            same_content(found[0],{k:f[k] for k in ("label","explanation","lead_priority")}|{"publication_status":"PUBLISHED"},f"DECIDE {f['subject']}")
        else:
            decide_missing.append(f)
    andorra=query(c,"SELECT * FROM fixtures WHERE home_team_id=8157 ORDER BY fixture_id")
    selected=[f for f in andorra if f["season"]==2026 and f["league_id"]==141 and f["venue_name"]=="Estadi de la FAF" and f["venue_city"]=="Encamp"]
    require([f["fixture_id"] for f in selected]==ANDORRA_FIXTURES,"Andorra exact fixture inventory drift")
    require(all(f["venue_id"] in ({encamp} if final else {23567,encamp}) for f in selected),"Andorra unexpected venue FK")
    unspecified=[f for f in andorra if not f["venue_name"] and not f["venue_city"]]
    madrid=query(c,"SELECT * FROM fixtures WHERE home_team_id=541 AND season=2026 AND league_id=140 ORDER BY fixture_id")
    require(len(madrid)==19,"Madrid home fixture count drift")
    require(any(f["fixture_id"]==1570340 and f["away_team_id"]==548 for f in madrid),"Madrid approved fixture identity drift")
    require(all(f["venue_id"]==23269 for f in madrid if f["fixture_id"]!=1570340),"Madrid broader fixture correction required")
    target=next(f for f in madrid if f["fixture_id"]==1570340)
    require(target["venue_id"] in ({23269} if final else {23238,23269}),"Madrid approved fixture FK drift")
    fixture_updates=[dict(fixture_id=f["fixture_id"],before=f["venue_id"],after=encamp) for f in selected if f["venue_id"]!=encamp]
    if target["venue_id"]!=23269:
        fixture_updates.append(dict(fixture_id=1570340,before=target["venue_id"],after=23269))
    html=html_plan(venues_list)
    if final:
        require(not any((missing,guide_missing,spot_missing,evidence_missing,decide_missing,fixture_updates,html)),"incomplete final publication")
        require(len(guides)==47 and len(spots)==18 and len(evidence)==18,"KNOW final exact set")
        require(len(scoped)==51,"DECIDE final live count")
        require(not any(has_decodable_references(v[field]) for v in venues_list for field in ("city","address")),"unintended HTML references remain")
        require(any(v["city"]=="Villeneuve d'Ascq" for v in venues_list),"Lille plain-text acceptance")
    mutations={t:{"INSERT":0,"UPDATE":0,"DELETE":0} for t in TABLE_KEYS}
    for table,n in {"venues":int(encamp==-1),"venue_names":int(encamp==-1),"club_venues":len(missing),
        "venue_guide_facts":len(guide_missing),"pre_match_spots":len(spot_missing),
        "pre_match_spot_evidence":len(spot_missing)+len(evidence_missing),"decision_facts":len(decide_missing)}.items():
        mutations[table]["INSERT"]=n
    mutations["venues"]["UPDATE"]=len({v["venue_id"] for v in html})
    mutations["fixtures"]["UPDATE"]=len(fixture_updates)
    return dict(encamp_venue_id=encamp,relationships_missing=missing,guide_missing=guide_missing,
        spot_missing=spot_missing,evidence_missing=evidence_missing,decide_missing=decide_missing,
        fixture_updates=fixture_updates,html_plan=html,html_values=len(html),html_previous_audit_delta=len(html)-44,
        html_collisions=0,proposed_mutations=mutations,unrelated_mutations=0,
        know=dict(clubs=42,relationships_present=len(present),tickets=sum(g["topic"]=="Tickets" for g in guides),
                  entry=sum(g["topic"]=="Entry" for g in guides),btm=len(spots),intentional_null=24,evidence=len(evidence)),
        decide=dict(catalogue=52,current=51,dormant_no_write=1,present=51-len(decide_missing),
                    categories=dict(Counter(r["category"] for r in reconciliation)),
                    great_support=[dict(team_id=f["team_id"],club=f["subject"]) for f in facts if f["subject_type"]=="TEAM"]),
        andorra_fixture_ids=ANDORRA_FIXTURES,andorra_unspecified_hosted=[f["fixture_id"] for f in unspecified],
        andorra_unspecified_note="Five provider-unspecified fixtures were described in the review; none are currently hosted. No insert or assignment is proposed." if not unspecified else "Unspecified hosted fixtures remain untouched.",
        madrid_correct=sum(f["venue_id"]==23269 for f in madrid),murcia_pair={5262:"FC Cartagena",5275:"Real Murcia"},
        unresolved=["Real Murcia provider venue 3989 inconsistency retained for later fixture-venue audit."])


def snapshots(c):
    result={}
    tables=[r["tablename"] for r in query(c,"SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")]
    for table in tables:
        quoted=c.dialect.identifier_preparer.quote(table)
        if table in TABLE_KEYS:
            key=TABLE_KEYS[table]
            result[table]={r["id"]:r["digest"] for r in query(c,f'SELECT "{key}" AS id,md5(to_jsonb(t)::text) AS digest FROM {quoted} t')}
        else:
            # Keep private/non-publication values in PostgreSQL. Only a table
            # fingerprint is returned, sufficient to prove no unrelated write.
            result[table]=c.execute(text(f"SELECT md5(coalesce(string_agg(h,'' ORDER BY h),'')) FROM (SELECT md5(to_jsonb(t)::text) h FROM {quoted} t) s")).scalar_one()
    return result


def physical_diff(before,after):
    require(before.keys()==after.keys(),"unexpected schema change")
    result={}
    for table,b in before.items():
        a=after[table]
        if isinstance(b,dict):
            result[table]={"INSERT":sorted(a.keys()-b.keys()),"DELETE":sorted(b.keys()-a.keys()),
                           "UPDATE":sorted(k for k in b.keys() & a.keys() if b[k]!=a[k])}
        else:
            require(a==b,f"unrelated table changed: {table}")
    return result


def changed_rows(c,plan):
    return {
        "venues":query(c,"SELECT * FROM venues WHERE venue_id=ANY(:ids) ORDER BY venue_id",
                       ids=sorted({r["venue_id"] for r in plan["html_plan"]})),
        "fixtures":query(c,"SELECT * FROM fixtures WHERE fixture_id=ANY(:ids) ORDER BY fixture_id",
                         ids=sorted(r["fixture_id"] for r in plan["fixture_updates"])),
    }


def verify_changed_columns(before,after,plan,encamp):
    for table,old_rows in before.items():
        key=TABLE_KEYS[table]
        require([r[key] for r in old_rows]==[r[key] for r in after[table]],"changed-row inventory drift")
        for old,new in zip(old_rows,after[table]):
            expected=dict(old)
            if table=="venues":
                for change in plan["html_plan"]:
                    if change["venue_id"]==old[key]:
                        expected[change["field"]]=change["after"]
            else:
                change=next(r for r in plan["fixture_updates"] if r["fixture_id"]==old[key])
                expected["venue_id"]=encamp if change["after"]==-1 else change["after"]
            same_content(new,expected,f"physical columns {table}/{old[key]}")


def insert(c,table,values):
    require(table in TABLE_KEYS,"unapproved insert table")
    cols=','.join(values); params=','.join(':'+k for k in values)
    return c.execute(text(f'INSERT INTO {table} ({cols}) VALUES ({params}) RETURNING {TABLE_KEYS[table]}'),values).scalar_one()


def publish(c,know,plan):
    inserted={t:[] for t in TABLE_KEYS}
    def add(table,values):
        key=insert(c,table,values); inserted[table].append(key); return key
    encamp=plan["encamp_venue_id"]
    if encamp==-1:
        encamp=add("venues",NEW_VENUE)
        add("venue_names",dict(venue_id=encamp,name=NEW_VENUE["name"],normalized_name="estadi de la faf",
            name_type="current",source="reviewed_spain_publication_20260906"))
    for r in plan["relationships_missing"]:
        add("club_venues",dict(team_id=r["team_id"],venue_id=encamp if r["venue_id"]==-1 else r["venue_id"],relationship_type="HOME",status="CURRENT"))
    cvs={r["team_id"]:r["club_venue_id"] for r in query(c,"SELECT team_id,club_venue_id FROM club_venues WHERE team_id=ANY(:ids) AND status='CURRENT' AND relationship_type='HOME'",ids=[int(r["canonical_team_id"]) for r in know])}
    for r in plan["guide_missing"]:
        add("venue_guide_facts",dict(club_venue_id=cvs[r["team_id"]],**r["values"]))
    for r in plan["spot_missing"]:
        sid=add("pre_match_spots",dict(club_venue_id=cvs[r["team_id"]],**r["values"]))
        add("pre_match_spot_evidence",dict(pre_match_spot_id=sid,**r["evidence"]))
    for r in plan["evidence_missing"]:
        add("pre_match_spot_evidence",dict(pre_match_spot_id=r["pre_match_spot_id"],**r["values"]))
    for f in plan["decide_missing"]:
        values={k:v for k,v in f.items() if k!="subject"}
        add("decision_facts",dict(**values,publication_status="PUBLISHED",confidence="HIGH",reviewed_at=APPROVED_AT,reviewed_by=REVIEWER))
    for r in plan["fixture_updates"]:
        count=c.execute(text("UPDATE fixtures SET venue_id=:after WHERE fixture_id=:fixture_id AND venue_id=:before"),
            {**r,"after":encamp if r["after"]==-1 else r["after"]}).rowcount
        require(count==1,"fixture BEFORE state drift")
    for r in plan["html_plan"]:
        require(r["field"] in ("city","address"),"HTML field outside scope")
        count=c.execute(text(f'UPDATE venues SET {r["field"]}=:after WHERE venue_id=:venue_id AND {r["field"]}=:before'),r).rowcount
        require(count==1,"HTML BEFORE state drift")
    return inserted


def verify_ticket_report(know):
    require(TICKETS.is_file(),"ticket preflight report required")
    report=json.loads(TICKETS.read_text(encoding="utf-8"))
    require(datetime.now(timezone.utc)-datetime.fromisoformat(report["checked_at"]) < timedelta(hours=24),"ticket preflight stale")
    require(len(report["routes"])==42,"ticket report count")
    by={r["team_id"]:r for r in report["routes"]}
    for r in know:
        check=by[int(r["canonical_team_id"])]
        require(check["url"]==r["ticket_url"] and check.get("accepted") is True,f"ticket preflight unresolved: {r['editorial_subject']}")
        require(check["publication_url"]==guide_values(r)["source_url"],"ticket maintenance report mismatch")
    return report


def run(url,write,backup=None,expected_plan=None):
    know,reconciliation,facts=approved()
    if write:
        verify_ticket_report(know)
        require(backup and Path(backup).is_file(),"validated full backup manifest required")
        manifest=json.loads(Path(backup).read_text(encoding="utf-8"))
        require(manifest["archive_validated"] is True and sha(manifest["path"])==manifest["sha256"],"backup validation failed")
        target=make_url(url)
        source_identity=hashlib.sha256(f'{target.host}:{target.port or 5432}/{target.database}'.encode()).hexdigest()
        require(manifest["source_identity_sha256"]==source_identity,"backup belongs to another database")
        require(datetime.now(timezone.utc)-datetime.fromisoformat(manifest["timestamp_utc"]) < timedelta(hours=1),"backup is not immediate pre-write")
        require(expected_plan and Path(expected_plan).is_file(),"reviewable dry-run plan required")
    engine=create_engine(url,pool_pre_ping=True)
    with engine.connect() as c:
        tx=c.begin()
        try:
            c.execute(text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE" if write else "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
            if write:
                # Prevent ingestion/content changes during the snapshot and
                # guarded write, including concurrent same-topic inserts.
                c.execute(text("SET LOCAL lock_timeout='15s'"))
                c.execute(text("LOCK TABLE "+','.join(TABLE_KEYS)+" IN SHARE ROW EXCLUSIVE MODE"))
            validate_hosted_schema(c,know,facts)
            pre=audit(c,know,reconciliation,facts)
            hashes={p.name:sha(p) for p in EXPECTED_ARTIFACTS}
            implementation={str(p.relative_to(ROOT)):sha(p) for p in (
                Path(__file__),ROOT/"backend/spain_know_decide_dry_run.py",ROOT/"ingestion/provider_text.py",
                ROOT/"backend/models.py",ROOT/"backend/know_population.py",
                ROOT/"backend/migrations/20260906_btm_supporting_line_capacity.sql",CATALOGUE,TICKETS)}
            if not write:
                tx.rollback()
                return dict(action="dry-run",hosted_writes=0,migrations=0,artifact_sha256=hashes,
                    catalogue_sha256=sha(CATALOGUE),implementation_sha256=implementation,preflight=pre)
            frozen=json.loads(Path(expected_plan).read_text(encoding="utf-8"))
            require(json.loads(json.dumps(pre,default=str))==frozen["preflight"],"dry-run plan drift; rerun read-only review")
            require(implementation==frozen["implementation_sha256"],"implementation/input drift since dry run")
            before=snapshots(c)
            columns_before=changed_rows(c,pre)
            inserted=publish(c,know,pre)
            post=audit(c,know,reconciliation,facts,final=True)
            verify_changed_columns(columns_before,changed_rows(c,pre),pre,post["encamp_venue_id"])
            after=snapshots(c); diff=physical_diff(before,after)
            for table,delta in diff.items():
                require(delta["INSERT"]==sorted(inserted[table]),f"unexpected inserts: {table}")
                require(not delta["DELETE"],f"unexpected deletes: {table}")
                allowed=sorted({r["venue_id"] for r in pre["html_plan"]}) if table=="venues" else sorted(r["fixture_id"] for r in pre["fixture_updates"]) if table=="fixtures" else []
                require(delta["UPDATE"]==allowed,f"unexpected updates: {table}")
                require({k:len(v) for k,v in delta.items()}==pre["proposed_mutations"][table],f"physical mutation count mismatch: {table}")
            tx.commit()
        except Exception:
            if tx.is_active:
                tx.rollback()
            raise
    return dict(action="write",artifact_sha256=hashes,preflight=pre,final=post,physical_diff=diff,
        mutation_counts={t:{k:len(v) for k,v in d.items()} for t,d in diff.items()},
        unrelated_mutations=0,all_public_tables_verified=sorted(before),migrations=0)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--database-url",default=os.environ.get("MATCHGOER_HOSTED_DATABASE_URL"))
    p.add_argument("--expected-script-sha256",required=True)
    p.add_argument("--write",action="store_true"); p.add_argument("--confirm-write",action="store_true")
    p.add_argument("--allow-remote-audit",action="store_true"); p.add_argument("--allow-remote-write",action="store_true")
    p.add_argument("--backup-manifest",type=Path); p.add_argument("--approved-plan",type=Path)
    p.add_argument("--output",type=Path)
    a=p.parse_args()
    require(sha(__file__)==a.expected_script_sha256.upper(),"publication script hash mismatch")
    require(a.database_url,"database URL required")
    require(a.write==a.confirm_write,"write requires both confirmations")
    remote=make_url(a.database_url).host not in LOCAL
    require(not remote or (a.allow_remote_write if a.write else a.allow_remote_audit),"remote access protection")
    result=run(a.database_url,a.write,a.backup_manifest,a.approved_plan)
    result["script_sha256"]=sha(__file__)
    if a.output:
        a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2,default=str)+"\n",encoding="utf-8")
    print(json.dumps(result,ensure_ascii=True,indent=2,default=str))


if __name__=="__main__":
    main()
