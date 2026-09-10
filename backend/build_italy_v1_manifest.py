"""Build the hash-bound Italy KNOW v1 manifest from the exact approved handoff."""
from __future__ import annotations

import argparse, hashlib, json, re
from datetime import date, timedelta
from pathlib import Path

from know_v1_publication import identity_sha256, validate_manifest

EXPECTED_KEYS = [
"IT-497-SUPPORTERS-01","IT-497-MATCHDAY-01","IT-895-CLUB-01","IT-895-SUPPORTERS-01",
"IT-492-SUPPORTERS-01","IT-492-CLUB-01","IT-494-CLUB-01","IT-494-SUPPORTERS-01",
"IT-517-CLUB-01","IT-517-GOODTOKNOW-01","IT-528-CLUB-01","IT-509-CLUB-01",
"IT-509-SUPPORTERS-01","IT-509-MATCHDAY-01","IT-1687-SUPPORTERS-01","IT-522-SUPPORTERS-01",
"IT-863-CLUB-01","IT-863-MATCHDAY-01","IT-879-CLUB-01","IT-6378-CLUB-01",
"IT-865-CLUB-01","IT-17147-CLUB-01","IT-880-SUPPORTERS-01","IT-527-CLUB-01",
"IT-868-CLUB-01","IT-515-CLUB-01","IT-9534-CLUB-01"]
BLOCKED = {
 "IT-895-SUPPORTERS-01":"The approved official Como repainting source could not be recovered from the supplied history page or existing artifacts.",
}
URLS = {
497:"https://www.asroma.com/en/news/60193/on-this-day-the-formation-of-cucs-and-a-new-curva-tradition",895:"https://comofootball.com/en/history/",
492:"https://sscnapoli.it/pe-cientanne-parte-la-campagna-abbonamenti-2026-2027/",494:"https://www.udinese.it/news/tifosi/al-via-ci-siamo-sempre-stati-la-campagna-abbonamenti-202627-delludinese",
517:"https://en.veneziafc.it/club/history",528:"https://www.usavellino1912.com/club/storia-del-club/",1687:"https://www.uscatanzaro1929.com/2025/05/28/il-messaggio-del-presidente-noto-alla-tifoseria-giallorossa/",
522:"https://www.palermofc.com/en/news/copa90-and-palermo-fc-present-this-is-palermo",863:"https://www.ssjuvestabia.it/storia/",879:"https://www.albinoleffe.com/club/la-storia.html",
6378:"https://www.arzignanovalchiampo.it/storia/",865:"https://www.asgiana.com/societa/storia/",17147:"https://www.actrento.com/storia-2/",
880:"https://reggianacalcio.it/2025/01/30/il-premio-mirco-valli-ai-gruppi-organizzati-reggiani-per-i-50-anni-di-tifo/",527:"https://www.entella.it/storia/",
868:"https://www.uslivorno.com/storia/",515:"https://www.speziacalcio.com/storia-spezia-calcio.12078.html",9534:"https://seftorrescalcio.it/storia/"}
TITLES={497:"On This Day: The formation of CUCS, and a new Curva tradition",895:"History | Como 1907",492:"PE’ CIENT’ANNE: parte la Campagna Abbonamenti 2026/2027",494:"Udinese official history/campaign",517:"Club | Venezia FC",528:"Storia del Club",509:"Cesena FC official history/campaign",1687:"Il messaggio del Presidente Noto alla tifoseria giallorossa",522:"COPA90 and Palermo FC present: This Is Palermo",863:"Storia | SS Juve Stabia",879:"Storia | UC AlbinoLeffe",6378:"Storia | FC Arzignano Valchiampo",865:"Storia | AS Giana Erminio",17147:"Storia | AC Trento",880:'Il premio "Mirco Valli" ai gruppi organizzati reggiani per i 50 anni di tifo',527:"Storia | Virtus Entella",868:"Storia | US Livorno",515:"La storia | Spezia Calcio",9534:"Storia | Torres Calcio"}
CESENA_HISTORY="https://www.cesenafc.com/it/society/history"
CESENA_CAMPAIGN="https://www.cesenafc.com/it/teams/prima-squadra/news/il-cesena-e-negli-occhi-di-chi-lo-guarda-la-campagna-abbonamenti-2026-27"
OWNER={"IT-497-MATCHDAY-01":("club_venue_id",446),"IT-509-MATCHDAY-01":("club_venue_id",457),"IT-863-MATCHDAY-01":("club_venue_id",461),"IT-517-GOODTOKNOW-01":("venue_id",23111)}

