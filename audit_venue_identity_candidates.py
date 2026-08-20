"""Generate the reviewed, non-mutating venue identity candidate report."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from sqlalchemy import create_engine, text

from ingestion.environment import database_url


CANDIDATES = [
    (22828, 22833, 22833, "Friends Arena", "Strawberry Arena", "high"),
    (12596, 22764, 12596, "St Andrew's Stadium", "St. Andrew's @ Knighthead Park", "high"),
    (19718, 21313, 21313, "Swansway Chester Stadium", "Deva Stadium", "high"),
    (18618, 22758, 18618, "Brisbane Road", "BetWright Stadium", "medium"),
    (2694, 19705, 19705, "Haig Avenue", "The BIG HELP Stadium", "high"),
    (592, 21482, 592, "The County Ground", "The Nigel Eady County Ground", "high"),
    (5548, 21970, 21970, "Select Security Stadium", "DCBL Stadium", "high"),
    (22843, 22850, 22843, "Visma Arena (provider 11916)", "Visma Arena (provider 22781)", "medium"),
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    engine = create_engine(database_url())
    report = {
        "audit_date": date.today().isoformat(),
        "status": "review candidates only; no merges or reassignments performed",
        "method": "The named audit pairs were checked against exact stored metadata and ownership counts. Similar names alone are not evidence of identity.",
        "candidates": [],
    }
    with engine.connect() as connection:
        for left_id, right_id, recommendation, left_label, right_label, confidence in CANDIDATES:
            rows = connection.execute(text("""
                SELECT v.venue_id, v.provider_venue_id, v.name, v.address, v.city,
                       v.latitude, v.longitude,
                       (SELECT count(*) FROM fixtures f WHERE f.venue_id=v.venue_id) fixture_count,
                       (SELECT count(*) FROM away_day_reviews r WHERE r.venue_id=v.venue_id) review_count,
                       (SELECT count(*) FROM matchday_tips t WHERE t.venue_id=v.venue_id) tip_count,
                       COALESCE((SELECT json_agg(json_build_object('team_id', tm.team_id, 'team_name', tm.team_name)
                                                ORDER BY tm.team_name)
                                 FROM teams tm WHERE tm.venue_id=v.venue_id), '[]'::json) teams
                FROM venues v WHERE v.venue_id IN (:left_id, :right_id) ORDER BY v.venue_id
            """), {"left_id": left_id, "right_id": right_id}).mappings().all()
            serialized = []
            for row in rows:
                item = dict(row)
                item["latitude"] = float(item["latitude"]) if item["latitude"] is not None else None
                item["longitude"] = float(item["longitude"]) if item["longitude"] is not None else None
                serialized.append(item)
            report["candidates"].append({
                "pair": [left_label, right_label],
                "records": serialized,
                "evidence_supporting_same_identity": "Exact coordinates and/or exact stored address; naming pattern is consistent with a rename or sponsorship change.",
                "evidence_against_or_uncertain": "Different API-Football provider venue IDs; provider continuity has not been independently established.",
                "recommended_canonical_venue_id_if_approved": recommendation,
                "confidence": confidence,
                "recommended_action": "Manual provider/source review before any reference reassignment; do not fuzzy-merge.",
            })
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
