"""Protected publisher for the reviewed France KNOW and DECIDE exact sets."""
from __future__ import annotations

import argparse, ast, csv, hashlib, json, os
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from sqlalchemy import bindparam, create_engine, text
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]
KNOW = ROOT / "reports/france/france-know-publication-inventory-20260906.csv"
DECIDE = ROOT / "reports/france/france-decide-reconciliation-20260906.csv"
CATALOGUE = ROOT / "reports/decide/decide-five-country-reconciliation-20260903.csv"
REVIEWED, REVIEW_AFTER = date(2026,9,6), date(2027,3,6)
APPROVED_AT = datetime(2026,9,6,tzinfo=timezone.utc)
REVIEWER = "Matchgoer France editorial approval 2026-09-06"
GS_COPY = "If supporter culture is important to you, this is one of the clubs worth seeing."
TABLES = ("teams","venues","fixtures","venue_provider_refs","club_venues","venue_guide_facts",
          "pre_match_spots","pre_match_spot_evidence","decision_facts","decision_evidence")
LOCAL = {None,"","localhost","127.0.0.1","::1"}
EXPECTED_ARTIFACTS = {
    KNOW: "3EEBF17535A28F0AE2C87C0E0528C03889C1AAAA7BF9EB92E199AB23A861AEEE",
    DECIDE: "40D82D1F6F03535134E9A78752E853B98D04968CDD9D7EC46F915DC2F48474E4",
}

class SafetyError(RuntimeError): pass
def rows(path):
    with path.open(encoding="utf-8-sig",newline="") as f: return list(csv.DictReader(f))
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest().upper()

def approved():
    for path, expected in EXPECTED_ARTIFACTS.items():
        if sha(path) != expected: raise SafetyError(f"reviewed artifact hash mismatch: {path}")
    know, reconciliation = rows(KNOW), rows(DECIDE)
    source = {(r["subject"],r["category"]):r for r in rows(CATALOGUE) if r["country"]=="France"}
    if len(know)!=36 or len(reconciliation)!=59: raise SafetyError("artifact count mismatch")
    if Counter(r["competition"] for r in know)!={"Ligue 1":18,"Ligue 2":18}: raise SafetyError("league count mismatch")
    if sum(r["intentional_null"]=="False" for r in know)!=21: raise SafetyError("BTM count mismatch")
    facts=[]
    for r in reconciliation:
        if r["current_status"]!="CURRENT": continue
        ids=list(map(int,ast.literal_eval(r["canonical_subject_ids"])))
        if r["category"]=="EXCEPTIONAL_SUPPORT":
            facts.append(dict(subject=r["editorial_subject"],subject_type="TEAM",team_a_id=None,team_b_id=None,
                venue_id=None,team_id=ids[0],attribute_key=r["category"],label="Exceptional support",
                explanation=GS_COPY,lead_priority="LEAD"))
        else:
            s=source[(r["editorial_subject"],r["category"])]; scope=s["scope"]
            facts.append(dict(subject=r["editorial_subject"],subject_type=scope,
                team_a_id=ids[0] if scope=="TEAM_PAIR" else None,team_b_id=ids[1] if scope=="TEAM_PAIR" else None,
                venue_id=ids[0] if scope=="VENUE" else None,team_id=None,attribute_key=r["category"],
                label=s["editorial_label"],explanation=s["short_explanation"],lead_priority=s["lead_priority"]))
    if len(facts)!=51 or sum(f["attribute_key"]=="EXCEPTIONAL_SUPPORT" for f in facts)!=12:
        raise SafetyError("DECIDE current contract mismatch")
    return know,reconciliation,facts

def decision_rows(c,f):
    return c.execute(text("""SELECT * FROM decision_facts WHERE subject_type=:subject_type AND attribute_key=:attribute_key
      AND team_a_id IS NOT DISTINCT FROM :team_a_id AND team_b_id IS NOT DISTINCT FROM :team_b_id
      AND venue_id IS NOT DISTINCT FROM :venue_id AND team_id IS NOT DISTINCT FROM :team_id"""),f).mappings().all()

