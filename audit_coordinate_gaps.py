"""Bounded, cached candidate audit for imported venue coordinate gaps."""

from __future__ import annotations

import argparse
import html
import json
import time
import unicodedata
from pathlib import Path

from geopy.geocoders import Nominatim
from sqlalchemy import create_engine, text

from ingestion.environment import ROOT, database_url
from retry_failed_coordinates import USER_AGENT, save_json


CACHE = ROOT / ".cache" / "nominatim" / "mvp-coordinate-gaps-2026.json"
REPORT = ROOT / "reports" / "ingestion" / "mvp-coordinate-gaps-2026.json"
LEAGUES = {
    "England": [39, 40, 41, 42, 43, 50, 51, 58, 59, 931, 60],
    "USA": [253, 255, 489],
    "Sweden": [113, 114, 563, 564, 592, 593, 594, 595, 596, 597],
}


def norm(value: object) -> str:
    value = html.unescape(str(value or "")).replace("&apos;", "'")
    value = unicodedata.normalize("NFKD", value)
    return " ".join("".join(ch for ch in value if not unicodedata.combining(ch)).casefold().split())


def gaps() -> list[dict]:
    rows = []
    engine = create_engine(database_url(), connect_args={"connect_timeout": 10})
    with engine.connect() as connection:
        for audit_country, league_ids in LEAGUES.items():
            found = connection.execute(text("""
                SELECT DISTINCT v.venue_id, v.provider_venue_id, v.name, v.address, v.city, v.country
                FROM venues v JOIN fixtures f ON f.venue_id = v.venue_id
                WHERE f.season = 2026 AND f.league_id = ANY(:ids)
                  AND (v.latitude IS NULL OR v.longitude IS NULL)
                ORDER BY v.venue_id
            """), {"ids": league_ids}).mappings()
            rows.extend([{**dict(row), "audit_country": audit_country} for row in found])
    return rows


def locality_match(candidate: dict, venue: dict) -> bool:
    expected = norm(venue["city"]).split(",", 1)[0]
    address = candidate.get("address") or {}
    values = [address.get(key) for key in ("city", "town", "village", "municipality", "borough", "county")]
    return bool(expected and any(expected == norm(value) for value in values if value))


def exact_names(candidate: dict) -> set[str]:
    values = [candidate.get("name"), str(candidate.get("display_name") or "").split(",", 1)[0]]
    values.extend((candidate.get("namedetails") or {}).values())
    return {norm(value) for value in values if value}


def classify(venue: dict, candidates: list[dict], error: str | None) -> tuple[str, dict | None, str]:
    if error:
        return "failed_request", None, error
    if not candidates:
        return "unresolved", None, "No candidates returned."
    expected = norm(venue["name"])
    strong = [candidate for candidate in candidates if locality_match(candidate, venue) and expected in exact_names(candidate)]
    if len(strong) == 1:
        return "accepted", strong[0], "One exact name/alias candidate in the provider locality."
    if len(strong) > 1:
        return "ambiguous", None, f"{len(strong)} exact locality-compatible candidates."
    local = [candidate for candidate in candidates if locality_match(candidate, venue)]
    if local:
        return "ambiguous", None, "Local candidates exist without one exact name/alias match."
    return "wrong_city", None, "Candidates exist, but none matches the provider locality."


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-venues", type=int, default=20)
    parser.add_argument("--spacing", type=float, default=2.0)
    parser.add_argument("--supplement-unresolved", action="store_true")
    args = parser.parse_args()
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    venues = gaps()
    if args.supplement_unresolved:
        targets = [venue for venue in venues if str(venue["venue_id"]) in cache
                   and cache[str(venue["venue_id"])]["status"] == "unresolved"
                   and not cache[str(venue["venue_id"])].get("supplemented")]
    else:
        targets = [venue for venue in venues if str(venue["venue_id"]) not in cache]
    client = Nominatim(user_agent=USER_AGENT)
    last_request = 0.0
    for venue in targets[:args.max_venues]:
        wait = args.spacing - (time.monotonic() - last_request)
        if wait > 0:
            time.sleep(wait)
        keys = ("name", "city", "country") if args.supplement_unresolved else ("name", "address", "city", "country")
        query = ", ".join(str(venue.get(key)).strip() for key in keys if venue.get(key))
        try:
            locations = client.geocode(query, exactly_one=False, limit=10, timeout=20,
                                       addressdetails=True, namedetails=True, extratags=True) or []
            candidates, error = [location.raw for location in locations], None
        except Exception as exc:
            candidates, error = [], f"{exc.__class__.__name__}: {exc}"
        last_request = time.monotonic()
        status, chosen, reason = classify(venue, candidates, error)
        entry = {"venue": venue, "query": query, "candidates": candidates,
                 "error": error, "status": status, "reason": reason,
                 "latitude": float(chosen["lat"]) if chosen else None,
                 "longitude": float(chosen["lon"]) if chosen else None,
                 "chosen_result": chosen.get("display_name") if chosen else None}
        if args.supplement_unresolved:
            previous = cache[str(venue["venue_id"])]
            entry["attempts"] = previous.get("attempts", []) + [{"query": previous["query"],
                "status": previous["status"], "candidate_count": len(previous.get("candidates", []))}]
            entry["supplemented"] = True
        cache[str(venue["venue_id"])] = entry
        save_json(CACHE, cache)
        print(json.dumps({"venue_id": venue["venue_id"], "name": venue["name"], "status": status,
                          "candidates": len(candidates), "error": error}, ensure_ascii=False), flush=True)
        if error:
            break
    relevant = [cache[str(venue["venue_id"])] for venue in venues if str(venue["venue_id"]) in cache]
    totals = {}
    for entry in relevant:
        country = entry["venue"]["audit_country"]
        totals.setdefault(country, {})[entry["status"]] = totals.setdefault(country, {}).get(entry["status"], 0) + 1
    report = {"total_gaps": len(venues), "cached": len(relevant), "remaining": len(venues) - len(relevant),
              "totals": totals, "venues": relevant}
    save_json(REPORT, report)
    print(json.dumps({key: report[key] for key in ("total_gaps", "cached", "remaining", "totals")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
