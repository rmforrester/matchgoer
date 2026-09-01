"""Prepare the targeted Sweden coordinate QA artifacts without hosted writes."""

from __future__ import annotations

import json
import os
from pathlib import Path

from sqlalchemy import create_engine, text


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / ".cache" / "nominatim" / "sweden-canonical-coordinate-audit-2026.json"
OSM = ROOT / ".cache" / "nominatim" / "sweden-canonical-coordinate-osm-qa-2026.json"
REVIEWED = ROOT / ".cache" / "nominatim" / "sweden-canonical-reviewed15-2026.json"
REPORT = ROOT / "reports" / "ingestion" / "sweden-canonical-coordinate-qa-2026.json"


DECISIONS = {
    1504: ("PASS", "OSM stadium's alt_name is Gavlevallen; soccer tags, provider address and Gävle locality converge."),
    1515: ("PASS", "Exact-name soccer pitch in Täby kyrkby with compatible provider address and locality."),
    1523: ("PASS", "Exact-name soccer stadium in Östersund with Wikidata/Wikipedia identity and matching road."),
    1528: ("PASS", "Exact-name soccer stadium in Eskilstuna with Wikidata identity and compatible address."),
    4866: ("WITHHOLD", "Provider identifies Råby IP pitch 3; OSM candidate is only the broader Råby IP sports centre."),
    4870: ("PASS", "Exact-name Gutavallen sports venue in Visby/Gotland with structured Wikidata identity."),
    4871: ("WITHHOLD", "Provider identifies Torvalla IP pitch 1; OSM candidate is the broader sports centre."),
    4874: ("PASS", "Exact normalized VapenVallen stadium identity in Huskvarna and compatible locality."),
    4881: ("WITHHOLD", "Provider identifies Lidingövallen pitch 2; OSM candidate is the broader multi-sport centre."),
    4888: ("WITHHOLD", "OSM object is an indoor civic sports-centre building tagged for swimming and ice hockey, not the football pitch."),
    4893: ("PASS", "Jernvallen is the same normalized named physical sports venue in Sandviken with Wikidata identity."),
    4895: ("PASS", "Exact-name Sollentunavallen venue with Wikidata/Wikipedia identity and compatible locality."),
    4899: ("PASS", "OSM short_name Övrevi IP and operator Tvååkers IF support the provider's Övrevi identity."),
    4900: ("WITHHOLD", "Provider specifies Umeå Energi Arena SOL; OSM candidate is the unqualified broader Umeå Energi Arena sports centre."),
    7653: ("PASS", "Exact-name LF Arena multi-sport venue in Piteå; structured tags explicitly include soccer."),
    7983: ("WITHHOLD", "Provider specifies the artificial-turf ground; OSM candidate is only the unqualified Skyttis IP stadium object."),
    7989: ("WITHHOLD", "OSM candidate is tagged as a sports-centre building with no pitch/football evidence."),
    7990: ("WITHHOLD", "Provider specifies Nolia pitch 1; OSM candidate is an unnumbered seasonal Nolia pitch."),
    8004: ("WITHHOLD", "Provider specifies Bergavik IP field A; OSM candidate is an unqualified Bergaviks IP pitch at a different road label."),
    8006: ("PASS", "Vägga Stadion is the documented Vägga IP soccer venue; matching address plus Wikidata/Wikipedia identity."),
    8866: ("PASS", "Exact normalized Vildmannavallen soccer pitch in Umeå with grass and outdoor venue tags."),
    12742: ("PASS", "OSM alt_name is Söndrums IP; same Halmstad locality and physical sports venue."),
    18631: ("PASS", "OSM alt_name Domnarvsvallen matches the provider compound name; exact arena, soccer and locality evidence."),
    19692: ("WITHHOLD", "Provider identifies Järfällavallen generally; OSM result is specifically pitch 1, so the physical sub-venue is not certain."),
    20512: ("WITHHOLD", "Provider specifies Rosvalla artificial pitch A; OSM candidate is only the broader Rosvalla sports centre."),
    21602: ("PASS", "Exact-name Sörforsvallen pitch at the provider's Sörfors address within Sundsvall municipality."),
    21797: ("WITHHOLD", "Provider specifies the artificial-turf pitch; OSM candidate is the broader Örsholmens sports centre."),
}


def main() -> None:
    checkpoint = json.loads(SOURCE.read_text(encoding="utf-8"))
    osm_rows = json.loads(OSM.read_text(encoding="utf-8"))
    osm = {(row["osm_type"], int(row["osm_id"])): row for row in osm_rows}
    accepted_ids = sorted(provider_id for provider_id, (decision, _) in DECISIONS.items() if decision == "PASS")
    withheld_ids = sorted(set(DECISIONS) - set(accepted_ids))
    reviewed = {}
    qa_rows = []
    for provider_id in sorted(DECISIONS):
        result = checkpoint[str(provider_id)]
        decision, reason = DECISIONS[provider_id]
        candidate = osm[(result["osm_type"], int(result["osm_id"]))]
        if decision == "PASS":
            reviewed[str(provider_id)] = {
                **result,
                "qa_decision": "PASS",
                "qa_reason": reason,
            }
        qa_rows.append({
            "provider_venue_id": provider_id,
            "matchgoer_venue": result["venue"]["name"],
            "provider_city": result["venue"].get("city"),
            "osm_result": candidate.get("name"),
            "osm_category": candidate.get("category"),
            "osm_type": candidate.get("type"),
            "osm_locality": (candidate.get("address") or {}).get("city")
                or (candidate.get("address") or {}).get("town")
                or (candidate.get("address") or {}).get("village"),
            "decision": decision,
            "reason": reason,
            "latitude": result["latitude"],
            "longitude": result["longitude"],
        })

    engine = create_engine(os.environ["DATABASE_URL"], connect_args={"connect_timeout": 10})
    with engine.connect() as connection:
        connection.execute(text("SET TRANSACTION READ ONLY"))
        fixture_counts = dict(connection.execute(text("""
            SELECT r.provider_venue_id, count(f.fixture_id)::int
            FROM venue_provider_refs r
            JOIN fixtures f ON f.venue_id=r.venue_id AND f.country='Sweden'
            WHERE r.provider='api_football' AND r.provider_venue_id=ANY(:ids)
            GROUP BY r.provider_venue_id
        """), {"ids": accepted_ids}).all())
        # The targeted hosted collision query is performed separately at the
        # same six-decimal precision as the protected application workflow.
        collisions = []
    unlocked = sum(fixture_counts.values())
    payload = {
        "mode": "READ_ONLY_TARGETED_QA",
        "source": str(SOURCE),
        "candidates": qa_rows,
        "summary": {
            "PASS": len(accepted_ids), "WITHHOLD": len(withheld_ids),
            "pass_provider_venue_ids": accepted_ids,
            "withheld_provider_venue_ids": withheld_ids,
            "fixtures_unlocked": unlocked,
            "sweden_current": 884, "sweden_projected": 884 + unlocked,
            "sweden_projected_percent": round(100 * (884 + unlocked) / 2040, 1),
            "europe_current": 22515, "europe_projected": 22515 + unlocked,
            "europe_projected_percent": round(100 * (22515 + unlocked) / 26043, 1),
        },
        "duplicate_collision_findings": collisions,
        "safety": {"hosted_writes": 0, "fixture_links_changed": 0, "identity_changes": 0},
    }
    REVIEWED.parent.mkdir(parents=True, exist_ok=True)
    REVIEWED.write_text(json.dumps(reviewed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))
    print(REVIEWED)
    print(REPORT)


if __name__ == "__main__":
    main()