def audit(c,know,reconciliation,facts,allow_content=False):
    tids=[int(r["canonical_team_id"]) for r in know]; expected={int(r["canonical_team_id"]):int(r["canonical_venue_id"]) for r in know}
    if expected[114]!=23298 or expected[94]!=23287: raise SafetyError("Paris FC or Rennes artifact identity mismatch")
    if c.execute(text("SELECT count(*) FROM teams WHERE team_id=ANY(:ids)"),{"ids":tids}).scalar_one()!=36:
        raise SafetyError("canonical team identity mismatch")
    if c.execute(text("SELECT count(*) FROM venues WHERE venue_id=ANY(:ids)"),{"ids":sorted(set(expected.values()))}).scalar_one()!=len(set(expected.values())):
        raise SafetyError("canonical venue identity mismatch")
    ref=c.execute(text("SELECT venue_id,is_primary FROM venue_provider_refs WHERE provider='api_football' AND provider_venue_id=18861")).mappings().all()
    if len(ref)!=1 or int(ref[0]["venue_id"])!=23298 or ref[0]["is_primary"] is not True: raise SafetyError("provider 18861 identity drift")
    if c.execute(text("SELECT count(*) FROM venue_provider_refs WHERE venue_id=23300")).scalar_one()!=0: raise SafetyError("venue 23300 provider ref changed")
    current=c.execute(text("""SELECT club_venue_id,team_id,venue_id,relationship_type,status FROM club_venues
      WHERE team_id=ANY(:ids) AND status='CURRENT'"""),{"ids":tids}).mappings().all()
    by={}; [by.setdefault(int(r["team_id"]),[]).append(dict(r)) for r in current]
    present=[]; missing=[]
    for tid,vid in expected.items():
        found=by.get(tid,[])
        if not found: missing.append((tid,vid))
        elif len(found)==1 and int(found[0]["venue_id"])==vid and found[0]["relationship_type"]=="HOME": present.append(found[0])
        else: raise SafetyError(f"conflicting current relationship for team {tid}: {found}")
    if any(int(r["venue_id"]) in (23295,23300) for r in by.get(114,[])): raise SafetyError("invalid Paris FC ownership")
    dec_present=[]; dec_missing=[]
    for f in facts:
        found=decision_rows(c,f)
        if len(found)>1: raise SafetyError(f"duplicate DECIDE fact: {f['subject']}")
        if not found: dec_missing.append(f); continue
        a=found[0]
        if (a["label"],a["explanation"],a["publication_status"],a["lead_priority"])!=(f["label"],f["explanation"],"PUBLISHED",f["lead_priority"]):
            raise SafetyError(f"contradictory DECIDE meaning: {f['subject']}")
        dec_present.append(f)
    cv_ids=[int(r["club_venue_id"]) for r in present]
    kcounts={"tickets":0,"btm":0,"evidence":0}
    if cv_ids:
        kcounts["tickets"]=c.execute(text("SELECT count(*) FROM venue_guide_facts WHERE club_venue_id=ANY(:ids)"),{"ids":cv_ids}).scalar_one()
        kcounts["btm"]=c.execute(text("SELECT count(*) FROM pre_match_spots WHERE club_venue_id=ANY(:ids)"),{"ids":cv_ids}).scalar_one()
        kcounts["evidence"]=c.execute(text("""SELECT count(*) FROM pre_match_spot_evidence e JOIN pre_match_spots s USING(pre_match_spot_id)
          WHERE s.club_venue_id=ANY(:ids)"""),{"ids":cv_ids}).scalar_one()
    if not allow_content and any(kcounts.values()): raise SafetyError(f"unexpected pre-existing France KNOW: {kcounts}")
    if allow_content and kcounts!={"tickets":36,"btm":21,"evidence":21}: raise SafetyError(f"France KNOW exact-set mismatch: {kcounts}")
    return {"club_venues_present":len(present),"club_venues_insert":len(missing),"missing":missing,
            "decide_present":len(dec_present),"decide_insert":len(dec_missing),"decide_missing":dec_missing,
            "dormant_no_write":sum(r["current_status"]=="DORMANT" for r in reconciliation),"know":kcounts}

def counts(c): return {t:c.execute(text(f'SELECT count(*) FROM "{t}"')).scalar_one() for t in TABLES}

