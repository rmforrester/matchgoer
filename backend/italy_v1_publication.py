"""Hash-bound Italy v1 structural, BTM and KNOW publication."""
from __future__ import annotations

import argparse, hashlib, json, os
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
STRUCTURAL = ROOT / "reports/italy-2026-27-preflight/italy-structural-repair-manifest.json"
KNOW = ROOT / "reports/italy-v1-publication/italy-know-v1-manifest.json"
DENOMINATOR = ROOT / "reports/italy-2026-27-preflight/italy-2026-27-senior-denominator.json"
STRUCTURAL_SHA = "641cceadb52759138b8e49b537a7269e832eee3f59736a4b153903750896277a"
ALCIONE_FIXTURES = [1608231,1608252,1608281,1608301,1608322,1608331,1608351,1608371,1608391,1608411,1608431,1608452,1608461,1608486,1608502,1608531,1608551,1608571,1608591]
ALLOWED = {"venues","venue_names","venue_provider_refs","teams","fixtures","club_venues","pre_match_spots","pre_match_spot_evidence","know_facts","know_fact_evidence"}
PK = {"venues":"venue_id","venue_names":"venue_name_id","venue_provider_refs":"venue_provider_ref_id","teams":"team_id","fixtures":"fixture_id","club_venues":"club_venue_id","pre_match_spots":"pre_match_spot_id","pre_match_spot_evidence":"evidence_id","know_facts":"know_fact_id","know_fact_evidence":"evidence_id"}

def require(ok, message):
    if not ok: raise RuntimeError(message)
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest().lower()
def q(c, sql, **params): return [dict(r) for r in c.execute(text(sql), params).mappings()]
def one(c, sql, **params): return c.execute(text(sql), params).mappings().one_or_none()

def fingerprints(c):
    out={}
    for (table,) in c.execute(text("select tablename from pg_tables where schemaname='public' order by tablename")):
        quoted=c.dialect.identifier_preparer.quote(table)
        out[table]=c.execute(text(f"select md5(coalesce(string_agg(h,'' order by h),'')) from (select md5(to_jsonb(t)::text) h from {quoted} t) s")).scalar_one()
    return out

def load():
    require(sha(STRUCTURAL)==STRUCTURAL_SHA,"structural manifest hash drift")
    structural=json.loads(STRUCTURAL.read_text(encoding="utf8")); require(len(structural)==38,"38 structural rows required")
    know=json.loads(KNOW.read_text(encoding="utf8")); require(len(know["declared_keys"])==27,"declared KNOW key set drift")
    require(len(know["facts"])==len(know["evidence"])==26,"approved KNOW set must be 26/26")
    return structural,know

def structural_plan(c, rows):
    simple=[]
    for row in rows:
        if row["team_id"] in (17824,26356): continue
        tid,vid=row["team_id"],row["correct_state"]["venue_id"]
        team=one(c,"select team_id,venue_id from teams where team_id=:id",id=tid); require(team and team["venue_id"]==vid,f"team/venue drift {tid}")
        current=q(c,"select * from club_venues where team_id=:id and status='CURRENT'",id=tid)
        if current: require(len(current)==1 and current[0]["venue_id"]==vid and current[0]["relationship_type"]=="HOME",f"conflicting current relationship {tid}")
        else: simple.append((tid,vid))
    alcione_ref=one(c,"select r.venue_id,v.name,v.city from venue_provider_refs r join venues v using(venue_id) where r.provider='api_football' and r.provider_venue_id=2772")
    if alcione_ref: require(alcione_ref["name"]=="Stadio Ferruccio" and alcione_ref["city"]=="Seregno","provider 2772 identity conflict")
    alcione_cv=q(c,"select * from club_venues where team_id=17824 and status='CURRENT'")
    if alcione_cv: require(alcione_ref and len(alcione_cv)==1 and alcione_cv[0]["venue_id"]==alcione_ref["venue_id"] and alcione_cv[0]["relationship_type"]=="HOME","Alcione relationship conflict")
    union=one(c,"select venue_id from teams where team_id=26356"); require(union is not None,"Union Brescia missing")
    require(one(c,"select venue_id from venue_provider_refs where provider='api_football' and provider_venue_id=882")["venue_id"]==23440,"Rigamonti identity drift")
    union_cv=q(c,"select * from club_venues where team_id=26356 and status='CURRENT'")
    if union_cv: require(len(union_cv)==1 and union_cv[0]["venue_id"]==23440 and union_cv[0]["relationship_type"]=="HOME","Union relationship conflict")
    fixture_state=q(c,"select fixture_id,venue_id,venue_name,venue_city from fixtures where fixture_id=any(:ids) order by fixture_id",ids=ALCIONE_FIXTURES)
    require(len(fixture_state)==19,"Alcione fixture exact set drift")
    fixture_updates=sum(not (r["venue_id"]==(alcione_ref or {}).get("venue_id") and r["venue_name"]=="Stadio Ferruccio" and r["venue_city"]=="Seregno") for r in fixture_state) if alcione_ref else 19
    return {"simple_relationship_inserts":simple,"alcione_venue_insert":not bool(alcione_ref),"alcione_venue_id":alcione_ref["venue_id"] if alcione_ref else None,"alcione_team_update":not alcione_ref or one(c,"select venue_id from teams where team_id=17824")["venue_id"]!=alcione_ref["venue_id"],"alcione_fixture_updates":fixture_updates,"alcione_relationship_insert":not bool(alcione_cv),"union_team_update":union["venue_id"]!=23440,"union_relationship_insert":not bool(union_cv)}

