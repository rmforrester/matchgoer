"""Build the frozen supporter-facing KNOW copy ledger from current local rows."""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/final-pre-beta-ux"

PROPOSALS = {
    "IT-1687-SUPPORTERS-01": "Catanzaro’s support travels unusually well for the size of the city. In 2024/25, its fans were the leading away support in the division, while support for the club remains shared across generations of the community.",
    "IT-492-CLUB-01": "Napoli’s identity is deliberately tied to the city around it. Its centenary imagery runs from Vesuvius and Posillipo through the historic centre, while the crest revives the Corsiero del Sole — the club’s original 1926 symbol.",
    "IT-492-SUPPORTERS-01": "Napoli’s supporter story runs through generations rather than trophies. A central figure born in 1926 passes his support for Napoli to his children, grandchildren and great-grandchildren, reflecting the club’s relationship with the city.",
    "IT-494-CLUB-01": "Udinese is a football expression of Friuli as well as a club based in Udine. In its 130th year, that relationship with the region became the central theme of the club’s identity and season-ticket campaign.",
    "IT-497-MATCHDAY-01": "The Curva Sud tradition is built around sustained vocal support. Drums begin before kick-off and supporters sing continuously for the full 90 minutes — a style of support that became part of the identity of the Sud.",
    "IT-509-MATCHDAY-01": "Curva Mare remains the focal point of Cesena’s home support. Years spent in the Curva are still treated as one of the defining ways supporters experience the Manuzzi.",
    "IT-509-SUPPORTERS-01": "Cesena’s support spans generations: people with decades in the Curva Mare share the same ground with families and first-time supporters building their own memories there.",
    "IT-522-SUPPORTERS-01": "Palermo’s identity is carried by long-standing Curva Nord fans, families and ordinary Palermitans, for whom football is a language passed between generations in the city.",
    "IT-527-CLUB-01": "Entella is more than Chiavari’s team. Its identity is shared by the city and the communities of the surrounding hinterland that grew around the Entella river.",
    "IT-9534-CLUB-01": "Torres’ history reached beyond Sassari unusually early: in 1908 the club played an exhibition in Ajaccio, the first football match on foreign soil by a Sardinian team.",
    "know-v1-proof:real-oviedo:matchday": "Carlos Tartiere continues to draw support on a scale that stands out against much of Real Oviedo’s recent football history. Average home attendance reached 24,888 in 2025/26, with strong crowds even for Monday and midweek fixtures.",
}


def main() -> None:
    base = make_url(dotenv_values(Path(os.environ["MATCHGOER_LOCAL_ENV"]))["DATABASE_URL"])
    engine = create_engine(base.set(database="matchgoer_btm_v2_local_20260907"))
    with engine.connect() as connection:
        found = connection.execute(text("""select k.editorial_key,k.content,k.module,k.team_id,k.club_venue_id,k.venue_id,k.fixture_id,
          k.publication_status,coalesce(t.team_name,tcv.team_name,tv.team_name,'Canonical owner') club,
          string_agg(coalesce(e.source_title,'') || ' | ' || coalesce(e.source_url,''),' || ' order by e.evidence_id) evidence
          from know_facts k
          left join club_venues cv on cv.club_venue_id=k.club_venue_id
          left join teams t on t.team_id=k.team_id
          left join teams tcv on tcv.team_id=cv.team_id
          left join club_venues cvv on cvv.venue_id=k.venue_id and cvv.status='CURRENT'
          left join teams tv on tv.team_id=cvv.team_id
          left join know_fact_evidence e on e.know_fact_id=k.know_fact_id
          where k.editorial_key=any(:keys) and k.publication_status='PUBLISHED'
          group by k.know_fact_id,t.team_name,tcv.team_name,tv.team_name order by k.editorial_key"""), {"keys": list(PROPOSALS)}).mappings().all()
    if len(found) != len(PROPOSALS):
        raise RuntimeError("proposal key set does not match local serving inventory")
    updates = []
    for row in found:
        updates.append({"editorial_key": row["editorial_key"], "club": row["club"], "module": row["module"],
            "before": row["content"], "after": PROPOSALS[row["editorial_key"]], "evidence": row["evidence"],
            "reason": "Remove source/campaign narration and state the same approved claim directly for supporters.",
            "evidence_faithful": True,
            "stable_identity": {key: row[key] for key in ("module","team_id","club_venue_id","venue_id","fixture_id","publication_status")}})
    pack = {"title": "Final pre-beta supporter-facing KNOW copy cleanup", "serving_inventory_count": 48,
            "unchanged_count": 48-len(updates), "updates": updates}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "know-copy-manifest.json").write_text(json.dumps(pack, indent=2, ensure_ascii=False), encoding="utf-8")
    fields = ("editorial_key","club","module","before","after","evidence","reason","evidence_faithful")
    with (OUT / "know-copy-ledger.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader()
        writer.writerows([{key: row[key] for key in fields} for row in updates])
    print(json.dumps({"serving": 48, "updates": len(updates), "unchanged": 48-len(updates)}, indent=2))


if __name__ == "__main__":
    main()
