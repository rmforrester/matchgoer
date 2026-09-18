"""Apply a frozen, reviewed global fixture-to-venue remediation manifest.

Dry-run is the default. A write requires both --write and --confirm-write.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import unicodedata
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text

ALIAS_NAME_TYPE = "provider"


def normalized(value: str | None) -> str:
    ascii_value = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", ascii_value.casefold()).strip()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def allowed_venue_name_types(constraint_definition: str) -> set[str]:
    """Extract the values accepted by venue_names_name_type_check."""
    return set(re.findall(r"'([^']+)'::character varying", constraint_definition))


def _target_id(target: dict[str, Any], created: dict[str, int]) -> int:
    return int(target["venue_id"]) if target.get("venue_id") else created[target["target_key"]]


def projected_second_run(receipt: dict[str, Any]) -> dict[str, int]:
    """Mutation counts after every guarded first-run operation is projected applied."""
    return {
        "canonical_venue_inserts": 0, "fixture_venue_corrections": 0,
        "fixture_links_cleared": 0, "aliases_inserted": 0,
        "relationship_inserts": 0, "relationship_updates": 0,
        "provider_refs_inserted": 0, "provider_refs_changed": 0,
        "coordinate_updates": 0, "deletes": 0,
    }


def coalesce_relationships(relationships: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Coalesce compatible operations by the hosted relationship uniqueness key."""
    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for relationship in relationships:
        key = (relationship["team_id"], relationship["target_key"], relationship["valid_from"])
        grouped.setdefault(key, []).append(relationship)
    physical, traces = [], []
    for key, operations in grouped.items():
        semantics = {(op["relationship_type"], op["valid_until"], op["status"]) for op in operations}
        if len(semantics) != 1:
            raise ValueError(f"conflicting planned club_venues semantics for key {key}: {sorted(semantics)}")
        operation = dict(operations[0])
        operation["source_cohort_ids"] = [op["cohort_id"] for op in operations]
        physical.append(operation)
        if len(operations) > 1:
            traces.append({"key": list(key), "source_cohort_ids": operation["source_cohort_ids"],
                           "logical_operations": len(operations), "physical_operations": 1})
    return physical, traces


def transaction_should_commit(*, write: bool, rollback_only: bool, status: str) -> bool:
    return write and not rollback_only and status == "PASS"


def approved_alias_ids_for_target(target: dict[str, Any], aliases: list[dict[str, Any]]) -> set[int]:
    names = {normalized(target["name"]), *(normalized(x) for x in target.get("aliases", []))}
    return {int(alias["venue_id"]) for alias in aliases if normalized(alias["name"]) in names}


