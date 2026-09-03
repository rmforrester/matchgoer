import csv
import json
import re
import unicodedata
import zipfile
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path
from xml.etree import ElementTree

from sqlalchemy import text


XLSX_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
PAIR_SEPARATOR = " — "
# Already reviewed and published by the DECIDE V1 proof artifact; reconciliation-only alias.
REVIEWED_VENUE_ALIASES = {
    ("England", "The Hawthorns"): 597,
    ("England", "St James' Park"): 562,
    ("Italy", "San Siro"): 23100,
    ("Spain", "Santiago Bernabéu"): 23269,
}
REVIEWED_IDENTITY_NOTES = {
    ("England", "The Hawthorns"): "Human-reviewed identity: West Brom team 60, CURRENT/HOME relationship and current fixtures resolve to venue 597/provider venue 597",
    ("Spain", "Santiago Bernabéu"): "Human-reviewed identity: Real Madrid team 541 and current fixtures resolve to venue 23269/provider venue 1456",
}
REVIEWED_DORMANT_SUBJECTS = {
    ("England", "Victoria Park", "CLASSIC_GROUND", "VENUE"): "Human-reviewed dormant: Hartlepool's Victoria Park is absent; Victory Park is a different ground",
    ("Italy", "Atalanta — Brescia", "SIGNIFICANT_RIVALRY", "TEAM_PAIR"): "Human-reviewed dormant: historical Brescia must not be mapped to Union Brescia",
    ("Italy", "Verona — Brescia", "SIGNIFICANT_RIVALRY", "TEAM_PAIR"): "Human-reviewed dormant: historical Brescia must not be mapped to Union Brescia",
    ("Italy", "Reggina — Messina", "SIGNIFICANT_RIVALRY", "TEAM_PAIR"): "Human-reviewed dormant: Reggina is not Reggiana and the approved pair is absent",
}
REVIEWED_TEAM_ALIASES = {
    ("England", "Brighton & Hove Albion"): 51,
    ("England", "MK Dons"): 1348,
    ("England", "Preston North End"): 59,
    ("England", "West Bromwich Albion"): 60,
    ("England", "Wolverhampton Wanderers"): 39,
    ("France", "Brest"): 106,
    ("France", "QRM"): 431,
    ("Italy", "Verona"): 504,
    ("Spain", "Real Oviedo"): 718,
}
TEAM_ORGANISATION_TOKENS = {
    "1", "ac", "acr", "afc", "as", "cf", "estac", "fc", "lr", "sc", "ssc", "spvgg", "ss", "tsv", "us",
}
TEAM_QUALIFIER_TOKENS = {
    "albion", "argyle", "athletic", "calcio", "city", "club", "county", "hotspur", "rovers", "town", "united",
    "virtus", "wanderers",
}
TEAM_WORD_ALIASES = {"utd": "united", "munchen": "munich"}


def normalize_identity(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).casefold()
    value = "".join(character for character in value if not unicodedata.combining(character))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value).split())


def _team_aliases(value: str) -> set[str]:
    tokens = [TEAM_WORD_ALIASES.get(token, token) for token in normalize_identity(value).split()]
    aliases = {" ".join(tokens)}
    without_organisation = [token for token in tokens if token not in TEAM_ORGANISATION_TOKENS]
    if without_organisation:
        aliases.add(" ".join(without_organisation))
    without_qualifiers = [token for token in without_organisation if token not in TEAM_QUALIFIER_TOKENS]
    if without_qualifiers:
        aliases.add(" ".join(without_qualifiers))
    return {alias for alias in aliases if len(alias) >= 3}


def _deterministic_team_candidates(subject: str, country: str, rows) -> dict[int, str]:
    wanted = _team_aliases(subject)
    matches = {}
    for row in rows:
        if row["country"] != country:
            continue
        if wanted & _team_aliases(row["team_name"]):
            matches[int(row["team_id"])] = row["team_name"]
    return matches


def _deterministic_venue_candidates(subject: str, country: str, rows) -> dict[int, str]:
    wanted = normalize_identity(subject)
    if len(wanted) < 6:
        return {}
    matches = {}
    for row in rows:
        if row["country"] != country:
            continue
        candidate = normalize_identity(row["name"])
        if wanted == candidate or wanted in candidate or candidate in wanted:
            matches[int(row["venue_id"])] = row["name"]
    return matches


