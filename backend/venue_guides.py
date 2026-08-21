"""Publication, trust and conflict rules for practical venue-guide facts."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Iterable


SECTION_ORDER = (
    ("getting_there", "Getting there"),
    ("tickets_entry", "Tickets & entry"),
    ("before_match", "Before the match"),
    ("at_ground", "At the ground"),
    ("getting_back", "Getting back"),
)
SECTION_LABELS = dict(SECTION_ORDER)
SOURCE_LABELS = {
    "official": "Official",
    "matchgoer_research": "Researched by Matchgoer",
    "supporter": "Supporter tip",
}
SOURCE_PRIORITY = {"official": 3, "matchgoer_research": 2, "supporter": 1}
PUBLISHABLE_STATUSES = {"current", "needs_review"}


def _freshness(fact, today: date) -> str:
    if fact.status == "needs_review":
        return "needs_review"
    if fact.expires_at is not None and fact.expires_at < today:
        return "expired"
    if fact.review_after is not None and fact.review_after < today:
        return "needs_review"
    return "current"


def _winner_key(fact) -> tuple:
    return (
        SOURCE_PRIORITY[fact.source_type],
        fact.reviewed_at or date.min,
        fact.updated_at or fact.created_at or datetime.min.replace(tzinfo=timezone.utc),
        fact.fact_id or 0,
    )


def build_venue_guide(venue_id: int, facts: Iterable, *, today: date | None = None) -> dict:
    """Return publishable facts grouped for presentation with one winner per topic."""

    current_day = today or date.today()
    candidates = [fact for fact in facts if fact.status in PUBLISHABLE_STATUSES]
    winners = {}
    for fact in candidates:
        key = (fact.section, fact.topic.strip().casefold())
        if key not in winners or _winner_key(fact) > _winner_key(winners[key]):
            winners[key] = fact

    grouped = defaultdict(list)
    has_current = False
    for fact in winners.values():
        freshness = _freshness(fact, current_day)
        has_current = has_current or freshness == "current"
        grouped[fact.section].append({
            "topic": fact.topic,
            "content": fact.content,
            "provenance": {
                "label": SOURCE_LABELS[fact.source_type],
                "source_url": fact.source_url or None,
                "last_checked": fact.reviewed_at,
            },
            "freshness": freshness,
            "_order": (fact.display_order, fact.topic.casefold(), fact.fact_id or 0),
        })

    sections = []
    for key, label in SECTION_ORDER:
        if not grouped[key]:
            continue
        ordered = sorted(grouped[key], key=lambda item: item["_order"])
        for item in ordered:
            item.pop("_order")
        sections.append({"key": key, "label": label, "facts": ordered})
    return {"venue_id": venue_id, "has_current_information": has_current, "sections": sections}