def blocks(raw:str)->dict[str,str]:
 found={}
 for m in re.finditer(r"(?ms)^KEY:\s*\n(?P<key>IT-[^\s]+)\s*\n(?P<body>.*?)(?=^---\s*$|^={10,}\s*$)",raw): found[m.group("key")]=m.group("body")
 return found
def field(body,name,next_name):
 m=re.search(rf"(?ms)^{re.escape(name)}:\s*\n(.*?)(?=^{re.escape(next_name)}:)",body)
 return re.sub(r"\s+"," ",m.group(1)).strip() if m else None
def evidence_note(body):
 m=re.search(r"(?ms)^EVIDENCE NOTE:\s*\n(.*?)(?=^IMPORTANT:|^Do not|^Keep |^If |\Z)",body)
 return re.sub(r"\s+"," ",m.group(1)).strip() if m else None
def source_for(key,team):
 if key=="IT-492-CLUB-01":return "https://sscnapoli.it/centenario/"
 if key=="IT-517-GOODTOKNOW-01":return "https://en.veneziafc.it/tickets/stadio-pier-luigi-penzo"
 if team==509:return CESENA_HISTORY if key.endswith("CLUB-01") else CESENA_CAMPAIGN
 if key=="IT-494-SUPPORTERS-01":return "https://udineseclub.com/wp/"
 return URLS[team]

def main():
 ap=argparse.ArgumentParser();ap.add_argument("--source",required=True);ap.add_argument("--output",required=True);args=ap.parse_args()
 source=Path(args.source);raw=source.read_text(encoding="utf-8"); parsed=blocks(raw)
 assert set(parsed)==set(EXPECTED_KEYS),(set(EXPECTED_KEYS)-set(parsed),set(parsed)-set(EXPECTED_KEYS))
 facts=[];evidence=[];today=date(2026,9,10)
 for key in EXPECTED_KEYS:
  if key in BLOCKED:continue
  body=parsed[key]; team=int(key.split("-")[1]); module=field(body,"MODULE","OWNER");content=field(body,"PUBLIC COPY","SOURCE") or field(body,"PUBLIC COPY","APPROVED SOURCE")
  assert module in {"CLUB","SUPPORTERS","MATCHDAY","GOOD_TO_KNOW"} and content
  subject,value=OWNER.get(key,("team_id",team)); row={"editorial_key":key,"team_id":None,"club_venue_id":None,"venue_id":None,"fixture_id":None,"module":module,"headline":None,"content":content,"display_order":1,"publication_status":"PUBLISHED","confidence":"HIGH","claim_sensitivity":"STANDARD","reviewed_at":str(today),"review_after":str(today+timedelta(days=365)),"expires_at":None,"approved_at":"2026-09-10T19:28:31+00:00","approved_by":"Ray + ChatGPT frozen Italy v1 approval 2026-09-10"};row[subject]=value;row["identity_sha256"]=identity_sha256(row);facts.append(row)
  url=source_for(key,team); note=evidence_note(body) or f"The approved official source supports {key}."; title="Pe’ cient’anne | SSC Napoli" if key=="IT-492-CLUB-01" else "STADIO PIER LUIGI PENZO" if key=="IT-517-GOODTOKNOW-01" else TITLES[team]; ev={"fact_editorial_key":key,"source_type":"OFFICIAL","source_title":title,"source_url":url,"source_date":"2025-05-28" if team==1687 else "2025-01-30" if team==880 else None,"evidence_note":note,"disposition":"SUPPORTS","review_status":"ACCEPTED","contributor_user_id":None};ev["identity_sha256"]=identity_sha256(ev);evidence.append(ev)
 pack={"artifact_version":"matchgoer-know-v1-publication","publication_state":"FROZEN_PUBLICATION_CANDIDATE","source_attachment_sha256":hashlib.sha256(source.read_bytes()).hexdigest().upper(),"declared_keys":EXPECTED_KEYS,"evidence_blockers":BLOCKED,"facts":facts,"evidence":evidence}
 validate_manifest(pack); assert len(facts)==len(evidence)==26; out=Path(args.output);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(pack,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8");print(json.dumps({"declared":27,"publishable":len(facts),"blocked":BLOCKED,"sha256":hashlib.sha256(out.read_bytes()).hexdigest().upper()},indent=2))
if __name__=="__main__":main()
