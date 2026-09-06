"""Build and reconcile the approved France KNOW + DECIDE package without writes."""

from __future__ import annotations

import argparse
import csv
import json
import os
import unicodedata
from collections import Counter
from pathlib import Path

from sqlalchemy import bindparam, create_engine, text


REVIEWED_AT = "2026-09-06"
GS_EXPLANATION = "If supporter culture is important to you, this is one of the clubs worth seeing."
APPROVED_FIXTURE_PROVIDER_VENUES = {114: 18861}

# Approved subject, hosted/provider team id, research population, verified official route.
CLUBS = [
    ("Angers SCO", 77, "Ligue 1", "https://billetterie.angers-sco.fr/fr"),
    ("AJ Auxerre", 108, "Ligue 1", "https://billetterie.aja.fr/"),
    ("Stade Brestois 29", 106, "Ligue 1", "https://billetterie.sb29.bzh/"),
    ("Le Havre AC", 111, "Ligue 1", "https://billetterie.hac.football/"),
    ("Le Mans FC", 1298, "Ligue 1", "https://billetterie.lemansfc.fr/fr"),
    ("RC Lens", 116, "Ligue 1", "https://billetterie.rclens.fr/"),
    ("FC Lorient", 97, "Ligue 1", "https://billetterie.fclorient.bzh/fr/"),
    ("LOSC Lille", 79, "Ligue 1", "https://billetterie.losc.fr/"),
    ("Olympique Lyonnais", 80, "Ligue 1", "https://billetterie.ol.fr/fr"),
    ("Olympique de Marseille", 81, "Ligue 1", "https://billetterie.om.fr/"),
    ("AS Monaco", 91, "Ligue 1", "https://billetterie.asmonaco.com/fr/"),
    ("OGC Nice", 84, "Ligue 1", "https://billetterie.ogcnice.com/fr/"),
    ("Paris FC", 114, "Ligue 1", "https://billetterie.parisfc.fr/"),
    ("Paris Saint-Germain", 85, "Ligue 1", "https://billetterie.psg.fr/"),
    ("Stade Rennais FC", 94, "Ligue 1", "https://billetterie.staderennais.com/"),
    ("RC Strasbourg Alsace", 95, "Ligue 1", "https://billetterie.rcstrasbourgalsace.fr/"),
    ("Toulouse FC", 96, "Ligue 1", "https://billetterie.toulousefc.com/"),
    ("ESTAC Troyes", 110, "Ligue 1", "https://ticket.estac.fr/fr"),
    ("FC Annecy", 3012, "Ligue 2", "https://billetterie.fc-annecy.fr/fr"),
    ("US Boulogne Côte d'Opale", 1299, "Ligue 2", "https://usbco.billetterie-club.fr/"),
    ("Clermont Foot", 99, "Ligue 2", "https://billetterie.clermontfoot.com/fr/"),
    ("Dijon FCO", 89, "Ligue 2", "https://www.dfco.fr/billetterie/"),
    ("USL Dunkerque", 1304, "Ligue 2", "https://www.usldunkerque.com/accueil/le-club/billetterie/"),
    ("Grenoble Foot 38", 101, "Ligue 2", "https://billetterie.gf38.fr/"),
    ("En Avant Guingamp", 90, "Ligue 2", "https://billetterie.eaguingamp.com/"),
    ("Stade Lavallois", 433, "Ligue 2", "https://stade-lavallois-billetterie.com/"),
    ("FC Metz", 112, "Ligue 2", "https://www.billetterie-fcmetz.com/fr"),
    ("Montpellier HSC", 82, "Ligue 2", "https://billetterie.mhscfoot.com/"),
    ("AS Nancy Lorraine", 102, "Ligue 2", "https://asnlbillets.net/"),
    ("FC Nantes", 83, "Ligue 2", "https://billetterie.fcnantes.com/"),
    ("Pau FC", 1297, "Ligue 2", "https://www.paufc.fr/billetterie/"),
    ("Red Star FC", 104, "Ligue 2", "https://billetterie.redstar.fr/"),
    ("Stade de Reims", 93, "Ligue 2", "https://billetterie.stade-de-reims.com/fr"),
    ("Rodez AF", 1301, "Ligue 2", "https://billetterie.rodezaveyronfootball.com/fr"),
    ("AS Saint-Étienne", 1063, "Ligue 2", "https://billetterie.asse.fr/fr/"),
    ("FC Sochaux-Montbéliard", 115, "Ligue 2", "https://billetterie.fcsochaux.fr/fr"),
]

