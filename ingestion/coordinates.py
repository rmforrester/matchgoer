"""Generalized version of the original Terrace Talk Nominatim repair ladder."""

import html
import time
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
    candidates = (f"{name}, {address}, {city}, {country}", f"{address}, {city}, {country}", f"{name}, {city}, {country}", f"{name}, {short_city}, {country}", f"{address}, {short_city}, {country}", f"{name}, {country}", name)
    return (query for query in candidates if query.strip(", "))


@dataclass
class CoordinateResult:
    latitude: float | None
    longitude: float | None
    source: str | None
    queries_attempted: int
    ambiguous: bool = False
    errors: tuple[str, ...] = ()


class NominatimCoordinateEnricher:
    def __init__(self, user_agent: str = "terrace-talk-ingestion/1.0", delay_seconds: float = 1.1) -> None:
        self.geolocator, self.delay_seconds = Nominatim(user_agent=user_agent), delay_seconds

    def enrich(self, venue: dict[str, object], strict_uniqueness: bool = False) -> CoordinateResult:
        attempted = 0
        errors: list[str] = []
        for attempted, query in enumerate(query_ladder(venue), start=1):
            try:
                location = self.geolocator.geocode(
                    query,
                    timeout=10,
                    exactly_one=not strict_uniqueness,
                )
            except Exception as error:
                errors.append(f"{error.__class__.__name__}: {error}")
                location = None
            finally:
                time.sleep(self.delay_seconds)
            if strict_uniqueness and isinstance(location, list):
                if len(location) == 1 and valid_coordinates(location[0].latitude, location[0].longitude):
                    return CoordinateResult(location[0].latitude, location[0].longitude, "nominatim", attempted, errors=tuple(errors))
                if len(location) > 1:
                    return CoordinateResult(None, None, None, attempted, ambiguous=True, errors=tuple(errors))
            elif location and valid_coordinates(location.latitude, location.longitude):
                return CoordinateResult(location.latitude, location.longitude, "nominatim", attempted, errors=tuple(errors))
        return CoordinateResult(None, None, None, attempted, errors=tuple(errors))
