"""Retry only failed coordinate-audit lookups, without database access or writes."""

from __future__ import annotations

import argparse
import html
import json
import time
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from geopy.exc import GeocoderQuotaExceeded, GeocoderRateLimited, GeocoderServiceError
from geopy.geocoders import Nominatim

from ingestion.coordinates import query_ladder, valid_coordinates
from ingestion.environment import ROOT


CHECKPOINT = ROOT / ".cache" / "nominatim" / "coordinate-dry-run-2026.json"
RETRY_LOG = ROOT / ".cache" / "nominatim" / "coordinate-failed-retry-2026.json"
SOURCE_REPORT = ROOT / "reports" / "ingestion" / "coordinate-dry-run-2026.json"
RETRY_REPORT = ROOT / "reports" / "ingestion" / "coordinate-failed-retry-2026.json"
USER_AGENT = "terrace-talk-ingestion/1.0"


def load_json(path: Path, default: Any) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def save_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def failure_types(errors: list[str]) -> list[str]:
    return sorted({error.split(":", 1)[0] for error in errors})


def venue_catalog() -> dict[str, dict[str, Any]]:
    catalog: dict[str, dict[str, Any]] = {}
    for path in (ROOT / ".cache" / "api-football").glob("*.json"):
        payload = load_json(path, {})
        for item in payload.get("response", []):
            venue = item.get("venue") or (item.get("fixture") or {}).get("venue") or {}
            venue_id = venue.get("id")
            if venue_id is None:
                continue
            team_country = (item.get("team") or {}).get("country")
            current = catalog.setdefault(str(venue_id), dict(venue))
            if team_country:
                current["country"] = team_country

    for league in load_json(SOURCE_REPORT, []):
        for venue in league.get("unresolved_venues", []):
            current = catalog.setdefault(str(venue["venue_id"]), {})
            current.update({key: value for key, value in venue.items() if key != "status" and value is not None})
            current["audit_country"] = league["country"]
    return catalog


def normalized(value: object) -> str:
    text = unicodedata.normalize("NFKD", html.unescape(str(value or "")))
    return " ".join("".join(character for character in text if not unicodedata.combining(character)).casefold().split())


def location_matches_venue(location: Any, venue: dict[str, Any]) -> bool:
    """Reject unique but irrelevant fallbacks such as BMO Field in Arizona."""
    city = normalized(venue.get("city")).split(",", 1)[0]
    address = (getattr(location, "raw", {}) or {}).get("address") or {}
    locality_keys = ("city", "town", "village", "municipality", "borough", "county", "state_district")
    localities = {normalized(address.get(key)) for key in locality_keys if address.get(key)}
    return bool(city and any(city == locality or city in locality.split(",", 1)[0] for locality in localities))


class ConservativeGeocoder:
    def __init__(self, spacing: float, retries: int, backoff: tuple[float, ...]) -> None:
        self.client = Nominatim(user_agent=USER_AGENT)
        self.spacing = spacing
        self.retries = retries
        self.backoff = backoff
        self.last_request = 0.0

    def request(self, query: str) -> tuple[list[Any] | None, list[str], int, bool]:
        errors: list[str] = []
        requests = 0
        for attempt in range(self.retries + 1):
            wait = self.spacing - (time.monotonic() - self.last_request)
            if wait > 0:
                time.sleep(wait)
            try:
                requests += 1
                locations = self.client.geocode(query, timeout=15, exactly_one=False, addressdetails=True)
                self.last_request = time.monotonic()
                return locations or [], errors, requests, False
            except (GeocoderRateLimited, GeocoderQuotaExceeded, GeocoderServiceError, OSError) as error:
                self.last_request = time.monotonic()
                errors.append(f"{error.__class__.__name__}: {error}")
                if attempt < self.retries:
                    time.sleep(self.backoff[min(attempt, len(self.backoff) - 1)])
        return None, errors, requests, True


def retry_venue(geocoder: ConservativeGeocoder, venue: dict[str, Any], unstable_limit: int) -> dict[str, Any]:
    request_count = 0
    errors: list[str] = []
    consecutive_failures = 0
    queries_attempted = 0
    for queries_attempted, query in enumerate(query_ladder(venue), start=1):
        locations, query_errors, made, failed = geocoder.request(query)
        request_count += made
        errors.extend(query_errors)
        if failed:
            consecutive_failures += 1
            if consecutive_failures >= unstable_limit:
                return {"status": "temporary_failure", "latitude": None, "longitude": None,
                        "queries_attempted": queries_attempted, "retry_requests": request_count,
                        "errors": errors, "stop_for_instability": True}
            continue
        consecutive_failures = 0
        if (len(locations) == 1 and valid_coordinates(locations[0].latitude, locations[0].longitude)
                and location_matches_venue(locations[0], venue)):
            return {"status": "geocoded", "latitude": locations[0].latitude,
                    "longitude": locations[0].longitude, "queries_attempted": queries_attempted,
                    "retry_requests": request_count, "errors": errors}
        if len(locations) > 1:
            return {"status": "ambiguous", "latitude": None, "longitude": None,
                    "queries_attempted": queries_attempted, "retry_requests": request_count,
                    "errors": errors}
    status = "temporary_failure" if errors else "unresolved"
    return {"status": status, "latitude": None, "longitude": None,
            "queries_attempted": queries_attempted, "retry_requests": request_count,
            "errors": errors, "stop_for_instability": False}