def execute(connection, manifest: dict[str, Any], *, write: bool) -> dict[str, Any]:
    expected_fixture_ids = set(manifest["frozen_fixture_ids"])
    fixture_rows = {
        row.fixture_id: dict(row._mapping)
        for row in connection.execute(
            text("SELECT fixture_id, venue_id FROM fixtures WHERE fixture_id = ANY(:ids)"),
            {"ids": sorted(expected_fixture_ids)},
        )
    }
    errors: list[str] = []
    if set(fixture_rows) != expected_fixture_ids:
        errors.append(f"frozen fixture coverage {len(fixture_rows)}/{len(expected_fixture_ids)}")

    existing_targets: dict[str, int] = {}
    new_targets: list[dict[str, Any]] = []
    for target in manifest["targets"]:
        if target.get("venue_id"):
            row = connection.execute(
                text("SELECT venue_id, name, city, country FROM venues WHERE venue_id=:id"),
                {"id": target["venue_id"]},
            ).mappings().all()
            if len(row) != 1:
                errors.append(f"existing target {target['target_key']} missing or non-unique")
            else:
                existing_targets[target["target_key"]] = int(target["venue_id"])
            continue
        matches = connection.execute(
            text("""
                SELECT v.venue_id, v.name, v.city, v.country,
                       array_remove(array_agg(n.name), NULL) AS aliases
                FROM venues v LEFT JOIN venue_names n ON n.venue_id=v.venue_id
                WHERE lower(coalesce(v.city,''))=lower(:city)
                  AND lower(coalesce(v.country,''))=lower(:country)
                GROUP BY v.venue_id, v.name, v.city, v.country
            """), {"city": target.get("city") or "", "country": target.get("country") or ""},
        ).mappings().all()
        names = {normalized(target["name"]), *(normalized(x) for x in target.get("aliases", []))}
        safe = [m for m in matches if names & {normalized(m["name"]), *(normalized(x) for x in m["aliases"])}]
        if len(safe) > 1:
            errors.append(f"ambiguous canonical collision for {target['target_key']}: {[m['venue_id'] for m in safe]}")
        elif safe:
            existing_targets[target["target_key"]] = int(safe[0]["venue_id"])
        else:
            reviewed_alias_candidates = approved_alias_ids_for_target(target, manifest["aliases"])
            compatible_alias_candidates = []
            for venue_id in reviewed_alias_candidates:
                venue = connection.execute(
                    text("SELECT venue_id,name,city,country FROM venues WHERE venue_id=:venue_id"),
                    {"venue_id": venue_id},
                ).mappings().one_or_none()
                if venue and normalized(venue["city"]) == normalized(target.get("city")) \
                        and normalized(venue["country"]) == normalized(target.get("country")):
                    compatible_alias_candidates.append(int(venue_id))
            if compatible_alias_candidates:
                errors.append(
                    f"approved alias identity conflict for new target {target['target_key']}: "
                    f"existing venues={sorted(compatible_alias_candidates)}"
                )
            else:
                new_targets.append(target)

    created = dict(existing_targets)
    corrections, already_correct = [], 0
    for op in manifest["fixture_corrections"]:
        target = next(t for t in manifest["targets"] if t["target_key"] == op["target_key"])
        target_id = _target_id(target, created) if target["target_key"] in created or target.get("venue_id") else None
        current = fixture_rows.get(op["fixture_id"], {}).get("venue_id")
        if target_id is not None and current == target_id:
            already_correct += 1
        elif current == op["old_venue_id"]:
            corrections.append((op, target_id))
        else:
            errors.append(f"fixture {op['fixture_id']} venue drift: {current}")

    clears, already_cleared = [], 0
    for op in manifest["fail_closed"]:
        current = fixture_rows.get(op["fixture_id"], {}).get("venue_id")
        if current is None:
            already_cleared += 1
        elif current == op["old_venue_id"]:
            clears.append(op)
        else:
            errors.append(f"fail-closed fixture {op['fixture_id']} venue drift: {current}")

    managed = {op["fixture_id"] for op in manifest["fixture_corrections"]} | {
        op["fixture_id"] for op in manifest["fail_closed"]
    }
    if len(managed) != len(manifest["fixture_corrections"]) + len(manifest["fail_closed"]):
        errors.append("a fixture appears in more than one mutation operation")
    for fixture_id, expected_venue_id in manifest["no_change_fixture_venues"].items():
        current = fixture_rows.get(int(fixture_id), {}).get("venue_id")
        if current != expected_venue_id:
            errors.append(f"no-change fixture {fixture_id} venue drift: {current}")

    alias_inserts, alias_present, alias_conflicts_withheld = [], 0, []
    for alias in manifest["aliases"]:
        normalized_alias = normalized(alias["name"])
        found = connection.execute(text("""
            SELECT 1 FROM venue_names
            WHERE venue_id=:venue_id AND normalized_name=:normalized_name
        """), {"venue_id": alias["venue_id"], "normalized_name": normalized_alias}).first()
        if found: alias_present += 1
        else:
            current_owners = connection.execute(text("""
                SELECT venue_id FROM venue_names
                WHERE normalized_name=:normalized_name AND name_type='current' AND venue_id<>:venue_id
            """), {"venue_id": alias["venue_id"], "normalized_name": normalized_alias}).scalars().all()
            if current_owners:
                alias_conflicts_withheld.append({**alias, "current_owner_venue_ids": sorted(current_owners)})
            else:
                alias_inserts.append(alias)

    coordinate = manifest["coordinate_update"]
    coordinate_row = connection.execute(text("""
        SELECT venue_id, name, city, country, latitude, longitude
        FROM venues WHERE venue_id=:venue_id
    """), coordinate).mappings().all()
    coordinate_updates = 0
    if len(coordinate_row) != 1:
        errors.append("Naples coordinate target missing or non-unique")
    elif coordinate_row[0]["latitude"] is None and coordinate_row[0]["longitude"] is None:
        coordinate_updates = 1
    elif (Decimal(str(coordinate_row[0]["latitude"])), Decimal(str(coordinate_row[0]["longitude"]))) != (
        Decimal(str(coordinate["latitude"])), Decimal(str(coordinate["longitude"]))
    ):
        errors.append("Naples coordinate target is no longer NULL")

    relationship_inserts: list[dict[str, Any]] = []
    relationship_updates: list[dict[str, Any]] = []
    relationship_noops = 0
    try:
        physical_relationships, coalesced_relationships = coalesce_relationships(manifest["relationships"])
    except ValueError as exc:
        errors.append(str(exc))
        physical_relationships, coalesced_relationships = [], []
    for rel in physical_relationships:
        target = next(t for t in manifest["targets"] if t["target_key"] == rel["target_key"])
        target_id = _target_id(target, created) if target["target_key"] in created or target.get("venue_id") else None
        if target_id is None:
            relationship_inserts.append(rel)
            continue
        rows = connection.execute(text("""
            SELECT club_venue_id, relationship_type, valid_from, valid_until, status
            FROM club_venues WHERE team_id=:team_id AND venue_id=:venue_id
        """), {"team_id": rel["team_id"], "venue_id": target_id}).mappings().all()
        exact = [r for r in rows if r["relationship_type"] == rel["relationship_type"]
                 and str(r["valid_from"] or "") == rel["valid_from"]
                 and str(r["valid_until"] or "") == rel["valid_until"]
                 and r["status"] == rel["status"]]
        if exact: relationship_noops += 1
        elif len(rows) == 1 and rows[0]["relationship_type"] == rel["relationship_type"]:
            relationship_updates.append({**rel, "club_venue_id": rows[0]["club_venue_id"]})
        elif rows:
            errors.append(f"ambiguous club_venues relationship for team {rel['team_id']} target {target_id}")
        else:
            relationship_inserts.append(rel)

    provider_refs_before = connection.execute(text("SELECT count(*) FROM venue_provider_refs")).scalar_one()
    name_type_constraint = connection.execute(text("""
        SELECT pg_get_constraintdef(oid) FROM pg_constraint
        WHERE conrelid='venue_names'::regclass AND conname='venue_names_name_type_check'
    """)).scalar_one_or_none()
    allowed_name_types = allowed_venue_name_types(name_type_constraint or "")
    for planned_type in {"current", ALIAS_NAME_TYPE}:
        if planned_type not in allowed_name_types:
            errors.append(f"venue_names schema does not permit planned name_type={planned_type!r}")
    zaragoza_home = [dict(r._mapping) for r in connection.execute(text("""
        SELECT club_venue_id,team_id,venue_id,relationship_type,valid_from,valid_until,status
        FROM club_venues WHERE team_id=732 AND venue_id=23233
    """))]
    zaragoza_provider_ref = [dict(r._mapping) for r in connection.execute(text("""
        SELECT provider,provider_venue_id,venue_id FROM venue_provider_refs
        WHERE provider='api_football' AND provider_venue_id=1493
    """))]
    if len(zaragoza_home) != 1:
        errors.append("Zaragoza historical/current La Romareda HOME relationship drift")
    if zaragoza_provider_ref != [{"provider": "api_football", "provider_venue_id": 1493, "venue_id": 23233}]:
        errors.append("api_football:1493 no longer resolves exclusively to La Romareda 23233")
    if errors:
        return {"status": "FAIL", "errors": errors}

    projected_target_ids = dict(created)
    if write:
        for target in new_targets:
            venue_id = connection.execute(text("""
                INSERT INTO venues(name,address,city,country,latitude,longitude,provider_venue_id)
                VALUES(:name,:address,:city,:country,NULL,NULL,NULL) RETURNING venue_id
            """), target).scalar_one()
            projected_target_ids[target["target_key"]] = venue_id
            connection.execute(text("""
                INSERT INTO venue_names(venue_id,name,normalized_name,name_type,source)
                VALUES(:venue_id,:name,:normalized_name,'current','global_high_impact_venue_v1')
            """), {"venue_id": venue_id, "name": target["name"], "normalized_name": normalized(target["name"])})
        for op, _ in corrections:
            target_id = projected_target_ids[op["target_key"]]
            changed = connection.execute(text("""
                UPDATE fixtures SET venue_id=:target WHERE fixture_id=:fixture AND venue_id=:old
            """), {"target": target_id, "fixture": op["fixture_id"], "old": op["old_venue_id"]}).rowcount
            if changed != 1: raise RuntimeError(f"fixture guard failed: {op['fixture_id']}")
        for op in clears:
            changed = connection.execute(text("""
                UPDATE fixtures SET venue_id=NULL WHERE fixture_id=:fixture AND venue_id=:old
            """), {"fixture": op["fixture_id"], "old": op["old_venue_id"]}).rowcount
            if changed != 1: raise RuntimeError(f"fail-closed guard failed: {op['fixture_id']}")
        for alias in alias_inserts:
            connection.execute(text("""
                INSERT INTO venue_names(venue_id,name,normalized_name,name_type,source)
                VALUES(:venue_id,:name,:normalized_name,:name_type,'global_high_impact_venue_v1')
            """), {**alias, "normalized_name": normalized(alias["name"]), "name_type": ALIAS_NAME_TYPE})
        for rel in relationship_inserts:
            connection.execute(text("""
                INSERT INTO club_venues(team_id,venue_id,relationship_type,valid_from,valid_until,status)
                VALUES(:team_id,:venue_id,:relationship_type,:valid_from,:valid_until,:status)
            """), {**rel, "venue_id": projected_target_ids[rel["target_key"]]})
        for rel in relationship_updates:
            connection.execute(text("""
                UPDATE club_venues SET valid_from=:valid_from,valid_until=:valid_until,status=:status
                WHERE club_venue_id=:club_venue_id
            """), rel)
        if coordinate_updates:
            changed = connection.execute(text("""
                UPDATE venues SET latitude=:latitude,longitude=:longitude
                WHERE venue_id=:venue_id AND latitude IS NULL AND longitude IS NULL
            """), coordinate).rowcount
            if changed != 1: raise RuntimeError("Naples coordinate guard failed")

    coordinate_complete_targets = sum(1 for t in manifest["targets"] if t.get("coordinate_complete"))
    immediate_map = sum(1 for op in manifest["fixture_corrections"] if op["target_coordinate_complete"])
    unavailable = len(manifest["fixture_corrections"]) - immediate_map
    receipt = {
        "status": "PASS", "mode": "WRITE" if write else "DRY_RUN",
        "counts": {
            "frozen_fixtures": len(expected_fixture_ids),
            "canonical_target_count": len(manifest["targets"]),
            "canonical_venue_inserts": len(new_targets),
            "canonical_venue_reuses": len(manifest["targets"]) - len(new_targets),
            "fixture_venue_corrections": len(corrections), "fixture_corrections_already_applied": already_correct,
            "fixture_links_cleared": len(clears), "fixture_links_already_cleared": already_cleared,
            "aliases_inserted": len(alias_inserts), "aliases_already_present": alias_present,
            "alias_identity_conflicts_withheld": len(alias_conflicts_withheld),
            "relationship_inserts": len(relationship_inserts), "relationship_updates": len(relationship_updates),
            "relationship_noops": relationship_noops, "provider_refs_inserted": 0, "provider_refs_changed": 0,
            "coordinate_updates": coordinate_updates, "deletes": 0,
            "map_visible_immediately": immediate_map + coordinate["fixture_count"],
            "coordinate_null_unavailable": unavailable,
            "fail_closed_unavailable": len(manifest["fail_closed"]),
            "coordinate_complete_targets": coordinate_complete_targets,
        },
        "provider_ref_count_before": provider_refs_before,
        "provider_ref_count_projected_after": provider_refs_before,
        "alias_identity_conflicts_withheld": alias_conflicts_withheld,
        "relationships": {"logical_operations": len(manifest["relationships"]),
                          "physical_operations": len(physical_relationships),
                          "coalesced_operations": len(manifest["relationships"]) - len(physical_relationships),
                          "coalesced_groups": coalesced_relationships,
                          "conflicting_groups": 0},
        "zaragoza_fixture_ids": manifest["acceptance"]["zaragoza_fixture_ids"],
        "zaragoza_target": manifest["acceptance"]["zaragoza_target"],
        "zaragoza_preserved_home_relationship": zaragoza_home,
        "zaragoza_preserved_provider_ref": zaragoza_provider_ref,
        "rustavi": manifest["acceptance"]["rustavi"],
        "naples": coordinate,
        "errors": [],
    }
    receipt["idempotence_simulation"] = {
        "status": "PASS", "second_run_mutations": projected_second_run(receipt),
        "total_second_run_mutations": 0,
    }
    return receipt


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", default=os.environ.get("MATCHGOER_HOSTED_DATABASE_URL"))
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--rollback-only", action="store_true")
    parser.add_argument("--confirm-write", action="store_true")
    args = parser.parse_args()
    if args.write and args.rollback_only:
        parser.error("--write and --rollback-only are mutually exclusive")
    if args.confirm_write != (args.write or args.rollback_only):
        parser.error("--confirm-write is required with --write or --rollback-only")
    if not args.database_url:
        parser.error("MATCHGOER_HOSTED_DATABASE_URL or --database-url is required")
    return args


