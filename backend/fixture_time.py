"""Canonical fixture time/status helpers.

Contract: fixtures.fixture_date is a timezone-aware UTC instant in PostgreSQL
(`timestamptz`) and every API response serializes an offset-aware value.
"""

from datetime import datetime, timezone

from sqlalchemy import Date, cast, func


FINISHED_STATUSES = frozenset({"FT", "AET", "PEN"})
LIVE_STATUSES = frozenset({"1H", "HT", "2H", "ET", "BT", "P", "SUSP", "INT", "LIVE"})
POSTPONED_STATUSES = frozenset({"PST"})
CANCELLED_STATUSES = frozenset({"CANC", "ABD", "AWD", "WO"})


def fixture_datetime_utc(value: datetime) -> datetime:
    """Return an aware UTC instant; naive values are rejected as contract drift."""
    if value.tzinfo is None:
        raise ValueError("Fixture datetime is not timezone-aware; run the Phase 5B fixture datetime migration")
    return value.astimezone(timezone.utc)


def fixture_kickoff_has_passed(value: datetime, now: datetime | None = None) -> bool:
    """Classify lifecycle state from the authoritative UTC kickoff instant."""
    current = fixture_datetime_utc(now or datetime.now(timezone.utc))
    return fixture_datetime_utc(value) <= current


def utc_date_expression(column):
    """UTC calendar date for deterministic API date filters."""
    return cast(func.timezone("UTC", column), Date)


def fixture_status_group(status: str | None) -> str:
    normalized = (status or "NS").upper()
    if normalized in FINISHED_STATUSES:
        return "finished"
    if normalized in LIVE_STATUSES:
        return "live"
    if normalized in POSTPONED_STATUSES:
        return "postponed"
    if normalized in CANCELLED_STATUSES:
        return "cancelled"
    return "upcoming"