def read_inventory(path: Path) -> list[dict]:
    with zipfile.ZipFile(path) as workbook:
        shared_root = ElementTree.fromstring(workbook.read("xl/sharedStrings.xml"))
        shared = ["".join(item.itertext()) for item in shared_root.findall(f"{XLSX_NS}si")]
        sheet = ElementTree.fromstring(workbook.read("xl/worksheets/sheet1.xml"))

    rows = []
    for row in sheet.findall(f".//{XLSX_NS}sheetData/{XLSX_NS}row"):
        values = {}
        for cell in row.findall(f"{XLSX_NS}c"):
            column = re.match(r"[A-Z]+", cell.attrib["r"]).group(0)
            raw = cell.find(f"{XLSX_NS}v")
            value = "" if raw is None else raw.text or ""
            if cell.attrib.get("t") == "s" and value:
                value = shared[int(value)]
            values[column] = value
        rows.append(values)

    header = rows[0]
    fields = {column: value for column, value in header.items()}
    return [
        {fields[column]: values.get(column, "") for column in fields}
        for values in rows[1:]
        if values.get("A")
    ]


def _index(rows, name_key, id_key, country_key="country"):
    result = {}
    for row in rows:
        key = (row[country_key], normalize_identity(row[name_key]))
        result.setdefault(key, set()).add(int(row[id_key]))
    return result


def load_identity_inventory(db) -> dict:
    db.execute(text("SET TRANSACTION READ ONLY"))
    teams = db.execute(text("""
        SELECT DISTINCT team_id, team_name, country
        FROM (
            SELECT home_team_id AS team_id, home_team AS team_name, country FROM fixtures
            UNION
            SELECT away_team_id, away_team, country FROM fixtures
        ) represented
        WHERE team_id IS NOT NULL AND btrim(team_name) <> '' AND btrim(country) <> ''
    """)).mappings().all()
    venues = db.execute(text("""
        SELECT DISTINCT fixture_countries.country, venue.venue_id, name.name
        FROM (
            SELECT DISTINCT country, venue_id FROM fixtures WHERE venue_id IS NOT NULL AND btrim(country) <> ''
        ) fixture_countries
        JOIN venues venue ON venue.venue_id = fixture_countries.venue_id
        CROSS JOIN LATERAL (
            SELECT venue.name
            UNION
            SELECT venue_name.name FROM venue_names venue_name WHERE venue_name.venue_id = venue.venue_id
        ) name
        WHERE btrim(name.name) <> ''
    """)).mappings().all()
    published = [dict(row) for row in db.execute(text("""
        SELECT subject_type, team_a_id, team_b_id, venue_id,
               (to_jsonb(decision_facts)->>'team_id')::integer AS team_id,
               attribute_key
        FROM decision_facts WHERE publication_status = 'PUBLISHED'
    """)).mappings().all()]
    team_index = _index(teams, "team_name", "team_id")
    represented_team_ids = {int(row["team_id"]) for row in teams}
    for (country, alias), team_id in REVIEWED_TEAM_ALIASES.items():
        if team_id in represented_team_ids:
            team_index.setdefault((country, normalize_identity(alias)), set()).add(team_id)
    venue_index = _index(venues, "name", "venue_id")
    represented_venue_ids = {int(row["venue_id"]) for row in venues}
    for (country, alias), venue_id in REVIEWED_VENUE_ALIASES.items():
        if venue_id in represented_venue_ids:
            venue_index[(country, normalize_identity(alias))] = {venue_id}
    return {
        "teams": teams,
        "venues": venues,
        "published": published,
        "team_index": team_index,
        "venue_index": venue_index,
    }


def _plausible(subject: str, country: str, rows, name_key: str) -> list[str]:
    wanted = normalize_identity(subject)
    matches = []
    for row in rows:
        if row["country"] != country:
            continue
        candidate = normalize_identity(row[name_key])
        ratio = SequenceMatcher(None, wanted, candidate).ratio()
        if ratio >= 0.82 or (len(wanted) >= 6 and (wanted in candidate or candidate in wanted)):
            matches.append(f'{row[name_key]} [{row.get("team_id", row.get("venue_id"))}]')
    return sorted(set(matches))[:5]