def build_summary(checkpoint: dict[str, dict], catalog: dict[str, dict], retry_log: dict[str, dict]) -> dict:
    countries: dict[str, Counter] = defaultdict(Counter)
    for venue_id, result in checkpoint.items():
        country = catalog.get(venue_id, {}).get("audit_country") or catalog.get(venue_id, {}).get("country") or ("Sweden" if venue_id == "21411" else "Unknown")
        # The audit's England profile includes Welsh clubs competing in its leagues.
        if country == "Wales":
            country = "England"
        status = result["status"]
        if status == "geocoded":
            countries[country]["unique_geocodes"] += 1
        elif status == "ambiguous":
            countries[country]["ambiguous"] += 1
        elif result.get("errors") or retry_log.get(venue_id, {}).get("retry_result") == "temporary_failure":
            countries[country]["temporary_request_failures"] += 1
        else:
            countries[country]["genuinely_unresolved"] += 1
    return {"total_venues": len(checkpoint), "countries": {key: dict(value) for key, value in countries.items()}}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-venues", type=int, default=10)
    parser.add_argument("--spacing", type=float, default=3.0)
    parser.add_argument("--request-retries", type=int, default=2)
    parser.add_argument("--unstable-query-limit", type=int, default=2)
    args = parser.parse_args()

    checkpoint = load_json(CHECKPOINT, {})
    retry_log = load_json(RETRY_LOG, {})
    catalog = venue_catalog()
    # Early retry versions accepted unique name-only results in the wrong city.
    rejected_legacy_results = {"312": 33.3063159, "11535": 35.2087167}
    repaired = False
    for venue_id, rejected_latitude in rejected_legacy_results.items():
        bad_result = retry_log.get(venue_id)
        if bad_result and bad_result.get("latitude") == rejected_latitude and checkpoint.get(venue_id, {}).get("retry"):
            history = checkpoint[venue_id]["retry"]
            checkpoint[venue_id] = {"status": history["previous_status"], "latitude": None, "longitude": None,
                                    "queries_attempted": 7, "errors": history["previous_errors"]}
            retry_log.pop(venue_id)
            repaired = True
    if repaired:
        save_json(CHECKPOINT, checkpoint)
        save_json(RETRY_LOG, retry_log)
    targets = [venue_id for venue_id, result in checkpoint.items()
               if result.get("status") == "unresolved" and result.get("errors") and venue_id not in retry_log]
    geocoder = ConservativeGeocoder(args.spacing, args.request_retries, (15.0, 45.0))
    processed = 0
    stopped = False
    for venue_id in targets[:args.max_venues]:
        venue = catalog.get(venue_id)
        if not venue or not venue.get("name"):
            raise RuntimeError(f"Missing cached venue metadata for {venue_id}")
        previous = checkpoint[venue_id]
        result = retry_venue(geocoder, venue, args.unstable_query_limit)
        record = {
            "venue_id": int(venue_id), "venue_name": venue["name"],
            "country": venue.get("audit_country") or venue.get("country"),
            "previous_status": previous["status"], "previous_failure_type": failure_types(previous.get("errors", [])),
            "retry_result": result["status"], "retry_requests": result["retry_requests"],
            "latitude": result["latitude"], "longitude": result["longitude"], "errors": result["errors"],
        }
        retry_log[venue_id] = record
        if result["status"] in {"geocoded", "ambiguous", "unresolved"}:
            checkpoint[venue_id] = {
                "status": result["status"], "latitude": result["latitude"], "longitude": result["longitude"],
                "queries_attempted": result["queries_attempted"], "errors": result["errors"],
                "retry": {"previous_status": previous["status"], "previous_errors": previous.get("errors", []),
                          "requests": result["retry_requests"]},
            }
        else:
            checkpoint[venue_id]["retry"] = {"status": "temporary_failure", "errors": result["errors"],
                                                "requests": result["retry_requests"]}
        save_json(CHECKPOINT, checkpoint)
        save_json(RETRY_LOG, retry_log)
        processed += 1
        print(json.dumps(record, ensure_ascii=False), flush=True)
        if result.get("stop_for_instability"):
            stopped = True
            break

    report = {"summary": build_summary(checkpoint, catalog, retry_log),
              "retry_complete": not any(result.get("status") == "unresolved" and result.get("errors") and venue_id not in retry_log
                                        for venue_id, result in checkpoint.items()),
              "stopped_for_connectivity_instability": stopped,
              "retry_results": list(retry_log.values())}
    save_json(RETRY_REPORT, report)
    print(json.dumps({"processed": processed, **report["summary"], "retry_complete": report["retry_complete"],
                      "stopped_for_connectivity_instability": stopped}, ensure_ascii=False, indent=2))
    return 2 if stopped else 0


if __name__ == "__main__":
    raise SystemExit(main())
