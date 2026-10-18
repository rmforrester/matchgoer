"""Conservative identity matching for reviewed canonical venue targets."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


class CanonicalVenues:
    """Reviewed direct physical-ID links, shared by ingestion and application.

    This is deliberately separate from name/locality matching below: labels,
    coordinates and provider IDs never create an equivalence.
    """
    def __init__(self, links):
        self.links = {}
        pairs = links.items() if isinstance(links, dict) else links
        for source, target in pairs:
            if type(source) is not int or type(target) is not int or source <= 0 or target <= 0:
                raise ValueError('Invalid reviewed venue equivalence')
            if source in self.links and self.links[source] != target:
                raise ValueError('Conflicting reviewed venue equivalence')
            self.links[source] = target
        if len(self.links) > 10000 or any(source == target or target in self.links for source, target in self.links.items()):
            raise ValueError('Venue equivalence must point directly to a root')
        self.groups = {}
        for source, target in self.links.items():
            self.groups.setdefault(target, set()).add(source)

    def canonical(self, venue_id):
        return self.links.get(venue_id, venue_id)

    def equivalents(self, venue_id):
        root = self.canonical(venue_id)
        return {root} | self.groups.get(root, set())


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