# Frozen editorial choices. A None value is an intentional NULL.
BTM = {
    "Angers SCO": ("Raymond-Kopa Fan Zone", "Recurring official pre-match fan zone beside the stadium.", None, "OFFICIAL"),
    "AJ Auxerre": None,
    "Stade Brestois 29": ("Le Penalty", "Supporter bar directly opposite the ground.", "Le Penalty, 35 route de Quimper, 29200 Brest, France", "EDITORIAL_RESEARCH"),
    "Le Havre AC": ("LH Club / west forecourt", "Official recurring pre-match supporter environment at the stadium.", None, "OFFICIAL"),
    "Le Mans FC": ("Stade Marie-Marvingt Fan Zone", "Recurring official pre-match fan zone on the stadium parvis.", None, "OFFICIAL"),
    "RC Lens": ("La Loco", "Long-established Lens supporter meeting point near the station.", "La Loco, 105 Rue Létienne, 62300 Lens, France", "EDITORIAL_RESEARCH"),
    "FC Lorient": ("Moustoir Fan Zone", "Recurring official pre-match supporter environment at the stadium.", None, "OFFICIAL"),
    "LOSC Lille": None,
    "Olympique Lyonnais": None,
    "Olympique de Marseille": None,
    "AS Monaco": None,
    "OGC Nice": ("Allianz Riviera forecourt / Cours 1904", "Official recurring pre-match supporter environment at the stadium.", None, "OFFICIAL"),
    "Paris FC": ("Stade Jean-Bouin parvis", "Recurring pre-match gathering area on the stadium parvis.", "Stade Jean-Bouin, 26 Avenue du Général Sarrail, Paris, France", "OFFICIAL"),
    "Paris Saint-Germain": ("Parc / Stade Jean-Bouin Fan Zone environment", "Official pre-match fan-zone environment beside Parc des Princes when operating; access conditions may vary.", "Stade Jean-Bouin, 26 Avenue du Général Sarrail, Paris, France", "OFFICIAL"),
    "Stade Rennais FC": ("Roazhon Park Fan Zone", "Recurring official pre-match fan zone beside the stadium.", None, "OFFICIAL"),
    "RC Strasbourg Alsace": ("Meinau Fan Zone", "Recurring official pre-match environment at the stadium.", None, "OFFICIAL"),
    "Toulouse FC": ("Stadium supporter / guinguette environment", "Recurring official supporter area on the stadium parvis.", "Stadium de Toulouse, 1 Allée Gabriel Biénès, Toulouse, France", "OFFICIAL"),
    "ESTAC Troyes": ("Stade de l'Aube Fan Zone", "Recurring official pre-match fan zone beside the stadium.", "Stade de l'Aube, 42 Avenue Robert Schumann, Troyes, France", "OFFICIAL"),
    "FC Annecy": ("Parc des Sports parvis", "Recurring pre-match supporter environment on the stadium parvis.", None, "OFFICIAL"),
    "US Boulogne Côte d'Opale": None,
    "Clermont Foot": ("Gabriel-Montpied Fan Zone", "Recurring official pre-match fan zone beside the stadium.", None, "OFFICIAL"),
    "Dijon FCO": None,
    "USL Dunkerque": ("Stade Marcel Tribut Fan Zone", "Recurring official fan zone before home matches.", None, "OFFICIAL"),
    "Grenoble Foot 38": None,
    "En Avant Guingamp": ("Roudourou Fan Zone / stadium forecourt", "Recurring pre-match supporter environment around the stadium.", None, "OFFICIAL"),
    "Stade Lavallois": None,
    "FC Metz": ("Saint-Symphorien Fan Zone", "Recurring official fan zone behind Tribune Ouest.", None, "OFFICIAL"),
    "Montpellier HSC": ("Mosson parvis", "Recurring official pre-match supporter environment on the stadium parvis.", None, "OFFICIAL"),
    "AS Nancy Lorraine": None,
    "FC Nantes": ("La Beaujoire Fan Zone", "Recurring official pre-match fan zone beside the stadium.", None, "OFFICIAL"),
    "Pau FC": None,
    "Red Star FC": ("Stade Bauer environment", "The urban Bauer matchday environment around the ground.", "Stade Bauer, 92 Rue du Docteur Bauer, 93400 Saint-Ouen-sur-Seine, France", "EDITORIAL_RESEARCH"),
    "Stade de Reims": None,
    "Rodez AF": None,
    "AS Saint-Étienne": None,
    "FC Sochaux-Montbéliard": None,
}