def reconcile_row(row: dict, inventory: dict) -> dict:
    country = row["Country"]
    scope = row["Subject Type"]
    subject = row["Subject"]
    category = row["Category"]
    ids = []
    note = ""
    dormant_note = REVIEWED_DORMANT_SUBJECTS.get((country, subject, category, scope))
    if dormant_note:
        return _result(row, [], "NOT_IN_CURRENT_INVENTORY", dormant_note)

    if scope == "TEAM_PAIR":
        parts = subject.split(PAIR_SEPARATOR)
        if len(parts) != 2:
            return _result(row, [], "NEEDS_IDENTITY_REVIEW", "Team pair is not expressed as two canonical subjects")
        candidates = [inventory["team_index"].get((country, normalize_identity(part)), set()) for part in parts]
        methods = ["exact", "exact"]
        for index, (part, candidate) in enumerate(zip(parts, candidates)):
            if not candidate:
                deterministic = _deterministic_team_candidates(part, country, inventory["teams"])
                candidates[index] = set(deterministic)
                methods[index] = "deterministic alias"
        if all(len(candidate) == 1 for candidate in candidates):
            ids = sorted(next(iter(candidate)) for candidate in candidates)
            note = f"Canonical pair resolved ({methods[0]}; {methods[1]})"
        elif any(len(candidate) > 1 for candidate in candidates):
            return _result(row, [], "NEEDS_IDENTITY_REVIEW", "An exact team name resolves to multiple canonical teams")
        else:
            plausible = [
                _plausible(part, country, inventory["teams"], "team_name") if len(candidate) != 1 else []
                for part, candidate in zip(parts, candidates)
            ]
            status = "NEEDS_IDENTITY_REVIEW" if any(plausible) else "NOT_IN_CURRENT_INVENTORY"
            return _result(row, [], status, f"Unresolved canonical pair candidates: {plausible}" if any(plausible) else "One or both teams are absent from current fixtures")
    elif scope == "TEAM":
        candidates = inventory["team_index"].get((country, normalize_identity(subject)), set())
        method = "exact"
        if not candidates:
            candidates = set(_deterministic_team_candidates(subject, country, inventory["teams"]))
            method = "deterministic alias"
        if len(candidates) == 1:
            ids = [next(iter(candidates))]
            note = f"Canonical team resolved ({method})"
        elif len(candidates) > 1:
            return _result(row, [], "NEEDS_IDENTITY_REVIEW", "Exact team name resolves to multiple canonical teams")
        else:
            plausible = _plausible(subject, country, inventory["teams"], "team_name")
            return _result(row, [], "NEEDS_IDENTITY_REVIEW" if plausible else "NOT_IN_CURRENT_INVENTORY", f"No exact canonical team; plausible candidates: {plausible}" if plausible else "Team is absent from current fixtures")
    elif scope == "VENUE":
        candidates = inventory["venue_index"].get((country, normalize_identity(subject)), set())
        method = "exact name/alias"
        if not candidates:
            candidates = set(_deterministic_venue_candidates(subject, country, inventory["venues"]))
            method = "unique contained name/alias"
        if len(candidates) == 1:
            ids = [next(iter(candidates))]
            note = REVIEWED_IDENTITY_NOTES.get((country, subject), f"Canonical venue resolved ({method})")
        elif len(candidates) > 1:
            return _result(row, [], "NEEDS_IDENTITY_REVIEW", "Exact venue name/alias resolves to multiple canonical venues")
        else:
            plausible = _plausible(subject, country, inventory["venues"], "name")
            return _result(row, [], "NEEDS_IDENTITY_REVIEW" if plausible else "NOT_IN_CURRENT_INVENTORY", f"No exact canonical venue; plausible candidates: {plausible}" if plausible else "Venue is absent from current fixtures and aliases")
    else:
        return _result(row, [], "NEEDS_IDENTITY_REVIEW", f"Unsupported subject scope {scope}")

    identity = (scope, *(ids if scope == "TEAM_PAIR" else [ids[0]]), category)
    for fact in inventory["published"]:
        fact_identity = (
            ("TEAM_PAIR", fact["team_a_id"], fact["team_b_id"], fact["attribute_key"])
            if fact["subject_type"] == "TEAM_PAIR"
            else (fact["subject_type"], fact["team_id"] if fact["subject_type"] == "TEAM" else fact["venue_id"], fact["attribute_key"])
        )
        if identity == fact_identity:
            return _result(row, ids, "ALREADY_PUBLISHED", "Equivalent published DECIDE fact already exists")
    return _result(row, ids, "READY", note or "Exact canonical identity resolved")


