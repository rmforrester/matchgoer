"""Generalized version of the original Terrace Talk Nominatim repair ladder."""

import html
import math
import re
import time
import unicodedata
from dataclasses import dataclass
from typing import Iterable

from geopy.geocoders import Nominatim


def clean_text(value: object) -> str:
    return "" if value is None else " ".join(html.unescape(str(value)).replace("&apos;", "'").split())


def valid_coordinates(latitude: object, longitude: object) -> bool:
    try:
        lat, lon = float(latitude), float(longitude)
    except (TypeError, ValueError):
        return False
    return -90 <= lat <= 90 and -180 <= lon <= 180


def query_ladder(venue: dict[str, object]) -> Iterable[str]:
    name, address, city, country = (clean_text(venue.get(key)) for key in ("name", "address", "city", "country"))
    short_city = city.split(",")[0].strip()
    literal_tokens = {
        token for token in normalize_identity(name).split()
        if token not in GENERIC_VENUE_WORDS and len(token) >= 4
    }
    distinctive = sorted(literal_tokens | identity_tokens(name), key=lambda token: (-len(token), token))[:4]
    candidates = (
        f"{name}, {address}, {city}, {country}", f"{address}, {city}, {country}",
        f"{name}, {city}, {country}", f"{name}, {short_city}, {country}",
        *(f"{token}, {short_city}, {country}" for token in distinctive),
        f"{address}, {short_city}, {country}", f"{name}, {country}", name,
    )
    return iter(dict.fromkeys(query for query in candidates if query.strip(", ")))


@dataclass
class CoordinateResult:
    latitude: float | None
    longitude: float | None
    source: str | None
    queries_attempted: int
    ambiguous: bool = False
    errors: tuple[str, ...] = ()
    matched_label: str | None = None
    osm_type: str | None = None
    osm_id: int | None = None
    acceptance_reason: str | None = None


GENERIC_VENUE_WORDS = {
    "arena", "camp", "complex", "football", "futbol", "gipedo", "ground",
    "municipal", "olympic", "park", "pitch", "sport", "sports", "sportiv",
    "stadion", "stadionu", "stadionas", "stadions", "stadium", "stadio",
}
PHYSICAL_TYPES = {"stadium", "pitch", "sports_centre", "track"}
LOCALITY_FIELDS = ("city", "town", "village", "municipality", "borough", "suburb", "county", "state_district")
NAME_FIELDS = ("name", "name:en", "int_name", "official_name", "short_name", "alt_name", "old_name")
COUNTRY_CODES = {
    "albania": "al", "andorra": "ad", "armenia": "am", "austria": "at",
    "azerbaijan": "az", "belarus": "by", "belgium": "be", "bulgaria": "bg",
    "cyprus": "cy", "denmark": "dk", "england": "gb", "estonia": "ee",
    "faroe islands": "fo", "finland": "fi", "france": "fr", "georgia": "ge",
    "germany": "de", "greece": "gr", "hungary": "hu", "iceland": "is",
    "israel": "il", "italy": "it", "kazakhstan": "kz", "kosovo": "xk",
    "latvia": "lv", "lithuania": "lt", "luxembourg": "lu", "malta": "mt",
    "moldova": "md", "montenegro": "me", "netherlands": "nl", "norway": "no",
    "poland": "pl", "portugal": "pt", "romania": "ro", "russia": "ru",
    "san marino": "sm", "scotland": "gb", "serbia": "rs", "slovakia": "sk",
    "slovenia": "si", "spain": "es", "sweden": "se", "switzerland": "ch",
    "ukraine": "ua", "usa": "us", "wales": "gb",
}


def normalize_identity(value: object) -> str:
    text = unicodedata.normalize("NFKD", clean_text(value).casefold())
    text = "".join(character for character in text if not unicodedata.combining(character))
    return " ".join(re.findall(r"[a-z0-9]+", text))


def identity_tokens(value: object) -> set[str]:
    tokens = set()
    for token in normalize_identity(value).split():
        if token in GENERIC_VENUE_WORDS:
            continue
        if len(token) > 5 and token.endswith("s"):
            token = token[:-1]
        if len(token) >= 7 and token.endswith("iou"):
            token = token[:-3] + "y"
        if len(token) >= 5 and token.endswith("i"):
            token = token[:-1] + "y"
        tokens.add(token)
    return tokens


def candidate_names(raw: dict) -> list[str]:
    details = raw.get("namedetails") or {}
    values: list[str] = []
    for key, value in details.items():
        if key in NAME_FIELDS or key.startswith(("name:", "alt_name:", "old_name:")):
            values.extend(str(value).split(";") if value else [])
    display_name = raw.get("display_name")
    if display_name:
        values.append(str(display_name).split(",", 1)[0])
    return list(dict.fromkeys(clean_text(value) for value in values if clean_text(value)))


def is_physical_venue(raw: dict) -> bool:
    category, kind = raw.get("category") or raw.get("class"), raw.get("type")
    if category == "leisure" and kind in PHYSICAL_TYPES:
        return True
    return category == "building" and kind == "stadium"


