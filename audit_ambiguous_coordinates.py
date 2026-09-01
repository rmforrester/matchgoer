"""Cache and conservatively audit Nominatim candidates for ambiguous venues."""

from __future__ import annotations

import argparse
import html
import json
import time
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from geopy.geocoders import Nominatim

from audit_coordinates import collect_cohort, scopes_from_cohort_report
from ingestion.api_football import ApiFootballClient
from ingestion.environment import ROOT
from ingestion.pipeline import TerraceTalkImporter
from retry_failed_coordinates import CHECKPOINT, SOURCE_REPORT, USER_AGENT, load_json, save_json, venue_catalog


CANDIDATE_CACHE = ROOT / ".cache" / "nominatim" / "coordinate-ambiguity-candidates-2026.json"
AUDIT_REPORT = ROOT / "reports" / "ingestion" / "coordinate-ambiguity-audit-2026.json"

# Explicit decisions from inspection of the cached raw candidates. Candidate indexes
# are intentionally venue-specific; these are not generalized fuzzy-match rules.
REVIEW_OVERRIDES: dict[str, tuple[str, int | None, str, str]] = {
    "12273": ("safely_resolved_from_candidates", 0, "Exact name and Swansea locality; the stadium feature is clearly preferable to the pitch and club shop.", ""),
    "10651": ("still_ambiguous", None, "All three Merthyr Tydfil results are bus stops and none represents Penydarren Park.", "The venue itself is absent from the candidate set."),
    "11918": ("safely_resolved_from_candidates", 0, "Exact PayPal Park name, street address, San Jose locality, and stadium feature.", ""),
    "19445": ("safely_resolved_from_candidates", 0, "Exact BC Place name, Vancouver locality, address, and stadium feature.", ""),
    "1833": ("safely_resolved_from_candidates", 0, "Exact Yankee Stadium name and address; Nominatim's New York locality is the provider's New York City.", ""),
    "1616": ("safely_resolved_from_candidates", 1, "Exact name and Carson locality; the stadium feature is clearly preferable to the sports-centre complex and bus stop.", ""),
    "1617": ("safely_resolved_from_candidates", 1, "Both results are stadium features, but only this candidate carries the provider's 400 Snelling Avenue address.", ""),
    "310": ("safely_resolved_from_candidates", 0, "Exact Stade Saputo name, Montréal locality, address, and stadium feature.", ""),
    "11535": ("insufficient_candidate_data", None, "Both limited searches returned no candidate for Q2 Stadium.", "No cached candidate payload to compare."),
    "19408": ("still_ambiguous", None, "Two Saint Louis stadium objects both carry CITYPARK as an old name and neither matches the provider street number.", "Two plausible stadium objects remain."),
    "20751": ("safely_resolved_from_candidates", 0, "Exact Protective Stadium name, Birmingham locality, and stadium feature.", ""),
    "11933": ("still_ambiguous", None, "The locality is correct, but candidates represent a museum and ferry terminal rather than the provider venue.", "The venue itself is absent from the candidate set."),
    "19452": ("safely_resolved_from_candidates", 0, "Single Indianapolis stadium candidate with the provider address and an expanded form of the provider name.", ""),
    "22767": ("insufficient_candidate_data", None, "Both limited searches returned no candidate.", "No cached candidate payload to compare."),
    "19706": ("insufficient_candidate_data", None, "Both limited searches returned no candidate.", "No cached candidate payload to compare."),
    "11936": ("safely_resolved_from_candidates", 0, "Exact Heart Health Park name, Sacramento locality, and sports-pitch feature.", ""),
    "21618": ("insufficient_candidate_data", None, "Both limited searches returned no candidate.", "No cached candidate payload to compare."),
    "20450": ("safely_resolved_from_candidates", 1, "Exact name and Hayward locality; the stadium object with the provider's Carlos Bee Boulevard address is clearly best.", ""),
    "18522": ("safely_resolved_from_candidates", 0, "Exact name and Seaside locality; the stadium object is clearly preferable to the colocated pitch.", ""),
    "6261": ("insufficient_candidate_data", None, "Both limited searches returned no candidate.", "No cached candidate payload to compare."),
    "20402": ("wrong_city_candidates", None, "The only result is in Travelers Rest, not the provider locality of Greenville.", "No candidate in the expected provider locality."),
    "6274": ("insufficient_candidate_data", None, "Both limited searches returned no candidate for the provider name MCU Park.", "No cached candidate payload to compare."),
    "20597": ("insufficient_candidate_data", None, "Both limited searches returned no candidate.", "No cached candidate payload to compare."),
    "1506": ("safely_resolved_from_candidates", 0, "Stockholm stadium candidate carries Tele2 Arena as its old name.", ""),
    "1509": ("safely_resolved_from_candidates", 0, "Exact Gamla Ullevi name, Göteborg locality, and stadium feature.", ""),
    "1511": ("insufficient_candidate_data", None, "Both limited searches returned no candidate for Bravida Arena.", "No cached candidate payload to compare."),
    "1524": ("safely_resolved_from_candidates", 0, "Uppsala sports-centre candidate carries Studenternas IP as an alternate name.", ""),
    "1503": ("safely_resolved_from_candidates", 0, "Exact name and Stockholm locality; the sports-centre object is clearly preferable to its colocated pitch.", ""),
    "1501": ("safely_resolved_from_candidates", 0, "Solna stadium candidate carries Friends Arena as its old name; the other result is only a map board.", ""),
    "1505": ("safely_resolved_from_candidates", 1, "Exact name and Degerfors locality; the sports-pitch object is clearly preferable to the neighbourhood result.", ""),
}