BTM_TARGET={
  507:{"display_name":"Del Duca / Curva Sud approach","classification":"SUPPORTER_AREA","audience":"MIXED","supporting_line":"Del Duca / Curva Sud approach is a pre-match meeting point for Ascoli supporters.","maps_destination":"Del Duca / Curva Sud approach, Ascoli Piceno","location_context":None,"confidence":"MEDIUM","status":"CURRENT","business_status":"NOT_APPLICABLE","reviewed_at":date(2026,9,7),"review_after":date(2027,3,7),"display_order":1,"approved_at":datetime(2026,9,7,tzinfo=timezone.utc),"approved_by":"Matchgoer frozen five-country BTM editorial review"},
  6379:{"display_name":"Bar Stadio","classification":"SUPPORTER_SPOT","audience":"HOME","supporting_line":None,"maps_destination":None,"location_context":None,"confidence":"HIGH","status":"CURRENT","business_status":"OPEN","reviewed_at":date(2026,9,10),"review_after":date(2027,3,10),"display_order":1,"approved_at":datetime(2026,9,10,tzinfo=timezone.utc),"approved_by":"Matchgoer frozen Italy v1 editorial approval"},
}
PALERMO={"display_name":"SiamoAquile Bar&Store / Stadio Renzo Barbera","classification":"CLUB_MATCHDAY_VENUE","business_status":"NOT_APPLICABLE","maps_destination":None,"location_context":None}

def btm_plan(c):
    inserts=[]
    for tid,target in BTM_TARGET.items():
        cv=one(c,"select club_venue_id from club_venues where team_id=:id and relationship_type='HOME' and status='CURRENT'",id=tid)
        if not cv: inserts.append({"team_id":tid,"blocked":"relationship_missing"}); continue
        existing=q(c,"select s.* from pre_match_spots s where club_venue_id=:cv",cv=cv["club_venue_id"])
        if not existing: inserts.append({"team_id":tid,"club_venue_id":cv["club_venue_id"]})
        else:
            require(len(existing)==1,f"unexpected BTM cardinality {tid}")
            require(all(existing[0].get(k)==v for k,v in target.items()),f"BTM state conflict {tid}")
    pal=one(c,"select s.* from pre_match_spots s join club_venues cv using(club_venue_id) where cv.team_id=522")
    require(pal,"Palermo BTM missing")
    pal_update=any(pal.get(k)!=v for k,v in PALERMO.items())
    av=one(c,"select s.* from pre_match_spots s join club_venues cv using(club_venue_id) where cv.team_id=528")
    require(av and av["display_name"]=="Old Style Pub" and av["business_status"]=="UNKNOWN","Avellino hold drift")
    return {"inserts":inserts,"palermo_spot_id":pal["pre_match_spot_id"],"palermo_update":pal_update}

def know_plan(c, pack):
    keys=[r["editorial_key"] for r in pack["facts"]]
    existing=q(c,"select editorial_key from know_facts where editorial_key=any(:keys)",keys=keys)
    require(not existing or len(existing)==26,"partial KNOW collision")
    atalanta=q(c,"select k.* from know_facts k where k.team_id=499 and k.publication_status='PUBLISHED'")
    require(len(atalanta)==2 and {r["module"] for r in atalanta}=={"CLUB","SUPPORTERS"},"Atalanta exact two facts drift")
    return {"state":"EXACTLY_PRESENT" if len(existing)==26 else "ABSENT","fact_inserts":0 if existing else 26,"evidence_inserts":0 if existing else 26,"atalanta":2}