def _result(row, ids, status, note):
    notes = row.get("Notes", "")
    evidence_season = "2025/26" if "2025/26" in notes else ""
    catalogue_status = {
        "READY": "ACTIVE",
        "ALREADY_PUBLISHED": "ALREADY_ACTIVE",
        "NOT_IN_CURRENT_INVENTORY": "DORMANT_NOT_IN_INVENTORY",
        "NEEDS_IDENTITY_REVIEW": "DORMANT_IDENTITY_REVIEW",
    }[status]
    return {
        "country": row["Country"],
        "subject": row["Subject"],
        "category": row["Category"],
        "scope": row["Subject Type"],
        "matchgoer_subject_id(s)": ";".join(str(value) for value in ids),
        "reconciliation_status": status,
        "catalogue_status": catalogue_status,
        "reconciliation_note": note,
        "editorial_label": row["Supporter Label"],
        "short_explanation": row["Short Explanation"],
        "discovery_value": row["Discovery Value"],
        "lead_priority": row["Lead Priority"].upper(),
        "evidence_url": row["Evidence URL"],
        "evidence_season": evidence_season,
        "editorial_status": row["Editorial Status"],
        "evidence_note": notes,
    }


def write_reconciliation(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def summary(rows: list[dict]) -> dict:
    return {
        "total": len(rows),
        "status": dict(sorted(Counter(row["reconciliation_status"] for row in rows).items())),
        "by_country": dict(sorted(Counter(row["country"] for row in rows).items())),
        "by_category": dict(sorted(Counter(row["category"] for row in rows).items())),
    }


def publication_summary(rows: list[dict]) -> dict:
    ready = [row for row in rows if row["reconciliation_status"] == "READY"]
    already = [row for row in rows if row["reconciliation_status"] == "ALREADY_PUBLISHED"]
    evidence = [row for row in ready if row["evidence_url"]]
    return {
        "total_approved": len(rows),
        "facts_to_insert": len(ready),
        "facts_already_present": len(already),
        "active_catalogue_facts": len(ready) + len(already),
        "evidence_rows_to_insert": len(evidence),
        "new_facts_without_evidence_metadata": sum(not row["evidence_url"] for row in ready),
        "active_facts_without_evidence_metadata": sum(not row["evidence_url"] for row in ready + already),
        "dormant_identity_review": sum(row["reconciliation_status"] == "NEEDS_IDENTITY_REVIEW" for row in rows),
        "dormant_not_in_inventory": sum(row["reconciliation_status"] == "NOT_IN_CURRENT_INVENTORY" for row in rows),
        "updates": 0,
        "deletes": 0,
        "hosted_writes": 0,
    }


def write_publication_summary(path: Path, rows: list[dict], reconciliation_path: Path) -> None:
    payload = publication_summary(rows)
    payload["source_inventory"] = "matchgoer_decide_publication_inventory_v0_1.xlsx"
    payload["reconciliation_artifact"] = reconciliation_path.as_posix()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sql_literal(value: str | None) -> str:
    if not value:
        return "NULL"
    return "'" + value.replace("'", "''") + "'"


def _publication_values(rows: list[dict]) -> str:
    values = []
    for row in rows:
        ids = [int(value) for value in row["matchgoer_subject_id(s)"].split(";")]
        scope = row["scope"]
        team_a = ids[0] if scope == "TEAM_PAIR" else None
        team_b = ids[1] if scope == "TEAM_PAIR" else None
        venue = ids[0] if scope == "VENUE" else None
        team = ids[0] if scope == "TEAM" else None
        values.append("(" + ", ".join([
            _sql_literal(scope), str(team_a) if team_a is not None else "NULL",
            str(team_b) if team_b is not None else "NULL", str(venue) if venue is not None else "NULL",
            str(team) if team is not None else "NULL", _sql_literal(row["category"]),
            _sql_literal(row["editorial_label"]), _sql_literal(row["short_explanation"]),
            _sql_literal(row["lead_priority"]), _sql_literal(row["evidence_url"]),
            _sql_literal(row["evidence_season"]), _sql_literal(row["evidence_note"]),
        ]) + ")")
    return ",\n    ".join(values)


def write_publication_sql(path: Path, rows: list[dict]) -> None:
    active = [row for row in rows if row["reconciliation_status"] in {"READY", "ALREADY_PUBLISHED"}]
    values = _publication_values(active)
    sql = f"""BEGIN;

CREATE TEMP TABLE decide_approved_catalogue (
    subject_type text NOT NULL, team_a_id integer, team_b_id integer, venue_id integer, team_id integer,
    attribute_key text NOT NULL, label text NOT NULL, explanation text NOT NULL, lead_priority text NOT NULL,
    evidence_url text, evidence_season text, evidence_note text
) ON COMMIT DROP;

INSERT INTO decide_approved_catalogue VALUES
    {values};

DO $$
BEGIN
    IF (SELECT count(*) FROM decide_approved_catalogue) <> {len(active)} THEN
        RAISE EXCEPTION 'DECIDE approved catalogue row-count mismatch';
    END IF;
    IF EXISTS (
        SELECT 1 FROM decide_approved_catalogue approved
        WHERE (approved.subject_type = 'TEAM' AND NOT EXISTS (SELECT 1 FROM teams WHERE team_id = approved.team_id))
           OR (approved.subject_type = 'TEAM_PAIR' AND (
               NOT EXISTS (SELECT 1 FROM teams WHERE team_id = approved.team_a_id)
               OR NOT EXISTS (SELECT 1 FROM teams WHERE team_id = approved.team_b_id)))
           OR (approved.subject_type = 'VENUE' AND NOT EXISTS (SELECT 1 FROM venues WHERE venue_id = approved.venue_id))
    ) THEN
        RAISE EXCEPTION 'DECIDE approved catalogue canonical identity mismatch';
    END IF;
END $$;

INSERT INTO decision_facts (
    subject_type, team_a_id, team_b_id, venue_id, team_id, attribute_key, label, explanation,
    publication_status, confidence, lead_priority, reviewed_at, reviewed_by
)
SELECT subject_type, team_a_id, team_b_id, venue_id, team_id, attribute_key, label, explanation,
       'PUBLISHED', 'HIGH', lead_priority, '2026-09-03T00:00:00Z',
       'Matchgoer five-country editorial inventory v0.1'
FROM decide_approved_catalogue
ON CONFLICT DO NOTHING;

INSERT INTO decision_evidence (
    fact_id, source_title, source_url, evidence_note, disposition, retrieved_at, reviewed_at, review_status
)
SELECT fact.fact_id, 'Approved five-country DECIDE inventory evidence', approved.evidence_url,
       coalesce(nullif(approved.evidence_note, ''), 'Evidence retained from approved editorial inventory.'),
       'SUPPORTS', '2026-09-03', '2026-09-03T00:00:00Z', 'ACCEPTED'
FROM decide_approved_catalogue approved
JOIN decision_facts fact ON fact.subject_type = approved.subject_type
 AND fact.attribute_key = approved.attribute_key
 AND fact.team_a_id IS NOT DISTINCT FROM approved.team_a_id
 AND fact.team_b_id IS NOT DISTINCT FROM approved.team_b_id
 AND fact.venue_id IS NOT DISTINCT FROM approved.venue_id
 AND fact.team_id IS NOT DISTINCT FROM approved.team_id
WHERE approved.evidence_url IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM decision_evidence evidence
      WHERE evidence.fact_id = fact.fact_id AND evidence.source_url = approved.evidence_url
  );

DO $$
DECLARE reconciled integer;
BEGIN
    SELECT count(*) INTO reconciled
    FROM decide_approved_catalogue approved
    JOIN decision_facts fact ON fact.subject_type = approved.subject_type
     AND fact.attribute_key = approved.attribute_key
     AND fact.team_a_id IS NOT DISTINCT FROM approved.team_a_id
     AND fact.team_b_id IS NOT DISTINCT FROM approved.team_b_id
     AND fact.venue_id IS NOT DISTINCT FROM approved.venue_id
     AND fact.team_id IS NOT DISTINCT FROM approved.team_id
     AND fact.publication_status = 'PUBLISHED';
    IF reconciled <> {len(active)} THEN
        RAISE EXCEPTION 'DECIDE publication reconciliation failed: expected {len(active)}, found %', reconciled;
    END IF;
END $$;

COMMIT;
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(sql, encoding="utf-8")
