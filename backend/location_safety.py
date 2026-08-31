"""Fail-closed predicate for all location-dependent serving paths."""


def has_usable_coordinates(latitude: float | None, longitude: float | None) -> bool:
    return latitude is not None and longitude is not None