GREAT_SUPPORT = {
    "RC Lens": 116, "Olympique de Marseille": 81, "Paris Saint-Germain": 85,
    "AS Saint-Étienne": 1063, "RC Strasbourg Alsace": 95, "SC Bastia": 1305,
    "FC Nantes": 83, "Red Star FC": 104, "FC Sochaux-Montbéliard": 115,
    "Toulouse FC": 96, "En Avant Guingamp": 90, "FC Metz": 112,
}


def normalized(value):
    value = unicodedata.normalize("NFKD", value or "").casefold()
    return "".join(char for char in value if not unicodedata.combining(char))


def load_hosted(connection):
    ids = [row[1] for row in CLUBS] + list(GREAT_SUPPORT.values())
    teams = connection.execute(text("""
        WITH venue_counts AS (
            SELECT home_team_id AS team_id,venue_id,count(*) AS fixture_count
            FROM fixtures WHERE country='France' AND season=2026 AND league_id IN (61,62) AND venue_id IS NOT NULL
            GROUP BY home_team_id,venue_id
        ), ranked AS (
            SELECT *,row_number() OVER (PARTITION BY team_id ORDER BY fixture_count DESC,venue_id) AS rank,
                   count(*) OVER (PARTITION BY team_id) AS variant_count
            FROM venue_counts
        )
        SELECT t.team_id,t.team_name,t.venue_id AS registered_venue_id,
               coalesce(approved_ref.venue_id,home.venue_id,t.venue_id) AS venue_id,
               v.name AS venue_name,v.city,v.country,
               ref.provider,ref.provider_venue_id,cv.club_venue_id,cv.relationship_type,
               cv.status AS relationship_status,coalesce(home.fixture_count,0) AS current_home_fixtures,
               coalesce(home.variant_count,0) AS current_venue_variants
        FROM teams t LEFT JOIN ranked home ON home.team_id=t.team_id AND home.rank=1
        LEFT JOIN (VALUES (114,18861)) approved(team_id,provider_venue_id) ON approved.team_id=t.team_id
        LEFT JOIN venue_provider_refs approved_ref ON approved_ref.provider='api_football'
          AND approved_ref.provider_venue_id=approved.provider_venue_id AND approved_ref.is_primary IS TRUE
        LEFT JOIN venues v ON v.venue_id=coalesce(approved_ref.venue_id,home.venue_id,t.venue_id)
        LEFT JOIN venue_provider_refs ref ON ref.venue_id=v.venue_id AND ref.provider='api_football' AND ref.is_primary IS TRUE
        LEFT JOIN club_venues cv ON cv.team_id=t.team_id AND cv.venue_id=v.venue_id AND cv.status='CURRENT'
        WHERE t.team_id IN :ids ORDER BY t.team_id
    """).bindparams(bindparam("ids", expanding=True)), {"ids": sorted(set(ids))}).mappings().all()
    facts = connection.execute(text("""
        SELECT fact_id,subject_type,team_a_id,team_b_id,venue_id,team_id,attribute_key,label,
               explanation,publication_status FROM decision_facts WHERE publication_status='PUBLISHED'
    """)).mappings().all()
    return {int(row["team_id"]): dict(row) for row in teams}, [dict(row) for row in facts]


