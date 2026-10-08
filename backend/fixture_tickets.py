from datetime import date
from urllib.parse import urlparse

from club_venue_know import resolve_club_venue
from official_channels import INFORMATION_STATE, ticket_destination_allowed

ELIGIBLE_TOPICS = {"official_ticket_portal", "buy online"}
V2_ONLINE_SOURCE_STATES = {
    "VERIFIED_DIRECT_PURCHASE_SOURCE",
    "VERIFIED_OFFICIAL_TICKET_NAVIGATION_SOURCE",
    "FIXTURE_SPECIFIC_TICKETING",
}
V2_PHYSICAL_SOURCE_STATES = {
    "PAY_AT_GATE_OR_OFFLINE_SOURCE",
    "NO_ONLINE_SALES",
}

def _fixture_day(fixture) -> date:
    return fixture.fixture_date.date() if fixture.fixture_date is not None else date.today()

def _is_https_url(value: str | None) -> bool:
    if not value:
        return False
    parsed = urlparse(value.strip())
    return parsed.scheme.casefold() == "https" and bool(parsed.netloc)

def _valid_relationships(fixture, relationships):
    if fixture.home_team_id is None or fixture.venue_id is None:
        return []
    day = _fixture_day(fixture)
    return [item for item in relationships
        if item.team_id == fixture.home_team_id
        and item.venue_id == fixture.venue_id
        and item.status == "CURRENT"
        and (item.valid_from is None or item.valid_from <= day)
        and (item.valid_until is None or item.valid_until >= day)]

def _resolve_v2_sources(scoped):
    active_primary = [source for source in scoped
        if source.source_role == "PRIMARY" and source.operational_status == "ACTIVE"]
    if len(active_primary) != 1:
        return {"action": None, "guidance": None, "serving": "V2_FAIL_CLOSED"}
    source = active_primary[0]
    if (source.source_state in V2_ONLINE_SOURCE_STATES
            and source.ticketing_model in {"ONLINE_DIRECT", "ONLINE_NAVIGATION", "FIXTURE_SPECIFIC"}
            and ticket_destination_allowed(source)):
        return {
            "action": {
                "label": "Buy tickets",
                "url": source.source_url.strip(),
                "source_label": source.source_label or "Official",
            },
            "guidance": None,
            "serving": "V2",
        }
    if (source.source_state == INFORMATION_STATE
            and source.ticketing_model == "OFFICIAL_INFORMATION"
            and ticket_destination_allowed(source)):
        return {
            "action": {"label": "Ticket info", "url": source.source_url,
                       "source_label": source.source_label or "Official"},
            "guidance": None, "serving": "V2",
        }
    if (source.source_state in V2_PHYSICAL_SOURCE_STATES
            and source.ticketing_model in {"PAY_AT_GATE", "OFFLINE"}
            and source.source_label and source.source_label.strip()):
        return {
            "action": None,
            "guidance": {
                "label": "Tickets",
                "message": source.source_label.strip(),
                "source_label": source.source_label.strip(),
            },
            "serving": "V2",
        }
    return {"action": None, "guidance": None, "serving": "V2_FAIL_CLOSED"}

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


def resolve_fixture_ticket_presentation(fixture, relationships, facts, ticket_sources):
    """Resolve V2 first and retain the legacy CTA only when no V2 source exists.

    A present but unsafe or ambiguous V2 source fails closed. This prevents a
    held/stale V2 record from falling through to a less precise legacy fact.
    """
    if fixture.home_team_id is None:
        return {"action": None, "guidance": None, "serving": "NONE"}
    valid_relationships = _valid_relationships(fixture, relationships)
    relationship = resolve_club_venue(
        fixture.home_team_id, fixture.venue_id, relationships, on_date=_fixture_day(fixture)
    ) if fixture.venue_id is not None else None
    relationship_ids = {item.club_venue_id for item in valid_relationships}
    relationship_scoped = [source for source in ticket_sources
        if getattr(source, "club_venue_id", None) in relationship_ids]
    if relationship_scoped:
        if relationship is None:
            return {"action": None, "guidance": None, "serving": "V2_FAIL_CLOSED"}
        scoped = [source for source in relationship_scoped
            if source.club_venue_id == relationship.club_venue_id]
        return _resolve_v2_sources(scoped)

    team_scoped = [source for source in ticket_sources
        if getattr(source, "team_id", None) == fixture.home_team_id]
    if team_scoped:
        return _resolve_v2_sources(team_scoped)

    return {
        "action": resolve_fixture_ticket_action(fixture, relationships, facts),
        "guidance": None,
        "serving": "LEGACY",
    }