def apply_structural(c, plan):
    for tid,vid in plan["simple_relationship_inserts"]: c.execute(text("insert into club_venues(team_id,venue_id,relationship_type,status) values(:t,:v,'HOME','CURRENT')"),{"t":tid,"v":vid})
    vid=plan["alcione_venue_id"]
    if plan["alcione_venue_insert"]:
        vid=c.execute(text("insert into venues(provider_venue_id,name,address,city,country,capacity) values(2772,'Stadio Ferruccio','Via Avogadro','Seregno','Italy',3700) returning venue_id")).scalar_one()
        c.execute(text("insert into venue_provider_refs(venue_id,provider,provider_venue_id,is_primary) values(:v,'api_football',2772,true)"),{"v":vid})
        c.execute(text("insert into venue_names(venue_id,name,normalized_name,name_type,source) values(:v,'Stadio Ferruccio','stadio ferruccio','current','manual_verified'),(:v,'Stadio Ferrucio','stadio ferrucio','provider','api_football')"),{"v":vid})
    if plan["alcione_team_update"]: c.execute(text("update teams set venue_id=:v where team_id=17824"),{"v":vid})
    if plan["alcione_fixture_updates"]: c.execute(text("update fixtures set venue_id=:v,venue_name='Stadio Ferruccio',venue_city='Seregno' where fixture_id=any(:ids)"),{"v":vid,"ids":ALCIONE_FIXTURES})
    if plan["alcione_relationship_insert"]: c.execute(text("insert into club_venues(team_id,venue_id,relationship_type,status) values(17824,:v,'HOME','CURRENT')"),{"v":vid})
    if plan["union_team_update"]: c.execute(text("update teams set venue_id=23440 where team_id=26356"))
    if plan["union_relationship_insert"]: c.execute(text("insert into club_venues(team_id,venue_id,relationship_type,status) values(26356,23440,'HOME','CURRENT')"))

def apply_btm(c, plan):
    inserted=[]
    for item in plan["inserts"]:
        require("blocked" not in item,f"BTM relationship blocker {item}")
        target=BTM_TARGET[item["team_id"]]
        sid=c.execute(text("""insert into pre_match_spots(club_venue_id,display_name,classification,audience,supporting_line,maps_destination,location_context,confidence,status,business_status,reviewed_at,review_after,display_order,approved_at,approved_by) values(:club_venue_id,:display_name,:classification,:audience,:supporting_line,:maps_destination,:location_context,:confidence,:status,:business_status,:reviewed_at,:review_after,:display_order,:approved_at,:approved_by) returning pre_match_spot_id"""),{"club_venue_id":item["club_venue_id"],**target}).scalar_one()
        c.execute(text("""insert into pre_match_spot_evidence(pre_match_spot_id,source_type,source_date,disposition,evidence_note,review_status) values(:sid,'EDITORIAL_RESEARCH','2026-09-10','SUPPORTS',:note,'ACCEPTED')"""),{"sid":sid,"note":"Frozen Italy v1 approved catalogue reconciliation; existing approved editorial identity preserved."})
        inserted.append(sid)
    if plan["palermo_update"]: c.execute(text("update pre_match_spots set display_name=:display_name,classification=:classification,business_status=:business_status,maps_destination=:maps_destination,location_context=:location_context where pre_match_spot_id=:id"),{**PALERMO,"id":plan["palermo_spot_id"]})
    return inserted

def apply_know(c, pack, plan):
    if plan["state"]=="EXACTLY_PRESENT": return []
    ids={}
    for raw in pack["facts"]:
        row=dict(raw); row.pop("identity_sha256",None)
        ids[row["editorial_key"]]=c.execute(text("""insert into know_facts(editorial_key,team_id,club_venue_id,venue_id,fixture_id,module,headline,content,display_order,publication_status,confidence,claim_sensitivity,reviewed_at,review_after,expires_at,approved_at,approved_by) values(:editorial_key,:team_id,:club_venue_id,:venue_id,:fixture_id,:module,:headline,:content,:display_order,:publication_status,:confidence,:claim_sensitivity,:reviewed_at,:review_after,:expires_at,:approved_at,:approved_by) returning know_fact_id"""),row).scalar_one()
    for raw in pack["evidence"]:
        row=dict(raw); row.pop("identity_sha256",None); row["know_fact_id"]=ids[row.pop("fact_editorial_key")]
        c.execute(text("""insert into know_fact_evidence(know_fact_id,source_type,source_title,source_url,source_date,evidence_note,disposition,review_status,contributor_user_id) values(:know_fact_id,:source_type,:source_title,:source_url,:source_date,:evidence_note,:disposition,:review_status,:contributor_user_id)"""),row)
    return list(ids.values())

