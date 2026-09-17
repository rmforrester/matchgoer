"""Bounded USA venue remediation. Dry-run by default; explicit flags required to write."""
from __future__ import annotations

import argparse, csv, hashlib, json, os, re
from collections import Counter
from pathlib import Path
from sqlalchemy import create_engine, text

EXPECTED_SHA="5926F38D9B34B9D475A5D4A3202DE1D82A6777C827D08D309CCA7A767669EFFE"

def norm(v): return re.sub(r"[^a-z0-9]+"," ",(v or "").casefold()).strip()
def ids(row): return [int(x.strip()) for x in row["fixture_ids"].split("|")]

def main():
 p=argparse.ArgumentParser(); p.add_argument("--database-url",default=os.environ.get("MATCHGOER_HOSTED_DATABASE_URL")); p.add_argument("--approval-csv",required=True); p.add_argument("--manifest",required=True); p.add_argument("--receipt",required=True); p.add_argument("--write",action="store_true"); p.add_argument("--confirm-write",action="store_true"); a=p.parse_args()
 if not a.database_url: raise SystemExit("database URL required")
 if a.write != a.confirm_write: raise SystemExit("--write and --confirm-write are required together")
 ap=Path(a.approval_csv); actual=hashlib.sha256(ap.read_bytes()).hexdigest().upper()
 if actual!=EXPECTED_SHA: raise SystemExit(f"approval hash mismatch: {actual}")
 rows=list(csv.DictReader(ap.open(encoding="utf-8-sig"))); manifest=json.loads(Path(a.manifest).read_text(encoding="utf-8-sig"))
 if len(rows)!=45 or len(manifest["overrides"])!=233: raise SystemExit("frozen scope mismatch")
 by_fixture={fid:r for r in rows for fid in ids(r)}
 engine=create_engine(a.database_url,connect_args={"connect_timeout":10})
 receipt={"mode":"WRITE" if a.write else "DRY_RUN","approval_sha256":actual,"counts":{},"unexpected":[]}
 with engine.connect() as c:
  tx=c.begin()
  if not a.write: c.execute(text("SET TRANSACTION READ ONLY"))
  fixtures={r.fixture_id:dict(r._mapping) for r in c.execute(text("select fixture_id,venue_id from fixtures where fixture_id=any(:x)"),{"x":list(by_fixture)})}
  if len(fixtures)!=321: receipt["unexpected"].append(f"fixture rows {len(fixtures)} != 321")
  refs=set()
  for r in rows:
   provider,pid=r["linked_provider_ref"].split(":"); refs.add((provider,int(pid),int(r["linked_canonical_venue_id"])))
  found=set(tuple(x) for x in c.execute(text("select provider,provider_venue_id,venue_id from venue_provider_refs where (provider,provider_venue_id) in (select * from unnest(:p,:i))"),{"p":[x[0] for x in refs],"i":[x[1] for x in refs]}))
  missing=refs-found
  if missing: receipt["unexpected"].append(f"missing/changed provider refs: {sorted(missing)}")
  correction_rows=[r for r in rows if r["approval_state"]=="READY_FOR_BOUNDED_DRY_RUN" and r["fixture_treatment"]=="REVIEWED_FIXTURE_OVERRIDE"]
  new_targets={(r["target_name"],r["target_city"],r["target_country"]) for r in correction_rows if r["target_venue_exists"]=="NO"}
  existing={}
  for name,city,country in new_targets:
   matches=c.execute(text("select venue_id from venues where lower(name)=lower(:n) and lower(city)=lower(:c) and country=:co"),{"n":name,"c":city,"co":country}).scalars().all()
   if len(matches)>1: receipt["unexpected"].append(f"duplicate canonical target {name}/{city}")
   if matches: existing[(name,city,country)]=matches[0]
  target_ids=dict(existing)
  pending_corrections=[]
  for r in correction_rows:
   target=int(r["target_venue_id"]) if r["target_venue_exists"]=="YES" else target_ids.get((r["target_name"],r["target_city"],r["target_country"]))
   expected=int(r["linked_canonical_venue_id"])
   for fid in ids(r):
    cur=fixtures.get(fid,{}).get("venue_id")
    if cur==expected: pending_corrections.append((fid,expected,target,r))
    elif target is not None and cur==target: pass
    else: receipt["unexpected"].append(f"fixture {fid} venue drift {cur}")
  fail_closed=set(manifest["fail_closed_fixture_ids"])
  pending_fail_closed=[]
  for fid in fail_closed:
   cur=fixtures.get(fid,{}).get("venue_id"); expected=int(by_fixture[fid]["linked_canonical_venue_id"])
   if cur==expected: pending_fail_closed.append((fid,expected))
   elif cur is not None: receipt["unexpected"].append(f"fixture {fid} fail-closed drift {cur}")
  managed_correction_ids={fid for r in correction_rows for fid in ids(r)}
  for fid,row in by_fixture.items():
   if fid in managed_correction_ids or fid in fail_closed: continue
   cur=fixtures.get(fid,{}).get("venue_id")
   if int(cur) != int(row["linked_canonical_venue_id"]): receipt["unexpected"].append(f"fixture {fid} unchanged-row drift {cur}")
  missing_aliases=[]
  for alias in manifest["aliases"]:
   if not c.execute(text("select 1 from venue_names where venue_id=:v and normalized_name=:n"),{"v":alias["venue_id"],"n":norm(alias["name"])}).first(): missing_aliases.append(alias)
  current_map=c.execute(text("""
    select count(*) from fixtures f join venues v on v.venue_id=f.venue_id
    where f.fixture_id=any(:x) and v.latitude is not null and v.longitude is not null
  """),{"x":list(by_fixture)}).scalar_one()
  if receipt["unexpected"]: tx.rollback(); Path(a.receipt).write_text(json.dumps(receipt,indent=2)+"\n"); raise SystemExit("preflight failed: "+"; ".join(receipt["unexpected"]))
  if a.write:
   if len(pending_corrections)!=158 or len(pending_fail_closed)!=5 or len(new_targets-set(existing))!=29 or len(missing_aliases)!=6:
    tx.rollback(); raise SystemExit("write scope no longer matches approved mutation set")
   actual={"venues":0,"aliases":0,"fixtures":0,"fail_closed":0}
   for key in sorted(new_targets-set(existing)):
    name,city,country=key
    vid=c.execute(text("insert into venues(name,city,country,latitude,longitude,provider_venue_id) values(:n,:c,:co,null,null,null) returning venue_id"),{"n":name,"c":city,"co":country}).scalar_one(); target_ids[key]=vid; actual["venues"]+=1
    c.execute(text("insert into venue_names(venue_id,name,normalized_name,name_type,source) values(:v,:n,:nn,'current','usa_venue_reconciliation_v1')"),{"v":vid,"n":name,"nn":norm(name)})
   for alias in missing_aliases:
    c.execute(text("insert into venue_names(venue_id,name,normalized_name,name_type,source) values(:v,:n,:nn,'provider',:s)"),{"v":alias["venue_id"],"n":alias["name"],"nn":norm(alias["name"]),"s":alias["source"]}); actual["aliases"]+=1
   for fid,expected,target,r in pending_corrections:
    if target is None: target=target_ids[(r["target_name"],r["target_city"],r["target_country"])]
    actual["fixtures"]+=c.execute(text("update fixtures set venue_id=:t where fixture_id=:f and venue_id=:e"),{"t":target,"f":fid,"e":expected}).rowcount
   for fid,expected in pending_fail_closed: actual["fail_closed"]+=c.execute(text("update fixtures set venue_id=null where fixture_id=:f and venue_id=:e"),{"f":fid,"e":expected}).rowcount
   if actual!={"venues":29,"aliases":6,"fixtures":158,"fail_closed":5}:
    tx.rollback(); raise SystemExit(f"guarded write count mismatch: {actual}")
   tx.commit()
  else: tx.rollback()
  alias_fixtures=sum(int(r["affected_fixture_count"]) for r in rows if r["classification"]=="SAME_VENUE_ALIAS")
  anomaly_nochange=sum(int(r["affected_fixture_count"]) for r in rows if r["classification"]=="PROVIDER_DATA_ANOMALY" and r["fixture_treatment"].startswith("NO_CHANGE"))
  receipt["counts"]={"approved_fixture_corrections":len(pending_corrections),"fail_closed_fixture_updates":len(pending_fail_closed),"withheld_fixtures":len(manifest["withheld_fixture_ids"]),"new_canonical_venues":len(new_targets-set(existing)),"existing_target_reuses":sum(r["target_venue_exists"]=="YES" for r in correction_rows),"fixture_override_entries":len(manifest["overrides"]),"fixture_specific_classification":sum(int(r["affected_fixture_count"]) for r in rows if r["classification"]=="FIXTURE_SPECIFIC_GROUND"),"alias_inserts":len(missing_aliases),"alias_fixtures_unchanged":alias_fixtures,"provider_anomaly_unchanged":anomaly_nochange,"provider_anomaly_corrected":16,"provider_ref_mutations":0,"coordinate_mutations":0,"deletes":0,"map_eligible_before":current_map,"map_eligible_after_projected":140 if pending_corrections or pending_fail_closed else current_map}
 Path(a.receipt).write_text(json.dumps(receipt,indent=2)+"\n",encoding="utf-8")
 print(json.dumps(receipt,indent=2))

if __name__=="__main__": main()
