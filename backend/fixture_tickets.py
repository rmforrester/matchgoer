from datetime import date
from urllib.parse import urlparse

from club_venue_know import resolve_club_venue

ELIGIBLE_TOPICS = {"official_ticket_portal", "buy online"}

def _fixture_day(fixture) -> date:
    return fixture.fixture_date.date() if fixture.fixture_date is not None else date.today()

def _is_https_url(value: str | None) -> bool:
    if not value:
        return False
    parsed = urlparse(value.strip())
    return parsed.scheme.casefold() == "https" and bool(parsed.netloc)

def resolve_fixture_ticket_action(fixture, relationships, facts):
    """Return one defensible home-fixture ticket action, or fail closed."""
    if fixture.home_team_id is None or fixture.venue_id is None:
        return None
    relationship = resolve_club_venue(
        fixture.home_team_id, fixture.venue_id, relationships, on_date=_fixture_day(fixture)
    )
    if relationship is None:
        return None
    today = date.today()
    eligible = [fact for fact in facts
        if fact.club_venue_id == relationship.club_venue_id
        and fact.venue_id is None
        and fact.section == "tickets_entry"
        and fact.topic.strip().casefold() in ELIGIBLE_TOPICS
        and fact.source_type == "official"
        and fact.status == "current"
        and (fact.expires_at is None or fact.expires_at >= today)
        and (fact.review_after is None or fact.review_after >= today)
        and _is_https_url(fact.source_url)]
    if len(eligible) != 1:
        return None
    fact = eligible[0]
    return {"label": "Buy tickets", "url": fact.source_url.strip(), "source_label": fact.source_label or "Official"}
