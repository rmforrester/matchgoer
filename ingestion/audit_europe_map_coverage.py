"""Read-only hosted audit of European fixture location-discovery coverage."""

from __future__ import annotations

import csv
import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine, text


ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "reports" / "ingestion" / "europe-breadth-provider-audit-2026.json"
REPORT_DIR = ROOT / "reports" / "ingestion"
JSON_REPORT = REPORT_DIR / "europe-map-coverage-hosted-2026.json"
COUNTRY_CSV = REPORT_DIR / "europe-map-coverage-hosted-2026.csv"
COMPETITION_CSV = REPORT_DIR / "europe-map-coverage-by-competition-hosted-2026.csv"


def rating(percent: float) -> str:
    if percent >= 90:
        return "EXCELLENT"
    if percent >= 80:
        return "GOOD"
    if percent >= 60:
        return "USABLE"
    if percent >= 40:
        return "PARTIAL"
    if percent >= 10:
        return "WEAK"
    return "NOT USABLE"


def distribution_band(percent: float) -> str:
    if percent >= 90:
        return ">=90%"
    if percent >= 80:
        return "80-89.9%"
    if percent >= 70:
        return "70-79.9%"
    if percent >= 60:
        return "60-69.9%"
    if percent >= 50:
        return "50-59.9%"
    if percent >= 40:
        return "40-49.9%"
    if percent >= 10:
        return "10-39.9%"
    return "<10%"