def audit(c, structural, know):
    sp=structural_plan(c,structural); bp=btm_plan(c); kp=know_plan(c,know)
    denominator=json.loads(DENOMINATOR.read_text(encoding="utf8"))
    tids=[int(r["team_id"]) for r in denominator if r["classification"]=="SENIOR_FIRST_TEAM"]
    require(len(tids)==78 and len(set(tids))==78,"Italy denominator drift")
    current=c.execute(text("select count(distinct team_id) from club_venues where team_id=any(:ids) and relationship_type='HOME' and status='CURRENT'"),{"ids":tids}).scalar_one()
    serving=c.execute(text("""select count(distinct cv.team_id) from pre_match_spots s join club_venues cv using(club_venue_id) where cv.team_id=any(:ids) and cv.status='CURRENT' and s.status='CURRENT' and ((s.classification='SUPPORTER_SPOT' and s.business_status='OPEN') or (s.classification in ('SUPPORTER_AREA','CLUB_MATCHDAY_VENUE') and s.business_status in ('OPEN','NOT_APPLICABLE')))"""),{"ids":tids}).scalar_one()
    italy_know=c.execute(text("""select count(*) from know_facts k where publication_status='PUBLISHED' and (team_id=any(:ids) or club_venue_id in(select club_venue_id from club_venues where team_id=any(:ids)) or venue_id in(select venue_id from club_venues where team_id=any(:ids)))"""),{"ids":tids}).scalar_one()
    clubs_know=c.execute(text("""select count(distinct coalesce(k.team_id,cv.team_id,cv2.team_id)) from know_facts k left join club_venues cv on cv.club_venue_id=k.club_venue_id left join club_venues cv2 on cv2.venue_id=k.venue_id and cv2.status='CURRENT' where k.publication_status='PUBLISHED' and coalesce(k.team_id,cv.team_id,cv2.team_id)=any(:ids)"""),{"ids":tids}).scalar_one()
    return {"structural":sp,"btm":bp,"know":kp,"denominator":len(tids),"current_home":current,"serving_btm_clubs":serving,"italy_know_facts":italy_know,"italy_clubs_with_know":clubs_know}

def run(url, execute=False):
    structural,know=load(); engine=create_engine(url,pool_pre_ping=True)
    with engine.connect() as c:
        tx=c.begin(); c.execute(text("set transaction isolation level serializable" if execute else "set transaction read only")); before=fingerprints(c); pre=audit(c,structural,know)
        if not execute: tx.rollback(); return {"status":"PASS","action":"DRY_RUN","preflight":pre,"fingerprints":before}
        apply_structural(c,pre["structural"]); mid=audit(c,structural,know); require(mid["current_home"]==78,"structural final count")
        btm_ids=apply_btm(c,mid["btm"]); mid2=audit(c,structural,know); require(mid2["serving_btm_clubs"]==35,"BTM final count")
        know_ids=apply_know(c,know,mid2["know"]); final=audit(c,structural,know)
        require(final["italy_know_facts"]==28 and final["italy_clubs_with_know"]==20,f"KNOW final acceptance: facts={final['italy_know_facts']} clubs={final['italy_clubs_with_know']}")
        after=fingerprints(c); changed=[t for t in before if before[t]!=after[t]]; require(set(changed)<=ALLOWED,"unrelated table mutation")
        tx.commit()
    return {"status":"COMMITTED","action":"PUBLISH","preflight":pre,"final":final,"changed_tables":changed,"btm_insert_ids":btm_ids,"know_insert_ids":know_ids,"before_fingerprints":before,"after_fingerprints":after}

def main():
    p=argparse.ArgumentParser(); p.add_argument("--database-url"); p.add_argument("--local-canonical",action="store_true"); p.add_argument("--hosted-env",action="store_true"); p.add_argument("--execute",action="store_true"); p.add_argument("--confirm",action="store_true"); p.add_argument("--allow-hosted",action="store_true"); p.add_argument("--output",type=Path)
    a=p.parse_args(); url=a.database_url
    if a.local_canonical:
        from backend.database import engine as configured_local_engine
        url=configured_local_engine.url.set(database="matchgoer_btm_v2_local_20260907").render_as_string(hide_password=False)
    if a.hosted_env: url=os.environ.get("MATCHGOER_HOSTED_DATABASE_URL")
    require(bool(url),"database URL required")
    remote=(urlparse(url).hostname or "").casefold() not in {"localhost","127.0.0.1","::1"}
    require(not remote or a.allow_hosted,"hosted access requires explicit --allow-hosted"); require(not a.execute or a.confirm,"write confirmation required")
    result=run(url,a.execute); result["checked_at"]=datetime.now(timezone.utc).isoformat()
    if a.output: a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(json.dumps(result,indent=2,default=str)+"\n",encoding="utf8")
    print(json.dumps({k:v for k,v in result.items() if k not in {"before_fingerprints","after_fingerprints","fingerprints"}},indent=2,default=str))
if __name__=="__main__": main()
