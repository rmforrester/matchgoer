"""Pure resolution and publication rules for CLUB_VENUE KNOW."""

from __future__ import annotations

from datetime import date
from typing import Iterable
from urllib.parse import urlencode


def resolve_club_venue(home_team_id: int | None, venue_id: int | None, relationships: Iterable, *, on_date: date | None = None):
    """Return the sole current relationship matching both fixture identities."""
    if home_team_id is None or venue_id is None:
        return None
    day = on_date or date.today()
    matches = [
        item for item in relationships
        if item.team_id == home_team_id
        and item.venue_id == venue_id
        and item.status == "CURRENT"
        and (item.valid_from is None or item.valid_from <= day)
        and (item.valid_until is None or item.valid_until >= day)
    ]
    return matches[0] if len(matches) == 1 else None


def spot_is_publishable(spot, *, today: date | None = None) -> bool:
    day = today or date.today()
    return bool(
        spot.status == "CURRENT"
        and spot.confidence in {"HIGH", "MEDIUM"}
        and spot.business_status in {"OPEN", "NOT_APPLICABLE"}
        and spot.approved_at is not None
        and bool(spot.approved_by and spot.approved_by.strip())
        and 1 <= spot.display_order <= 3
        and (spot.review_after is None or spot.review_after >= day)
    )


def publishable_spots(relationship, spots: Iterable, *, today: date | None = None) -> list:
    if relationship is None or relationship.status != "CURRENT":
        return []
    return sorted(
        (spot for spot in spots if spot.club_venue_id == relationship.club_venue_id and spot_is_publishable(spot, today=today)),
        key=lambda spot: (spot.display_order, spot.pre_match_spot_id or 0),
    )


def google_maps_search_url(destination: str) -> str:
    return "https://www.google.com/maps/search/?" + urlencode({"api": "1", "query": destination})


def guide_facts_for_relationship(venue_id: int, relationship, facts: Iterable) -> list:
    """Coexist physical venue facts with facts owned by the matching relationship."""
    relationship_id = relationship.club_venue_id if relationship is not None else None
    return [
        fact for fact in facts
        if fact.venue_id == venue_id
        or (relationship_id is not None and fact.club_venue_id == relationship_id)
    ]
