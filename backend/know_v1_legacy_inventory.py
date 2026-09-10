"""Read-only deterministic inventory of legacy venue-guide facts for KNOW v1."""

from __future__ import annotations
import argparse, csv, json
from pathlib import Path
from urllib.parse import urlparse
from sqlalchemy import create_engine, text


def classify(row):
    topic = (row["topic"] or "").strip().casefold()
    if row["section"] == "before_match":
        return "IDENTITY_BLOCKER", "Requires editorial comparison with canonical BTM; no automatic duplication."
    if row["section"] == "tickets_entry" or topic in {"buy online", "official_ticket_portal", "general_purchase_process"}:
        return "KEEP_AS_UTILITY", "Ticket utility remains outside KNOW v1."
    return "KEEP_AS_UTILITY", "No deterministic evidence that this practical fact passes the KNOW exception standard."


def build_ledger(database_url, output_stem):
    if (urlparse(database_url).hostname or "").casefold() not in {"localhost", "127.0.0.1", "::1"}:
        raise RuntimeError("legacy KNOW inventory is local-only")
    engine=create_engine(database_url,pool_pre_ping=True)
    with engine.connect() as c:
        tx=c.begin(); c.execute(text("SET TRANSACTION READ ONLY"))
        rows=c.execute(text("""SELECT fact_id,venue_id,club_venue_id,section,topic,status,source_type,source_url
            FROM venue_guide_facts ORDER BY fact_id""")).mappings().all(); tx.rollback()
    ledger=[]
    for row in rows:
        disposition,reason=classify(row); ledger.append({**dict(row),"migration_disposition":disposition,"reason":reason})
    counts={key:sum(x["migration_disposition"]==key for x in ledger) for key in
            ("MIGRATE_TO_KNOW","KEEP_AS_UTILITY","ARCHIVE_AFTER_REVIEW","IDENTITY_BLOCKER")}
    stem=Path(output_stem); stem.parent.mkdir(parents=True,exist_ok=True)
    stem.with_suffix(".json").write_text(json.dumps({"counts":counts,"rows":ledger},indent=2,default=str),encoding="utf-8")
    with stem.with_suffix(".csv").open("w",newline="",encoding="utf-8-sig") as f:
        writer=csv.DictWriter(f,fieldnames=list(ledger[0]) if ledger else ["fact_id","migration_disposition","reason"]); writer.writeheader(); writer.writerows(ledger)
    return counts


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--database-url",required=True)
    parser.add_argument("--output-stem",required=True)
    args=parser.parse_args()
    print(json.dumps(build_ledger(args.database_url,args.output_stem),indent=2))


if __name__ == "__main__": main()
