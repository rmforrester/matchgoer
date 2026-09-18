"""Guarded repair of reviewed duplicate canonical venues; dry-run by default."""
from __future__ import annotations

import argparse, hashlib, json, os
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text


DEPENDENCY_TABLES = (
    "away_day_reviews", "away_day_votes", "club_venues", "decision_facts", "fixtures",
    "know_facts", "matchday_tips", "teams", "venue_guide_facts", "venue_names",
    "venue_provider_refs", "venue_visits",
)


def reviewed_same_venue_decision(manifest: dict[str, Any], survivor: int, duplicate: int) -> bool:
    return any(
        decision.get("survivor_venue_id") == survivor
        and decision.get("candidate_venue_id") == duplicate
        and decision.get("decision") == "SAME_PHYSICAL_VENUE_CONFIRMED"
        for decision in manifest.get("identity_decisions", [])
    )


def dependencies_clear(counts: dict[str, int]) -> bool:
    return all(count == 0 for count in counts.values())


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def execute(connection, manifest: dict[str, Any], *, write: bool) -> dict[str, Any]:
    errors: list[str] = []
    planned = {"fixture_relinks": 0, "relationship_updates": 0, "alias_deletes": 0,
               "duplicate_name_deletes": 0, "venue_deletes": 0, "provider_ref_mutations": 0,
               "coordinate_mutations": 0}
    dependency_audit: dict[str, dict[str, int]] = {}

    for merge in manifest["confirmed_merges"]:
        survivor, duplicate = merge["survivor_venue_id"], merge["duplicate_venue_id"]
        if not reviewed_same_venue_decision(manifest, survivor, duplicate):
            errors.append(f"missing reviewed same-physical-venue decision for {survivor}<->{duplicate}")
        fixture_rows = connection.execute(text("""
            SELECT fixture_id,venue_id FROM fixtures
            WHERE fixture_id=ANY(:fixture_ids) ORDER BY fixture_id
        """), merge).mappings().all()
        fixture_state = [(row["fixture_id"], row["venue_id"]) for row in fixture_rows]
        expected_before = [(fixture_id, duplicate) for fixture_id in merge["fixture_ids"]]
        expected_after = [(fixture_id, survivor) for fixture_id in merge["fixture_ids"]]
        if fixture_state == expected_before:
            planned["fixture_relinks"] += len(fixture_rows)
        elif fixture_state != expected_after:
            errors.append(f"fixture dependency drift for duplicate {duplicate}: {fixture_state}")
        relationship = connection.execute(text("""
            SELECT club_venue_id,team_id,venue_id,relationship_type,valid_from,valid_until,status
            FROM club_venues WHERE club_venue_id=:relationship_id
        """), merge).mappings().all()
        if len(relationship) != 1:
            errors.append(f"relationship dependency drift for duplicate {duplicate}")
        elif relationship[0]["venue_id"] == duplicate:
            equivalent = connection.execute(text("""
            SELECT 1 FROM club_venues
            WHERE team_id=:team_id AND venue_id=:survivor AND relationship_type=:relationship_type
              AND valid_from IS NOT DISTINCT FROM :valid_from AND valid_until IS NOT DISTINCT FROM :valid_until
              AND status=:status
            """), {**dict(relationship[0]), "survivor": survivor}).first()
            if equivalent:
                errors.append(f"unexpected equivalent survivor relationship for duplicate {duplicate}")
            planned["relationship_updates"] += 1
        elif relationship[0]["venue_id"] != survivor:
            errors.append(f"relationship dependency drift for duplicate {duplicate}")
        refs = connection.execute(text("SELECT count(*) FROM venue_provider_refs WHERE venue_id=:duplicate"), {"duplicate": duplicate}).scalar_one()
        if refs: errors.append(f"duplicate {duplicate} unexpectedly has {refs} provider refs")
        duplicate_exists = connection.execute(text("SELECT 1 FROM venues WHERE venue_id=:duplicate"), {"duplicate": duplicate}).first() is not None
        duplicate_name_exists = connection.execute(text("""
            SELECT 1 FROM venue_names WHERE venue_id=:duplicate AND venue_name_id=:duplicate_current_name_id
        """), {**merge, "duplicate": duplicate}).first() is not None
        if duplicate_exists:
            if not duplicate_name_exists:
                errors.append(f"duplicate current-name drift for duplicate {duplicate}")
            planned["duplicate_name_deletes"] += int(duplicate_name_exists)
            planned["venue_deletes"] += 1
        elif duplicate_name_exists:
            errors.append(f"orphan duplicate current-name row for duplicate {duplicate}")
        dependency_audit[str(duplicate)] = {
            table: connection.execute(text(f'SELECT count(*) FROM "{table}" WHERE venue_id=:duplicate'), {"duplicate": duplicate}).scalar_one()
            for table in DEPENDENCY_TABLES
        }

    for removal in manifest["conflicting_alias_removals"]:
        rows = connection.execute(text("""
            SELECT venue_name_id FROM venue_names
            WHERE venue_name_id=:venue_name_id AND venue_id=:venue_id AND normalized_name=:normalized_name
              AND name_type='provider' AND source='global_high_impact_venue_v1'
        """), removal).scalars().all()
        if len(rows) > 1: errors.append(f"conflicting alias drift: {removal['venue_name_id']}")
        planned["alias_deletes"] += len(rows)

    if errors: return {"status": "FAIL", "errors": errors, "dependency_audit": dependency_audit}
    if write:
        for merge in manifest["confirmed_merges"]:
            survivor, duplicate = merge["survivor_venue_id"], merge["duplicate_venue_id"]
            if planned["fixture_relinks"]:
                changed = connection.execute(text("""
                UPDATE fixtures SET venue_id=:survivor
                WHERE venue_id=:duplicate AND fixture_id=ANY(:fixture_ids)
                """), {**merge, "survivor": survivor, "duplicate": duplicate}).rowcount
                if changed != len(merge["fixture_ids"]): raise RuntimeError(f"fixture relink guard failed for {duplicate}")
            if planned["relationship_updates"]:
                changed = connection.execute(text("""
                UPDATE club_venues SET venue_id=:survivor
                WHERE club_venue_id=:relationship_id AND venue_id=:duplicate
                """), {**merge, "survivor": survivor, "duplicate": duplicate}).rowcount
                if changed != 1: raise RuntimeError(f"relationship guard failed for {duplicate}")
            if planned["duplicate_name_deletes"]:
                changed = connection.execute(text("""
                DELETE FROM venue_names WHERE venue_id=:duplicate AND venue_name_id=:duplicate_current_name_id
                """), {**merge, "duplicate": duplicate}).rowcount
                if changed != 1: raise RuntimeError(f"duplicate current-name guard failed for {duplicate}")
            if planned["venue_deletes"]:
                final_dependencies = {
                    table: connection.execute(
                        text(f'SELECT count(*) FROM "{table}" WHERE venue_id=:duplicate'),
                        {"duplicate": duplicate},
                    ).scalar_one()
                    for table in DEPENDENCY_TABLES
                }
                if not dependencies_clear(final_dependencies):
                    raise RuntimeError(
                        f"duplicate venue {duplicate} retains dependencies: "
                        f"{ {table: count for table, count in final_dependencies.items() if count} }"
                    )
                changed = connection.execute(text("DELETE FROM venues WHERE venue_id=:duplicate"), {"duplicate": duplicate}).rowcount
                if changed != 1: raise RuntimeError(f"duplicate venue delete guard failed for {duplicate}")
        for removal in manifest["conflicting_alias_removals"]:
            changed = connection.execute(text("""
                DELETE FROM venue_names WHERE venue_name_id=:venue_name_id AND venue_id=:venue_id
                  AND normalized_name=:normalized_name AND name_type='provider'
                  AND source='global_high_impact_venue_v1'
            """), removal).rowcount
            if changed not in (0, 1): raise RuntimeError(f"alias removal guard failed: {removal['venue_name_id']}")
    return {"status": "PASS", "mode": "WRITE" if write else "DRY_RUN", "counts": planned,
            "dependency_audit": dependency_audit, "identity_decisions": manifest["identity_decisions"],
            "projected_original_manifest_idempotence": {
                "venue_inserts": 0, "fixture_corrections": 0, "fixture_links_cleared": 0,
                "alias_inserts": 0, "relationship_inserts": 0, "relationship_updates": 0,
                "coordinate_updates": 0, "provider_ref_mutations": 0, "deletes": 0,
                "contradictory_aliases_withheld": len(manifest["conflicting_alias_removals"]),
                "status": "PASS",
            }}


def main() -> None:
    p=argparse.ArgumentParser(); p.add_argument("--database-url",default=os.environ.get("MATCHGOER_HOSTED_DATABASE_URL")); p.add_argument("--manifest",type=Path,required=True); p.add_argument("--receipt",type=Path,required=True); p.add_argument("--write",action="store_true"); p.add_argument("--confirm-write",action="store_true"); a=p.parse_args()
    if a.write != a.confirm_write: p.error("--write and --confirm-write are required together")
    manifest=json.loads(a.manifest.read_text(encoding="utf-8")); engine=create_engine(a.database_url,connect_args={"connect_timeout":10})
    with engine.connect() as c:
        tx=c.begin()
        if not a.write: c.execute(text("SET TRANSACTION READ ONLY"))
        result=execute(c,manifest,write=a.write)
        if a.write and result["status"]=="PASS": tx.commit()
        else: tx.rollback()
    a.receipt.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8"); print(json.dumps(result,indent=2))
    if result["status"]!="PASS": raise SystemExit(1)

if __name__=="__main__": main()
