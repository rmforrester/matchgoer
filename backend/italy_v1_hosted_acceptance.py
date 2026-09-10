"""Read-only hosted Italy v1 API acceptance."""
import json, os
from datetime import datetime, timezone
from pathlib import Path
import requests
from sqlalchemy import create_engine, text

ROOT=Path(__file__).resolve().parents[1]; pack=json.loads((ROOT/"reports/italy-v1-publication/italy-know-v1-manifest.json").read_text(encoding="utf8"))
teams=[497,499,895,492,494,517,528,509,1687,522,863,879,6378,865,17147,880,527,868,515,9534,17824,26356,507,6379,500]
expected={}
for f in pack["facts"]:
 tid=f["team_id"]
 if tid is None and f["club_venue_id"]:
  tid={446:497,457:509,461:863}[f["club_venue_id"]]
 if tid is None and f["venue_id"]==23111: tid=517
 expected.setdefault(tid,[]).append(f["module"])
expected[499]=["CLUB","SUPPORTERS"]
results=[]
with create_engine(os.environ["MATCHGOER_HOSTED_DATABASE_URL"]).connect() as c:
 c.execute(text("set transaction read only"))
 for tid in teams:
  row=c.execute(text("select fixture_id,venue_id from fixtures where season=2026 and home_team_id=:t order by fixture_date limit 1"),{"t":tid}).mappings().one()
  response=requests.get(f"https://api.beta.matchgoer.com/fixtures/{row['fixture_id']}/know",timeout=30); payload=response.json() if response.ok else {}
  api_keys={"club":"CLUB","supporters":"SUPPORTERS","matchday":"MATCHDAY","dont_miss":"DONT_MISS","good_to_know":"GOOD_TO_KNOW"}
  modules=sorted(module for key,module in api_keys.items() if payload.get(key)); wanted=sorted(expected.get(tid,[]))
  results.append({"team_id":tid,"fixture_id":row["fixture_id"],"venue_id":row["venue_id"],"http":response.status_code,"modules":modules,"expected_modules":wanted,"pass":response.ok and modules==wanted,"before_match":len(payload.get("before_match",[]))})
 c.rollback()
status="PASS" if all(r["pass"] for r in results) else "FAIL"
out={"status":status,"checked_at":datetime.now(timezone.utc).isoformat(),"hosted_writes":0,"results":results}
path=ROOT/"reports/italy-v1-publication/hosted-api-acceptance.json";path.write_text(json.dumps(out,indent=2)+"\n",encoding="utf8");print(json.dumps(out,indent=2))
if status!="PASS": raise SystemExit(1)