def country_compatible(venue: dict[str, object], raw: dict) -> bool:
    address = raw.get("address") or {}
    expected = normalize_identity(venue.get("country"))
    actual = normalize_identity(address.get("country"))
    country_code = normalize_identity(address.get("country_code"))
    if not actual and not country_code:
        return False
    return actual == expected or country_code == COUNTRY_CODES.get(expected)


def locality_compatible(venue: dict[str, object], raw: dict, *, strong_identity: bool, query_has_locality: bool) -> bool:
    expected = identity_tokens(clean_text(venue.get("city")).split(",", 1)[0])
    address = raw.get("address") or {}
    actual = set().union(*(identity_tokens(address.get(field)) for field in LOCALITY_FIELDS))
    if expected and actual and expected & actual:
        return True
    provider_address = identity_tokens(venue.get("address"))
    candidate_address = set().union(*(identity_tokens(value) for value in address.values()))
    # Exact identity plus a distinctive shared address token supports an adjacent metro municipality.
    return strong_identity and query_has_locality and (
        not provider_address or any(
            token in candidate_address and len(token) >= 4 for token in provider_address
        ) or not any(identity_tokens(address.get(field)) for field in ("road", "house_number"))
    )


def identity_evidence(venue: dict[str, object], raw: dict) -> tuple[bool, bool, str | None]:
    provider = normalize_identity(venue.get("name"))
    provider_tokens = identity_tokens(venue.get("name"))
    for label in candidate_names(raw):
        candidate = normalize_identity(label)
        tokens = identity_tokens(label)
        exact = bool(provider and candidate and provider == candidate)
        conservative = bool(
            provider_tokens and tokens and (provider_tokens == tokens or (
                (provider_tokens <= tokens or tokens <= provider_tokens)
                and any(len(token) >= 4 for token in provider_tokens & tokens)
            ))
        )
        if exact or conservative:
            # Equal distinctive token sets are strong structured-name evidence
            # even when language changes generic-word order (for example,
            # "Stadion X" versus "X Stadium").
            return True, exact or provider_tokens == tokens, label
    return False, False, None


def same_physical_object(left, right) -> bool:
    if left["osm_key"] == right["osm_key"]:
        return True
    lat1, lon1, lat2, lon2 = left["location"].latitude, left["location"].longitude, right["location"].latitude, right["location"].longitude
    distance = math.hypot((lat1 - lat2) * 111_000, (lon1 - lon2) * 75_000)
    return distance <= 150


class NominatimCoordinateEnricher:
    def __init__(self, user_agent: str = "terrace-talk-ingestion/1.0", delay_seconds: float = 1.1) -> None:
        self.geolocator, self.delay_seconds = Nominatim(user_agent=user_agent), delay_seconds

    def enrich(self, venue: dict[str, object], strict_uniqueness: bool = False) -> CoordinateResult:
        attempted = 0
        errors: list[str] = []
        supported: list[dict] = []
        for attempted, query in enumerate(query_ladder(venue), start=1):
            try:
                location = self.geolocator.geocode(
                    query,
                    timeout=10,
                    exactly_one=False,
                    addressdetails=True,
                    namedetails=True,
                    extratags=True,
                    language="en",
                )
            except Exception as error:
                errors.append(f"{error.__class__.__name__}: {error}")
                location = None
            finally:
                time.sleep(self.delay_seconds)
            locations = location if isinstance(location, list) else [location] if location else []
            for candidate in locations:
                raw = candidate.raw or {}
                if not valid_coordinates(candidate.latitude, candidate.longitude) or not is_physical_venue(raw):
                    continue
                if not country_compatible(venue, raw):
                    continue
                matched, exact, label = identity_evidence(venue, raw)
                short_city = normalize_identity(clean_text(venue.get("city")).split(",", 1)[0])
                geographic = locality_compatible(
                    venue, raw, strong_identity=exact,
                    query_has_locality=bool(short_city and short_city in normalize_identity(query)),
                )
                item = {
                    "location": candidate,
                    "raw": raw,
                    "osm_key": (raw.get("osm_type"), raw.get("osm_id")),
                    "label": label,
                    "exact": exact,
                }
                if matched and geographic:
                    supported.append(item)

        clusters: list[list[dict]] = []
        for item in supported:
            for cluster in clusters:
                if same_physical_object(item, cluster[0]):
                    cluster.append(item)
                    break
            else:
                clusters.append([item])
        if len(clusters) == 1:
            chosen = sorted(clusters[0], key=lambda item: (not item["exact"], item["raw"].get("category") != "leisure"))[0]
            raw, location = chosen["raw"], chosen["location"]
            return CoordinateResult(
                location.latitude, location.longitude, "nominatim", attempted,
                errors=tuple(errors), matched_label=chosen["label"],
                osm_type=raw.get("osm_type"), osm_id=raw.get("osm_id"),
                acceptance_reason="structured_venue_identity_and_geography",
            )
        return CoordinateResult(
            None, None, None, attempted,
            ambiguous=len(clusters) > 1,
            errors=tuple(errors),
        )
