"""Read-only database and active-API QA for the 2026 MVP data-quality stage."""

from __future__ import annotations

import json
from urllib.parse import urlencode
from urllib.request import urlopen

from sqlalchemy import create_engine, text

from ingestion.environment import ROOT, database_url


REPORT = ROOT / "reports" / "ingestion" / "mvp-data-quality-final-2026.json"
BASE_URL = "http://127.0.0.1:8000"
COUNTRY_LEAGUES = {
    "USA": [253, 255, 489],
    "Sweden": [113, 114, 563, 564, 592, 593, 594, 595, 596, 597],
    "England": [39, 40, 41, 42, 43, 50, 51, 58, 59, 931, 60],
}
MARKETS = {
    "Stockholm": (59.3293, 18.0686, 60),
    "Goteborg": (57.7089, 11.9746, 60),
    "Vaxjo_lower_league": (56.8790, 14.8059, 70),
    "Brooklyn_New_York": (40.6782, -73.9442, 45),
    "Jacksonville": (30.3322, -81.6557, 45),
    "Fort_Wayne": (41.0793, -85.1394, 50),
    "London": (51.5074, -0.1278, 35),
    "Manchester": (53.4808, -2.2426, 35),
}


def get(path: str, params: dict | None = None):
    url = BASE_URL + path + (("?" + urlencode(params)) if params else "")
    try:
        with urlopen(url, timeout=15) as response:
            return {"url": url, "status": response.status, "data": json.load(response)}
    except Exception as exc:
        return {"url": url, "status": None, "error": f"{type(exc).__name__}: {exc}"}


def main() -> int:
    engine = create_engine(database_url(), connect_args={"connect_timeout": 10})
    db = {"by_country_league": {}, "country_totals": {}}
    all_ids = [league for ids in COUNTRY_LEAGUES.values() for league in ids]
    with engine.connect() as connection:
        db["fixture_venue_orphans"] = connection.execute(text("""
            SELECT count(*) FROM fixtures f LEFT JOIN venues v ON v.venue_id=f.venue_id
            WHERE f.venue_id IS NOT NULL AND v.venue_id IS NULL
        """)).scalar_one()
        db["team_venue_orphans"] = connection.execute(text("""
            SELECT count(*) FROM teams t LEFT JOIN venues v ON v.venue_id=t.venue_id
            WHERE t.venue_id IS NOT NULL AND v.venue_id IS NULL
        """)).scalar_one()
        db["duplicate_provider_venue_ids"] = connection.execute(text("""
            SELECT count(*) FROM (
              SELECT provider_venue_id FROM venues WHERE provider_venue_id IS NOT NULL
              GROUP BY provider_venue_id HAVING count(*) > 1
            ) d
        """)).scalar_one()
        rows = connection.execute(text("""
            SELECT f.league_id, max(f.league_name) AS league_name, count(*) AS fixtures,
                   count(*) FILTER (WHERE f.venue_id IS NULL) AS unresolved_links,
                   count(DISTINCT f.venue_id) FILTER (WHERE f.venue_id IS NOT NULL) AS venue_refs,
                   count(DISTINCT f.venue_id) FILTER (
                     WHERE v.latitude BETWEEN -90 AND 90 AND v.longitude BETWEEN -180 AND 180
                   ) AS venue_refs_with_coordinates
            FROM fixtures f LEFT JOIN venues v ON v.venue_id=f.venue_id
            WHERE f.season=2026 AND f.league_id = ANY(:league_ids)
            GROUP BY f.league_id ORDER BY f.league_id
        """), {"league_ids": all_ids}).mappings()
        keyed = {row["league_id"]: dict(row) for row in rows}
        for country, ids in COUNTRY_LEAGUES.items():
            db["by_country_league"][country] = [keyed[i] for i in ids if i in keyed]
            db["country_totals"][country] = dict(connection.execute(text("""
                SELECT count(*) AS fixtures,
                       count(*) FILTER (WHERE f.venue_id IS NULL) AS unresolved_links,
                       count(DISTINCT f.venue_id) FILTER (WHERE f.venue_id IS NOT NULL) AS distinct_venues,
                       count(DISTINCT f.venue_id) FILTER (
                         WHERE v.latitude BETWEEN -90 AND 90 AND v.longitude BETWEEN -180 AND 180
                       ) AS distinct_venues_with_coordinates
                FROM fixtures f LEFT JOIN venues v ON v.venue_id=f.venue_id
                WHERE f.season=2026 AND f.league_id = ANY(:league_ids)
            """), {"league_ids": ids}).mappings().one())

    api = {
        "leagues": get("/leagues"),
        "fixtures": get("/fixtures"),
        "markets": {},
        "venue_searches": {},
    }
    for name, (latitude, longitude, radius) in MARKETS.items():
        result = get("/nearby", {
            "latitude": latitude, "longitude": longitude, "radius": radius,
            "start_date": "2026-01-01", "end_date": "2027-06-30", "limit": 100,
        })
        if "data" in result:
            result["result_count"] = len(result["data"])
            result["sample"] = result.pop("data")[:5]
        api["markets"][name] = result
    for query in ["Hodges Stadium", "Maimonides Park", "Ruoff Mortgage", "Stockholm", "London"]:
        result = get("/venues/search", {"q": query, "limit": 10})
        if "data" in result:
            result["result_count"] = len(result["data"])
            result["sample"] = result.pop("data")[:5]
        api["venue_searches"][query] = result

    if "data" in api["leagues"]:
        api["leagues"]["result_count"] = len(api["leagues"]["data"])
        api["leagues"].pop("data")
    if "data" in api["fixtures"]:
        api["fixtures"]["result_count"] = len(api["fixtures"]["data"])
        api["fixtures"]["sample"] = api["fixtures"].pop("data")[:3]

    report = {"database": db, "active_api": api}
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