def know_inventory(teams):
    rows = []
    for editorial_name, team_id, competition, ticket_url in CLUBS:
        team = teams.get(team_id)
        if not team:
            status, note = "DORMANT / GENUINE_NOT_IN_CURRENT_INVENTORY", "Approved team is absent from usable hosted inventory."
        elif not team["venue_id"] or not team["provider_venue_id"]:
            status, note = "TECHNICAL_PRECONDITION / PROVIDER_REFERENCE", "Current home venue is deterministic but its primary provider venue reference is incomplete."
        elif not team["club_venue_id"]:
            status, note = "TECHNICAL_PRECONDITION / MISSING_CURRENT_HOME", "Prepare deterministic CURRENT/HOME club_venues relationship before publication."
        else:
            status, note = "READY / DETERMINISTIC_ALIAS", "Canonical owner and provider-linked home venue resolved."
        spot = BTM[editorial_name]
        display = description = destination = evidence_classification = None
        if spot:
            display, description, destination, evidence_classification = spot
            destination = destination or f'{display}, {team["venue_name"]}, {team["city"]}, France'
        rows.append({
            "canonical_team_id": team_id if team else None,
            "canonical_team_name": team["team_name"] if team else None,
            "provider_team_id": team_id if team else None,
            "canonical_venue_id": team["venue_id"] if team else None,
            "canonical_venue_name": team["venue_name"] if team else None,
            "provider_venue_id": team["provider_venue_id"] if team else None,
            "club_venue_id": team["club_venue_id"] if team else None,
            "relationship_type": team["relationship_type"] if team else None,
            "relationship_status": team["relationship_status"] if team else None,
            "competition": competition, "country": "France", "editorial_subject": editorial_name,
            "display_name": display, "supporting_line": description, "maps_destination": destination,
            "classification": ("SUPPORTER_SPOT" if editorial_name in {"Stade Brestois 29", "RC Lens"}
                               else "SUPPORTER_AREA" if editorial_name == "Red Star FC"
                               else "CLUB_MATCHDAY_VENUE" if spot else None),
            "audience": "HOME" if spot else None,
            "pre_match_status": "CURRENT" if spot else None,
            "business_status": "NOT_APPLICABLE" if spot else None,
            "pre_match_confidence": "HIGH" if spot else None,
            "display_order": 1 if spot else None,
            "btm_evidence_url": None,
            "btm_evidence_classification": evidence_classification,
            "ticket_url": ticket_url,
            "ticket_description": f"Buy tickets through {editorial_name}'s official ticket route.",
            "ticket_evidence_url": ticket_url,
            "ticket_section": "tickets_entry", "ticket_topic": "Tickets",
            "ticket_source_type": "official", "ticket_status": "current", "ticket_confidence": "high",
            "entry_description": None, "entry_evidence_url": None,
            "entry_section": None, "entry_topic": None, "entry_source_type": None,
            "publication_status": status,
            "intentional_null": spot is None,
            "exception_review_note": note + (f' Current fixtures contain {team["current_venue_variants"]} venue variants; the dominant current home has {team["current_home_fixtures"]} fixtures.' if team and team["current_venue_variants"] > 1 else ""),
        })
    return rows


def fact_identity(row):
    if row["subject_type"] == "TEAM_PAIR":
        return ("TEAM_PAIR", row["team_a_id"], row["team_b_id"], row["attribute_key"])
    if row["subject_type"] == "TEAM":
        return ("TEAM", row["team_id"], row["attribute_key"])
    return ("VENUE", row["venue_id"], row["attribute_key"])


def decide_inventory(source_path, published):
    published_keys = {fact_identity(row) for row in published}
    with source_path.open(encoding="utf-8-sig", newline="") as handle:
        existing = [row for row in csv.DictReader(handle) if row["country"] == "France"]
    rows = []
    reviewed_venue_aliases = {"Stade Bonal": 23033, "Stade Vélodrome": 23283}
    for source in existing:
        ids = [int(value) for value in source["matchgoer_subject_id(s)"].split(";") if value]
        if source["subject"] in reviewed_venue_aliases:
            ids = [reviewed_venue_aliases[source["subject"]]]
        scope, category = source["scope"], source["category"]
        key = (("TEAM_PAIR", *ids, category) if scope == "TEAM_PAIR" and len(ids) == 2
               else (scope, ids[0], category) if len(ids) == 1 else None)
        dormant = source["reconciliation_status"] == "NOT_IN_CURRENT_INVENTORY" and source["subject"] not in reviewed_venue_aliases
        rows.append({"editorial_subject": source["subject"], "category": category,
                     "canonical_subject_ids": ids, "provider_identity": ids,
                     "resolution_type": "GENUINE_NOT_IN_CURRENT_INVENTORY" if dormant else "DETERMINISTIC_ALIAS",
                     "current_status": "DORMANT" if dormant else "CURRENT",
                     "proposed_action": "DORMANT_NO_WRITE" if dormant else "ALREADY_PRESENT" if key in published_keys else "INSERT",
                     "evidence_provenance_status": "APPROVED_CATALOGUE_PROVENANCE_RETAINED",
                     "exception_note": ("Approved venue alias resolved to current canonical venue." if source["subject"] in reviewed_venue_aliases else source["reconciliation_note"])})
    for subject, team_id in GREAT_SUPPORT.items():
        key = ("TEAM", team_id, "EXCEPTIONAL_SUPPORT")
        rows.append({"editorial_subject": subject, "category": "EXCEPTIONAL_SUPPORT",
                     "canonical_subject_ids": [team_id], "provider_identity": [team_id],
                     "resolution_type": "DETERMINISTIC_ALIAS", "current_status": "CURRENT",
                     "proposed_action": "ALREADY_PRESENT" if key in published_keys else "INSERT",
                     "evidence_provenance_status": "APPROVED_EDITORIAL_DECISION; INDEPENDENT_PROVENANCE_TO_RETAIN",
                     "exception_note": GS_EXPLANATION})
    return rows


