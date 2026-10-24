"""Explicit opt-in enrichment building block. Not wired to a scheduler or CLI."""
from datetime import datetime, timedelta, timezone

from backend.matchday_highlights import save_snapshot, project_highlights
from models import Fixture, FixtureEventSnapshot


def enrich_batch(db, client, fixture_ids, *, enabled=False):
    """One bounded existing batch fetch; never commits or changes fixtures."""
    if not enabled:
        raise RuntimeError("Highlights ingestion is disabled pending separate activation approval")
    ids = sorted(set(fixture_ids))
    if not ids or len(ids) > 20 or any(type(i) is not int or i <= 0 for i in ids):
        raise ValueError("Select 1–20 existing fixture IDs")
    eligible = db.query(Fixture).filter(Fixture.fixture_id.in_(ids), Fixture.status == "FT").all()
    if sorted(row.fixture_id for row in eligible) != ids:
        raise ValueError("Only existing, verified FT fixtures may be enriched")
    started = datetime.now(timezone.utc)
    stale = []
    for fixture in eligible:
        snapshot = db.get(FixtureEventSnapshot, fixture.fixture_id)
        fetched = snapshot.fetched_at if snapshot else None
        if fetched is not None and fetched.tzinfo is None:
            fetched = fetched.replace(tzinfo=timezone.utc)
        if not snapshot or not (started - timedelta(hours=24) <= fetched <= started) or project_highlights(fixture, snapshot.payload) is None:
            stale.append(fixture.fixture_id)
    if not stale:
        return dict.fromkeys(ids, False)
    rows = client.fixtures_by_ids(sorted(stale))
    indexed = {}
    for row in rows:
        key = row.get("fixture", {}).get("id")
        if key not in stale or key in indexed:
            raise ValueError("Unexpected or duplicate provider fixture identity")
        indexed[key] = row
    return {key: save_snapshot(db, key, indexed[key], started) if key in indexed else False for key in ids}