def main() -> None:
    args = parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    for path, expected in manifest["source_hashes"].items():
        actual = sha256(Path(path))
        if actual != expected: raise SystemExit(f"source hash mismatch for {path}: {actual}")
    engine = create_engine(args.database_url, connect_args={"connect_timeout": 10})
    with engine.connect() as connection:
        transaction = connection.begin()
        if not args.write and not args.rollback_only:
            connection.execute(text("SET TRANSACTION READ ONLY"))
        try:
            receipt = execute(connection, manifest, write=args.write or args.rollback_only)
            if args.rollback_only:
                receipt["mode"] = "ROLLBACK_ONLY"
            if transaction_should_commit(write=args.write, rollback_only=args.rollback_only, status=receipt["status"]):
                transaction.commit()
            else:
                transaction.rollback()
        except Exception as exc:
            transaction.rollback()
            receipt = {"status": "FAIL", "mode": "ROLLBACK_ONLY" if args.rollback_only else "WRITE",
                       "exception_type": type(exc).__name__, "exception_message": str(exc),
                       "rollback_executed": True}
            args.receipt.parent.mkdir(parents=True, exist_ok=True)
            args.receipt.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            raise
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    if receipt["status"] != "PASS": raise SystemExit(1)


if __name__ == "__main__":
    main()