def norm(value: object) -> str:
    text = unicodedata.normalize("NFKD", html.unescape(str(value or "")))
    return " ".join("".join(ch for ch in text if not unicodedata.combining(ch)).casefold().split())


def actual_country(venue: dict[str, Any]) -> str:
    return str(venue.get("country") or venue.get("audit_country") or "")


def query_for(venue: dict[str, Any]) -> str:
    return ", ".join(str(venue.get(key)).strip() for key in ("name", "address", "city") if venue.get(key)) + ", " + actual_country(venue)


def compact_query_for(venue: dict[str, Any]) -> str:
    return ", ".join(str(venue.get(key)).strip() for key in ("name", "city") if venue.get(key)) + ", " + actual_country(venue)


def candidate_names(raw: dict[str, Any]) -> set[str]:
    values = [raw.get("name"), str(raw.get("display_name") or "").split(",", 1)[0]]
    values.extend((raw.get("namedetails") or {}).values())
    return {norm(value) for value in values if value}


def locality_match(raw: dict[str, Any], venue: dict[str, Any]) -> bool:
    expected = norm(venue.get("city")).split(",", 1)[0]
    address = raw.get("address") or {}
    keys = ("city", "town", "village", "municipality", "borough", "county", "state_district")
    return bool(expected and any(expected == norm(address.get(key)) for key in keys if address.get(key)))


def country_match(raw: dict[str, Any], venue: dict[str, Any]) -> bool:
    expected = norm(actual_country(venue))
    address = raw.get("address") or {}
    returned_code = norm(address.get("country_code"))
    expected_codes = {"usa": "us", "canada": "ca", "sweden": "se", "england": "gb", "wales": "gb"}
    if returned_code and expected_codes.get(expected):
        return returned_code == expected_codes[expected]
    returned = norm(address.get("country"))
    aliases = {"usa": {"united states", "united states of america"}, "england": {"united kingdom", "england"}}
    return returned == expected or returned in aliases.get(expected, set())


def address_match(raw: dict[str, Any], venue: dict[str, Any]) -> bool:
    expected = norm(venue.get("address"))
    return bool(expected and expected in norm(raw.get("display_name")))