def main() -> None:
    reference = json.loads(REFERENCE.read_text(encoding="utf-8"))
    uefa_countries = reference["uefa_countries"]
    unavailable = {row["country"]: row["reason"] for row in reference["unavailable"]}
    generated_at = datetime.now(timezone.utc)
    local_now = generated_at.astimezone(ZoneInfo("Europe/Bucharest"))
    default_start = local_now.date().isoformat()
    default_end = "2026-09-30"

    engine = create_engine(os.environ["DATABASE_URL"], connect_args={"connect_timeout": 10})
    query = text(
        """
        SELECT
          f.country,
          f.league_id,
          f.league_name,
          f.season,
          count(*)::int AS fixtures,
          count(*) FILTER (WHERE f.venue_id IS NOT NULL)::int AS canonical_venue_link,
          count(*) FILTER (
            WHERE f.venue_id IS NOT NULL
              AND v.latitude IS NOT NULL AND v.longitude IS NOT NULL
              AND v.latitude BETWEEN -90 AND 90
              AND v.longitude BETWEEN -180 AND 180
          )::int AS location_discoverable,
          count(*) FILTER (WHERE f.venue_id IS NULL)::int AS fixture_venue_id_null,
          count(*) FILTER (
            WHERE f.venue_id IS NOT NULL
              AND (v.latitude IS NULL OR v.longitude IS NULL)
          )::int AS linked_coordinates_null,
          count(*) FILTER (
            WHERE f.venue_id IS NOT NULL
              AND v.latitude IS NOT NULL AND v.longitude IS NOT NULL
              AND NOT (
                v.latitude BETWEEN -90 AND 90
                AND v.longitude BETWEEN -180 AND 180
              )
          )::int AS linked_coordinates_invalid,
          count(*) FILTER (
            WHERE f.venue_id IS NOT NULL
              AND v.latitude IS NOT NULL AND v.longitude IS NOT NULL
              AND v.latitude BETWEEN -90 AND 90
              AND v.longitude BETWEEN -180 AND 180
              AND f.fixture_date >= :display_start
              AND f.fixture_date < (CAST(:display_end AS date) + interval '1 day')
          )::int AS current_default_window_displayable
        FROM fixtures f
        LEFT JOIN venues v ON v.venue_id = f.venue_id
        WHERE f.country = ANY(:countries)
        GROUP BY f.country, f.league_id, f.league_name, f.season
        ORDER BY f.country, f.league_id, f.season
        """
    )
    with engine.connect() as connection:
        connection.execute(text("SET TRANSACTION READ ONLY"))
        rows = [
            dict(row)
            for row in connection.execute(
                query,
                {
                    "countries": uefa_countries,
                    "display_start": default_start,
                    "display_end": default_end,
                },
            ).mappings()
        ]

    for row in rows:
        row["completion_percent"] = round(100 * row["location_discoverable"] / row["fixtures"], 1)
        row["missing"] = row["fixtures"] - row["location_discoverable"]

    by_country: dict[str, list[dict]] = {}
    for row in rows:
        by_country.setdefault(row["country"], []).append(row)

    countries = []
    for country, country_rows in by_country.items():
        fixtures = sum(row["fixtures"] for row in country_rows)
        linked = sum(row["canonical_venue_link"] for row in country_rows)
        discoverable = sum(row["location_discoverable"] for row in country_rows)
        null_links = sum(row["fixture_venue_id_null"] for row in country_rows)
        null_coordinates = sum(row["linked_coordinates_null"] for row in country_rows)
        invalid_coordinates = sum(row["linked_coordinates_invalid"] for row in country_rows)
        displayable = sum(row["current_default_window_displayable"] for row in country_rows)
        percent = round(100 * discoverable / fixtures, 1)
        reasons = {
            "fixture venue_id NULL": null_links,
            "linked venue coordinates NULL": null_coordinates,
            "linked venue coordinates invalid": invalid_coordinates,
        }
        nonzero_reasons = [(name, count) for name, count in reasons.items() if count]
        main_reason = max(nonzero_reasons, key=lambda item: item[1])[0] if nonzero_reasons else "none"
        competitions = sorted({f'{row["league_name"]} ({row["league_id"]})' for row in country_rows})
        countries.append(
            {
                "country": country,
                "competitions": competitions,
                "competition_count": len(competitions),
                "fixtures": fixtures,
                "canonical_venue_link": linked,
                "fixtures_with_valid_coordinates": discoverable,
                "location_discoverable": discoverable,
                "completion_percent": percent,
                "rating": rating(percent),
                "missing": fixtures - discoverable,
                "fixture_venue_id_null": null_links,
                "linked_coordinates_null": null_coordinates,
                "linked_coordinates_invalid": invalid_coordinates,
                "main_reason": main_reason,
                "current_default_window_displayable": displayable,
            }
        )
    countries.sort(key=lambda row: (-row["completion_percent"], row["country"]))

    total_fixtures = sum(row["fixtures"] for row in countries)
    total_discoverable = sum(row["location_discoverable"] for row in countries)
    represented = {row["country"] for row in countries}
    missing_countries = [country for country in uefa_countries if country not in represented]
    distribution = Counter(distribution_band(row["completion_percent"]) for row in countries)
    bands = [">=90%", "80-89.9%", "70-79.9%", "60-69.9%", "50-59.9%", "40-49.9%", "10-39.9%", "<10%"]
    payload = {
        "audit": {
            "generated_at_utc": generated_at.isoformat(),
            "mode": "READ_ONLY",
            "definition": "fixture has a canonical venue link and non-null, in-range latitude/longitude",
            "discover_path": "GET /nearby inner-joins fixtures to venues and requires coordinates; frontend then applies date/radius filters",
            "current_display_window": {
                "timezone": "Europe/Bucharest",
                "start_date": default_start,
                "end_date": default_end,
                "note": "Current default frontend date window; actual visibility also depends on the supporter-selected place/radius or viewport.",
            },
        },
        "summary": {
            "reference_countries": len(uefa_countries),
            "represented_countries": len(countries),
            "competitions": sum(row["competition_count"] for row in countries),
            "fixtures": total_fixtures,
            "location_discoverable": total_discoverable,
            "completion_percent": round(100 * total_discoverable / total_fixtures, 1),
            "missing": total_fixtures - total_discoverable,
            "current_default_window_displayable": sum(row["current_default_window_displayable"] for row in countries),
            "country_distribution": {band: distribution.get(band, 0) for band in bands},
        },
        "countries": countries,
        "competitions": rows,
        "reference_universe": {
            "represented": sorted(represented),
            "no_hosted_fixtures": missing_countries,
            "established_provider_unavailable": [
                {"country": country, "reason": unavailable[country]}
                for country in missing_countries
                if country in unavailable
            ],
        },
    }
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    JSON_REPORT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    country_fields = [
        "country", "competitions", "fixtures", "canonical_venue_link",
        "fixtures_with_valid_coordinates", "location_discoverable", "completion_percent",
        "rating", "missing", "fixture_venue_id_null", "linked_coordinates_null",
        "linked_coordinates_invalid", "main_reason", "current_default_window_displayable",
    ]
    with COUNTRY_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=country_fields)
        writer.writeheader()
        for row in countries:
            output = {key: row[key] for key in country_fields}
            output["competitions"] = " | ".join(row["competitions"])
            writer.writerow(output)

    competition_fields = list(rows[0]) if rows else []
    with COMPETITION_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=competition_fields)
        writer.writeheader()
        writer.writerows(rows)

    print(json.dumps(payload["summary"], indent=2))
    print(JSON_REPORT)
    print(COUNTRY_CSV)
    print(COMPETITION_CSV)


if __name__ == "__main__":
    main()