def insert_know(c,know):
    for r in know:
        tid,vid=int(r["canonical_team_id"]),int(r["canonical_venue_id"])
        cv=c.execute(text("SELECT club_venue_id FROM club_venues WHERE team_id=:t AND venue_id=:v AND relationship_type='HOME' AND status='CURRENT'"),{"t":tid,"v":vid}).scalar_one()
        c.execute(text("""INSERT INTO venue_guide_facts(club_venue_id,section,topic,content,source_type,source_label,source_url,
          reviewed_at,confidence,status,review_after,expires_at,display_order) VALUES
          (:cv,'tickets_entry','Tickets',:content,'official',:label,:url,:reviewed,'high','current',:after,NULL,1)"""),
          {"cv":cv,"content":r["ticket_description"],"label":r["editorial_subject"],"url":r["ticket_url"],"reviewed":REVIEWED,"after":REVIEW_AFTER})
        if r["intentional_null"]=="False":
            sid=c.execute(text("""INSERT INTO pre_match_spots(club_venue_id,display_name,classification,audience,supporting_line,
              maps_destination,confidence,status,business_status,reviewed_at,review_after,display_order,approved_at,approved_by)
              VALUES (:cv,:name,:class,'HOME',:line,:dest,'HIGH','CURRENT','NOT_APPLICABLE',:reviewed,:after,1,:at,:by)
              RETURNING pre_match_spot_id"""),{"cv":cv,"name":r["display_name"],"class":r["classification"],"line":r["supporting_line"],
              "dest":r["maps_destination"],"reviewed":REVIEWED,"after":REVIEW_AFTER,"at":APPROVED_AT,"by":REVIEWER}).scalar_one()
            c.execute(text("""INSERT INTO pre_match_spot_evidence(pre_match_spot_id,source_type,source_url,source_date,disposition,evidence_note,review_status)
              VALUES (:sid,:source,NULL,:reviewed,'SUPPORTS','Supports the reviewed France display name, location and supporter-context classification.','ACCEPTED')"""),
              {"sid":sid,"source":r["btm_evidence_classification"],"reviewed":REVIEWED})

def run(url,write):
    know,reconciliation,facts=approved(); engine=create_engine(url,pool_pre_ping=True)
    with engine.connect() as c:
        tx=c.begin()
        try:
            c.execute(text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE" if write else "SET TRANSACTION READ ONLY"))
            pre=audit(c,know,reconciliation,facts); before=counts(c)
            if not write: tx.rollback(); return {"action":"dry-run","writes":0,"preflight":pre,"counts":before}
            for tid,vid in pre["missing"]: c.execute(text("INSERT INTO club_venues(team_id,venue_id,relationship_type,status) VALUES (:t,:v,'HOME','CURRENT')"),{"t":tid,"v":vid})
            insert_know(c,know)
            now=datetime.now(timezone.utc)
            for f in pre["decide_missing"]:
                c.execute(text("""INSERT INTO decision_facts(subject_type,team_a_id,team_b_id,venue_id,team_id,attribute_key,label,explanation,
                  publication_status,confidence,lead_priority,reviewed_at,reviewed_by) VALUES
                  (:subject_type,:team_a_id,:team_b_id,:venue_id,:team_id,:attribute_key,:label,:explanation,'PUBLISHED','HIGH',:lead_priority,:now,:by)"""),{**f,"now":now,"by":REVIEWER})
            post=audit(c,know,reconciliation,facts,True); after=counts(c)
            expected={"teams":0,"venues":0,"fixtures":0,"venue_provider_refs":0,"club_venues":pre["club_venues_insert"],
              "venue_guide_facts":36,"pre_match_spots":21,"pre_match_spot_evidence":21,"decision_facts":pre["decide_insert"],"decision_evidence":0}
            delta={t:after[t]-before[t] for t in TABLES}
            if delta!=expected: raise SafetyError(f"physical delta mismatch: {delta}")
            tx.commit()
        except Exception:
            if tx.is_active: tx.rollback()
            raise
    return {"action":"write","preflight":pre,"delta":delta,"final":post,"writes":sum(delta.values())}

def main():
    p=argparse.ArgumentParser(); p.add_argument("--database-url",default=os.environ.get("MATCHGOER_HOSTED_DATABASE_URL")); p.add_argument("--expected-script-sha256",required=True)
    p.add_argument("--write",action="store_true"); p.add_argument("--confirm-write",action="store_true"); p.add_argument("--allow-remote-audit",action="store_true"); p.add_argument("--allow-remote-write",action="store_true"); a=p.parse_args()
    actual=sha(Path(__file__))
    if actual!=a.expected_script_sha256.upper(): raise SafetyError("script hash mismatch")
    if not a.database_url: raise SafetyError("database URL required")
    if a.write!=a.confirm_write: raise SafetyError("write requires both confirmations")
    remote=make_url(a.database_url).host not in LOCAL
    if remote and a.write and not a.allow_remote_write: raise SafetyError("remote write refused without --allow-remote-write")
    if remote and not a.write and not a.allow_remote_audit: raise SafetyError("remote audit refused without --allow-remote-audit")
    result=run(a.database_url,a.write); result["script_sha256"]=actual; result["artifact_sha256"]={str(KNOW):sha(KNOW),str(DECIDE):sha(DECIDE)}
    print(json.dumps(result,indent=2,default=str,ensure_ascii=False))
if __name__=="__main__": main()