def validate(know, decide):
    assert len(know) == 36
    assert Counter(row["competition"] for row in know) == {"Ligue 1": 18, "Ligue 2": 18}
    assert sum(not row["intentional_null"] for row in know) == 21
    assert sum(row["intentional_null"] for row in know) == 15
    assert all(row["maps_destination"] for row in know if not row["intentional_null"])
    assert all(row["display_name"] is None and row["maps_destination"] is None for row in know if row["intentional_null"])
    assert all(row["ticket_url"].startswith("https://") for row in know)
    assert all(row["entry_description"] is None for row in know)
    assert len(decide) == 59
    assert sum(row["category"] == "EXCEPTIONAL_SUPPORT" for row in decide) == 12
    assert not any(row["category"] == "EXCEPTIONAL_SUPPORT" and row["current_status"] != "CURRENT" for row in decide)


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.environ.get("MATCHGOER_HOSTED_DATABASE_URL"))
    parser.add_argument("--decide-source", type=Path, default=Path("reports/decide/decide-five-country-reconciliation-20260903.csv"))
    parser.add_argument("--output-dir", type=Path, default=Path("reports/france"))
    parser.add_argument("--allow-remote-audit", action="store_true")
    args = parser.parse_args()
    if not args.database_url or not args.allow_remote_audit:
        raise RuntimeError("read-only hosted dry run requires database URL and --allow-remote-audit")
    engine = create_engine(args.database_url, pool_pre_ping=True)
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(text("SET TRANSACTION READ ONLY"))
            teams, published = load_hosted(connection)
            know = know_inventory(teams)
            decide = decide_inventory(args.decide_source, published)
        finally:
            transaction.rollback()
    validate(know, decide)
    write_csv(args.output_dir / "france-know-publication-inventory-20260906.csv", know)
    write_csv(args.output_dir / "france-decide-reconciliation-20260906.csv", decide)
    remediation = [{"team_id": row["canonical_team_id"], "venue_id": row["canonical_venue_id"],
                    "relationship_type": "HOME", "status": "CURRENT", "valid_from": None,
                    "valid_until": None, "precondition_note": row["exception_review_note"]} for row in know
                   if row["canonical_team_id"] and row["canonical_venue_id"]]
    write_csv(args.output_dir / "france-club-venue-remediation-dry-run-20260906.csv", remediation)
    summary = {
        "action": "dry-run", "hosted_writes": 0, "migrations": 0,
        "know": {"total": len(know), "btm_populated": 21, "intentional_null": 15,
                 "status": dict(Counter(row["publication_status"] for row in know))},
        "decide": {"total": len(decide), "existing_approved": 47, "great_support": 12,
                   "status": dict(Counter(row["current_status"] for row in decide)),
                   "actions": dict(Counter(row["proposed_action"] for row in decide))},
        "entry_candidates": 0, "entry_omissions": 36,
        "club_venue_remediation": {"proposed_relationships": len(remediation), "hosted_writes": 0},
        "reviewed_at": REVIEWED_AT,
    }
    (args.output_dir / "france-know-decide-dry-run-20260906.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
