"""Read-only IANA timezone projection from canonical physical-venue coordinates."""
from functools import lru_cache
import logging
from math import isfinite
from threading import Lock
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from timezonefinder import TimezoneFinder

_log = logging.getLogger(__name__)
_lock = Lock()
_finder = None


@lru_cache(maxsize=4096)
def _coordinate_timezone(latitude: float, longitude: float) -> str | None:
    global _finder
    try:
        # One disk-backed resolver; serialize access to its shared data readers.
        with _lock:
            if _finder is None:
                _finder = TimezoneFinder(in_memory=False)
            certain = _finder.certain_timezone_at(lat=latitude, lng=longitude)
            zones = set(_finder.timezones_at(lat=latitude, lng=longitude))
        if not certain or certain.startswith("Etc/") or zones != {certain}:
            return None
        ZoneInfo(certain)  # Reject names unavailable to the runtime's IANA database.
        return certain
    except (OSError, ValueError, ZoneInfoNotFoundError):
        _log.warning("Venue timezone unavailable; ticket action will remain hidden")
        return None


def venue_timezone(venue) -> str | None:
    if venue is None:
        return None
    latitude, longitude = getattr(venue, "latitude", None), getattr(venue, "longitude", None)
    # No country, kickoff offset, home-club or supporter-timezone inference.
    if isinstance(latitude, bool) or isinstance(longitude, bool):
        return None
    if not isinstance(latitude, (int, float)) or not isinstance(longitude, (int, float)):
        return None
    if not isfinite(latitude) or not isfinite(longitude) or not (-90 < latitude < 90 and -180 <= longitude <= 180):
        return None
    return _coordinate_timezone(float(latitude), float(longitude))