def classify(venue: dict[str, Any], candidates: list[dict[str, Any]]) -> tuple[str, dict | None, str, str]:
    if not candidates:
        return "insufficient_candidate_data", None, "The fully specified cached search returned no candidates.", "No candidate payload to compare."
    local = [raw for raw in candidates if locality_match(raw, venue) and country_match(raw, venue)]
    if not local:
        return "wrong_city_candidates", None, "All returned candidates are outside the expected city/locality or country.", "No locality-valid candidate remains."
    expected_name = norm(venue.get("name"))
    exact_name = [raw for raw in local if expected_name in candidate_names(raw)]
    strong = exact_name or [raw for raw in local if address_match(raw, venue)]
    signal = "exact normalized venue name/alias" if exact_name else "exact provider address"
    if len(strong) == 1:
        chosen = strong[0]
        return "safely_resolved_from_candidates", chosen, f"One locality-valid candidate has an {signal} match.", ""
    if len(strong) > 1:
        return "still_ambiguous", None, f"Multiple locality-valid candidates share the {signal} signal.", f"{len(strong)} equally strong candidates remain."
    return "still_ambiguous", None, "Locality-valid candidates exist, but none has an exact normalized name/alias or provider-address match.", f"{len(local)} locality-valid candidate(s) remain without a decisive identity signal."


def breadth_venue_catalog(cohort_report: Path, provider_cache_dir: Path) -> dict[str, dict[str, Any]]:
    scopes = scopes_from_cohort_report(cohort_report, 2026)
    client = ApiFootballClient("cache-only", provider_cache_dir, min_request_interval=0)
    importer = TerraceTalkImporter.__new__(TerraceTalkImporter)
    importer.client = client
    venues, league_venues, _, labels = collect_cohort(client, importer, scopes)
    countries = {
        provider_id: labels[key][0]
        for key, provider_ids in league_venues.items()
        for provider_id in provider_ids
    }
    return {
        str(provider_id): {**venue, "audit_country": countries.get(provider_id, venue.get("country"))}
        for provider_id, venue in venues.items()
    }


