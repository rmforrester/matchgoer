"""Fixture-context composition and publication rules for KNOW v1."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Iterable

from club_venue_know import google_maps_search_url, public_supporting_line, publishable_spots

MODULE_ORDER = ("CLUB", "SUPPORTERS", "MATCHDAY", "DONT_MISS", "GOOD_TO_KNOW")
PUBLIC_MODULE_KEYS = {
    "CLUB": "club",
    "SUPPORTERS": "supporters",
    "MATCHDAY": "matchday",
    "DONT_MISS": "dont_miss",
    "GOOD_TO_KNOW": "good_to_know",
}


def accepted_supporting_evidence(fact) -> list:
    return [
        item for item in getattr(fact, "evidence", [])
        if item.review_status == "ACCEPTED" and item.disposition == "SUPPORTS"
    ]


def evidence_policy_satisfied(fact) -> bool:
    """Apply the frozen evidence burden without reducing it to a DB source-count constraint."""
    accepted = accepted_supporting_evidence(fact)
    if fact.claim_sensitivity == "SENSITIVE":
        distinct_sources = {
            (item.source_type, item.source_title.strip().casefold(), (item.source_url or "").strip().casefold())
            for item in accepted
        }
        return len(distinct_sources) >= 2
    return len(accepted) >= 1


def fact_is_publishable(fact, *, today: date | None = None) -> bool:
    day = today or date.today()
    return bool(
        fact.publication_status == "PUBLISHED"
        and fact.confidence in {"HIGH", "MEDIUM"}
        and fact.approved_at is not None
        and bool(fact.approved_by and fact.approved_by.strip())
        and fact.display_order > 0
        and (fact.review_after is None or fact.review_after >= day)
        and (fact.expires_at is None or fact.expires_at >= day)
        and evidence_policy_satisfied(fact)
    )


def fact_matches_context(fact, fixture, relationship) -> bool:
    relationship_id = relationship.club_venue_id if relationship is not None else None
    return bool(
        (fact.team_id is not None and fact.team_id == fixture.home_team_id)
        or (fact.club_venue_id is not None and fact.club_venue_id == relationship_id)
        or (fact.venue_id is not None and fact.venue_id == fixture.venue_id)
        or (fact.fixture_id is not None and fact.fixture_id == fixture.fixture_id)
    )


def _fact_payload(fact) -> dict:
    evidence = sorted(
        accepted_supporting_evidence(fact),
        key=lambda item: (item.source_date or date.min, item.evidence_id or 0),
        reverse=True,
    )
    return {
        "know_fact_id": fact.know_fact_id,
        "headline": fact.headline,
        "content": fact.content,
        "provenance": [
            {
                "source_type": item.source_type,
                "source_title": item.source_title,
                "source_url": item.source_url,
                "source_date": item.source_date,
            }
            for item in evidence
        ],
    }


def compose_fixture_know(fixture, relationship, facts: Iterable, spots: Iterable, *, today: date | None = None) -> dict:
    selected = [
        fact for fact in facts
        if fact_matches_context(fact, fixture, relationship) and fact_is_publishable(fact, today=today)
    ]
    grouped = defaultdict(list)
    for fact in selected:
        grouped[fact.module].append(fact)
    for values in grouped.values():
        values.sort(key=lambda item: (item.display_order, item.know_fact_id or 0))

    # A journey-level collision can span different subject types; fail closed rather than
    # choosing a ritual merely because one owner is more specific.
    dont_miss = grouped["DONT_MISS"] if len(grouped["DONT_MISS"]) == 1 else []
    before_match = publishable_spots(relationship, spots, today=today)
    return {
        "fixture_id": fixture.fixture_id,
        "team_id": fixture.home_team_id,
        "venue_id": fixture.venue_id,
        "club_venue_id": relationship.club_venue_id if relationship is not None else None,
        "club": [_fact_payload(item) for item in grouped["CLUB"]],
        "supporters": [_fact_payload(item) for item in grouped["SUPPORTERS"]],
        "matchday": [_fact_payload(item) for item in grouped["MATCHDAY"]],
        "dont_miss": [_fact_payload(item) for item in dont_miss],
        "before_match": [{
            "pre_match_spot_id": spot.pre_match_spot_id,
            "display_name": spot.display_name,
            "classification": spot.classification,
            "audience": spot.audience,
            "supporting_line": public_supporting_line(spot.supporting_line),
            "location_context": spot.location_context,
            "directions_url": google_maps_search_url(spot.maps_destination),
        } for spot in before_match],
        "good_to_know": [_fact_payload(item) for item in grouped["GOOD_TO_KNOW"]],
    }
