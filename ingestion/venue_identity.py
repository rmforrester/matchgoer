"""Conservative identity matching for reviewed canonical venue targets."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


_US_REGIONS = {
    "va": "virginia",
    "mo": "missouri",
    "pa": "pennsylvania",
    "ny": "new york",
    "ca": "california",
    "ct": "connecticut",
    "dc": "district of columbia",
    "fl": "florida",
    "md": "maryland",
    "or": "oregon",
    "tx": "texas",
    "wa": "washington",
    "wi": "wisconsin",
}


def normalize_identity(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char)).casefold()
    text = re.sub(r"\bst[.]?\b", "saint", text)
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def normalize_region(value: object) -> str:
    normalized = normalize_identity(value)
    return _US_REGIONS.get(normalized, normalized)


@dataclass(frozen=True)
class VenueIdentity:
    name: str
    city: str = ""
    region: str = ""
    country: str = ""

    @classmethod
    def from_values(
        cls, *, name: object, city: object = "", region: object = "", country: object = ""
    ) -> "VenueIdentity":
        city_text = str(city or "").strip()
        region_text = str(region or "").strip()
        if not region_text and "," in city_text:
            city_text, region_text = (part.strip() for part in city_text.split(",", 1))
        return cls(
            name=normalize_identity(name),
            city=normalize_identity(city_text),
            region=normalize_region(region_text),
            country=normalize_identity(country),
        )

    @property
    def key(self) -> tuple[str, str, str, str]:
        return self.name, self.city, self.region, self.country


def locality_compatible(proposed: VenueIdentity, existing: VenueIdentity) -> bool:
    """Return whether available geographic context safely permits canonical reuse.

    A proposal with a known city cannot reuse a same-name canonical whose city is
    blank: its more specific identity has not been established. A proposal with no
    city may retain historical name-based reuse when no available country/region
    evidence conflicts. This preserves incomplete legacy inputs without allowing a
    known cross-city proposal to collapse into an underspecified canonical.
    """
    if proposed.country and existing.country and proposed.country != existing.country:
        return False
    if proposed.region and existing.region and proposed.region != existing.region:
        return False
    if proposed.city and not existing.city:
        return False
    if proposed.city and existing.city and proposed.city != existing.city:
        return False
    return True


def canonical_reuse_permitted(proposed: VenueIdentity, existing: VenueIdentity) -> bool:
    return proposed.name == existing.name and locality_compatible(proposed, existing)