def build_report(
    checkpoint: dict[str, dict], catalog: dict[str, dict], cache: dict[str, dict],
    selected_ids: set[str] | None = None,
) -> dict:
    rows = []
    totals: dict[str, Counter] = defaultdict(Counter)
    for venue_id, original in checkpoint.items():
        if selected_ids is not None and venue_id not in selected_ids:
            continue
        if original.get("status") != "ambiguous" and venue_id not in cache:
            continue
        if venue_id not in catalog:
            raise RuntimeError(f"Provider venue {venue_id} is absent from the supplied catalog")
        venue = catalog[venue_id]
        cached = cache.get(venue_id)
        if not cached or cached.get("error"):
            classification, chosen, reason, remaining = ("insufficient_candidate_data", None,
                "No successful cached candidate response is available.", "Candidate request failed or has not run.")
            candidates = [] if not cached else cached.get("candidates", [])
        else:
            candidates = cached.get("candidates", [])
            classification, chosen, reason, remaining = classify(venue, candidates)
        if venue_id in REVIEW_OVERRIDES:
            classification, chosen_index, reason, remaining = REVIEW_OVERRIDES[venue_id]
            chosen = candidates[chosen_index] if chosen_index is not None and chosen_index < len(candidates) else None
        country = venue.get("audit_country") or venue.get("country")
        row = {"venue_id": int(venue_id), "provider_venue_id": int(venue_id),
               "venue_name": venue.get("name"), "country": country,
               "provider_country": actual_country(venue), "provider_city": venue.get("city"),
               "normalized_venue_name": norm(venue.get("name")), "classification": classification,
               "chosen_result": None if not chosen else chosen.get("display_name"),
               "latitude": None if not chosen else float(chosen["lat"]),
               "longitude": None if not chosen else float(chosen["lon"]),
               "reason": reason, "remaining_ambiguity": remaining,
               "candidate_count": len(candidates), "candidates": candidates}
        rows.append(row)
        totals[country][classification] += 1
    return {
        "scope": "selected provider venues" if selected_ids is not None else "legacy ambiguous venues",
        "totals": {c: dict(v) for c, v in totals.items()}, "venues": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-venues", type=int, default=10)
    parser.add_argument("--spacing", type=float, default=3.0)
    parser.add_argument("--supplement-zero", action="store_true")
    parser.add_argument("--apply-safe", action="store_true")
    parser.add_argument("--checkpoint", type=Path, default=CHECKPOINT)
    parser.add_argument("--candidate-cache", type=Path, default=CANDIDATE_CACHE)
    parser.add_argument("--audit-report", type=Path, default=AUDIT_REPORT)
    parser.add_argument("--cohort-report", type=Path)
    parser.add_argument("--provider-cache-dir", type=Path, default=ROOT / ".cache" / "api-football")
    parser.add_argument("--provider-venue-ids", type=int, nargs="+")
    args = parser.parse_args()
    checkpoint = load_json(args.checkpoint, {})
    catalog = (
        breadth_venue_catalog(args.cohort_report, args.provider_cache_dir)
        if args.cohort_report else venue_catalog()
    )
    cache = load_json(args.candidate_cache, {})
    selected_ids = {str(value) for value in args.provider_venue_ids} if args.provider_venue_ids else None
    if selected_ids:
        missing = sorted(selected_ids - checkpoint.keys(), key=int)
        if missing:
            raise RuntimeError(f"Requested provider venue IDs are absent from checkpoint: {missing}")
    if args.supplement_zero:
        targets = [venue_id for venue_id, result in checkpoint.items()
                   if (selected_ids is None or venue_id in selected_ids)
                   and result.get("status") in {"ambiguous", "unresolved"} and venue_id in cache
                   and not cache[venue_id].get("error") and not cache[venue_id].get("candidates")
                   and not cache[venue_id].get("supplemented")]
    else:
        targets = [venue_id for venue_id, result in checkpoint.items()
                   if (selected_ids is None or venue_id in selected_ids)
                   and result.get("status") in {"ambiguous", "unresolved"} and venue_id not in cache]
    client = Nominatim(user_agent=USER_AGENT)
    last_request = 0.0
    for venue_id in targets[:args.max_venues]:
        wait = args.spacing - (time.monotonic() - last_request)
        if wait > 0:
            time.sleep(wait)
        venue = catalog[venue_id]
        query = compact_query_for(venue) if args.supplement_zero else query_for(venue)
        try:
            locations = client.geocode(query, timeout=20, exactly_one=False, limit=10,
                                       addressdetails=True, namedetails=True, extratags=True) or []
            entry = {"query": query, "error": None, "candidates": [location.raw for location in locations]}
        except Exception as error:
            entry = {"query": query, "error": f"{error.__class__.__name__}: {error}", "candidates": []}
        last_request = time.monotonic()
        if args.supplement_zero:
            prior = cache[venue_id]
            prior.setdefault("attempts", [{"query": prior.get("query"), "error": prior.get("error"),
                                            "candidate_count": len(prior.get("candidates", []))}])
            prior["attempts"].append({"query": query, "error": entry["error"],
                                      "candidate_count": len(entry["candidates"])})
            prior["candidates"] = entry["candidates"]
            prior["error"] = entry["error"]
            prior["supplemented"] = True
            entry = prior
        else:
            cache[venue_id] = entry
        save_json(args.candidate_cache, cache)
        print(json.dumps({"venue_id": int(venue_id), "venue": venue.get("name"),
                          "candidate_count": len(entry["candidates"]), "error": entry["error"]}, ensure_ascii=False), flush=True)
        if entry["error"]:
            break
    report = build_report(checkpoint, catalog, cache, selected_ids)
    if args.apply_safe:
        for row in report["venues"]:
            venue_id = str(row["venue_id"])
            if row["classification"] != "safely_resolved_from_candidates":
                continue
            current = checkpoint.get(venue_id, {})
            if current.get("status") == "geocoded":
                continue
            if current.get("status") != "ambiguous":
                raise RuntimeError(f"Refusing to replace non-ambiguous checkpoint result for {venue_id}")
            checkpoint[venue_id] = {"status": "geocoded", "latitude": row["latitude"],
                                    "longitude": row["longitude"], "queries_attempted": current.get("queries_attempted", 0),
                                    "errors": current.get("errors", []),
                                    "ambiguity_resolution": {"classification": row["classification"],
                                                             "reason": row["reason"],
                                                             "previous_result": current}}
        save_json(args.checkpoint, checkpoint)
    save_json(args.audit_report, report)
    print(json.dumps({"cached": len(cache), "remaining": len(targets) - min(len(targets), args.max_venues),
                      "totals": report["totals"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
