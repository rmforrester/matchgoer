"""Explicit opt-in, demand-led event stage for the existing reconciliation job."""
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.matchday_highlights import save_snapshot, project_highlights
from models import Fixture, FixtureEventSnapshot, InterestedFixture, User, VenueVisit


def enrich_batch(db, client, fixture_ids, *, enabled=False, provider_rows=None, fetched_at=None):
    """One bounded existing batch fetch; never commits or changes fixtures."""
    if not enabled:
        raise RuntimeError("Highlights ingestion is disabled pending separate activation approval")
    ids = sorted(set(fixture_ids))
    if not ids or len(ids) > 20 or any(type(i) is not int or i <= 0 for i in ids):
        raise ValueError("Select 1–20 existing fixture IDs")
    eligible = db.query(Fixture).filter(Fixture.fixture_id.in_(ids), Fixture.status == "FT").order_by(Fixture.fixture_id).all()
    if sorted(row.fixture_id for row in eligible) != ids:
        raise ValueError("Only existing, verified FT fixtures may be enriched")
    started = fetched_at or datetime.now(timezone.utc)
    if started.tzinfo is None:
        raise ValueError("fetched_at must be timezone aware")
    stale = [f.fixture_id for f in eligible
             if (snapshot := db.get(FixtureEventSnapshot, f.fixture_id)) is None
             or project_highlights(f, snapshot.payload) is None]
    if not stale:
        return dict.fromkeys(ids, False)
    rows = client.fixtures_by_ids(sorted(stale)) if provider_rows is None else provider_rows
    indexed, seen_ids = {}, set()
    for row in rows:
        key = row.get("fixture", {}).get("id")
        if key not in ids or key in seen_ids:
            raise ValueError("Unexpected or duplicate provider fixture identity")
        seen_ids.add(key)
        if key in stale:
            indexed[key] = row
    return {key: save_snapshot(db, key, indexed[key], started) if key in indexed else False for key in stale} | {key: False for key in ids if key not in stale}


def _utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def select_demand(db, *, now=None, historical=False, retained_ids=(), held_ids=()):
    """Read-only, deduplicated WENT then awaiting-confirmation demand. No inferred visits."""
    now = _utc(now or datetime.now(timezone.utc))
    active = User.account_status.in_(("anonymous", "registered"))
    visits = dict(db.query(VenueVisit.fixture_id, func.max(VenueVisit.created_at))
                  .join(User, User.user_id == VenueVisit.user_id).filter(active, VenueVisit.fixture_id.isnot(None))
                  .group_by(VenueVisit.fixture_id).all())
    attended = select(VenueVisit.visit_id).where(
        VenueVisit.user_id == InterestedFixture.user_id,
        VenueVisit.fixture_id == InterestedFixture.fixture_id).correlate(InterestedFixture).exists()
    saved = dict(db.query(InterestedFixture.fixture_id, func.max(InterestedFixture.created_at))
                 .join(User, User.user_id == InterestedFixture.user_id).filter(active, ~attended)
                 .group_by(InterestedFixture.fixture_id).all())
    ids = set(visits) | set(saved)
    if not ids:
        return []
    retained_ids, held_ids = set(retained_ids), set(held_ids)
    result = []
    for fixture in db.query(Fixture).filter(Fixture.fixture_id.in_(ids)).all():
        keys = (fixture.fixture_id, fixture.league_id, fixture.season, fixture.home_team_id, fixture.away_team_id)
        if (fixture.status != "FT" or fixture.fixture_date is None or _utc(fixture.fixture_date) > now
                or fixture.fixture_id in held_ids or any(type(v) is not int or v <= 0 for v in keys)
                or fixture.home_team_id == fixture.away_team_id
                or any(type(v) is not int or v < 0 for v in (fixture.home_goals, fixture.away_goals))):
            continue
        priority = 0 if fixture.fixture_id in visits else 1
        if priority == 1 and fixture.venue_id is None:
            continue
        snapshot = db.get(FixtureEventSnapshot, fixture.fixture_id)
        if snapshot and project_highlights(fixture, snapshot.payload) is not None:
            continue
        dates = [_utc(fixture.fixture_date)] + [_utc(d[fixture.fixture_id]) for d in (visits, saved)
                                                if d.get(fixture.fixture_id) is not None]
        anchor = max(dates)
        age = (now.date() - anchor.date()).days
        if age < 0:
            continue
        due = age < 7 or (age < 30 and now.weekday() == fixture.fixture_id % 7)
        if historical or fixture.fixture_id in retained_ids or due:
            result.append(dict(fixture_id=fixture.fixture_id, priority=priority,
                               fixture_date=_utc(fixture.fixture_date)))
    return sorted(result, key=lambda r: (r['priority'], r['fixture_date'], r['fixture_id']))


def run_demand_enrichment(engine, client, *, enabled=False, provider_rows=(), held_ids=(),
                          max_requests=750, now=None):
    """Optional post-reconciliation stage; at most TWO extra calls, including quota probe."""
    result = dict(enabled=enabled, inserted_or_updated=[], unavailable=[], errors=[], extra_requests=0)
    if not enabled:
        return result
    now = _utc(now or datetime.now(timezone.utc))
    initial_requests = client.requests_made
    retained = {}
    for row in provider_rows:
        key = row.get('fixture', {}).get('id')
        retained.setdefault(key, []).append(row)
    with Session(engine) as db:
        demand = select_demand(db, now=now, retained_ids=retained, held_ids=held_ids)
    ids = [r['fixture_id'] for r in demand]
    result['selected'] = len(ids)
    result['deferred'] = len(ids)

    def store(batch, rows, fetched):
        try:
            with Session(engine) as db, db.begin():
                if engine.dialect.name == 'postgresql':
                    db.connection().exec_driver_sql("SET LOCAL lock_timeout = '10s'")
                    db.connection().exec_driver_sql("SET LOCAL statement_timeout = '120s'")
                changed = enrich_batch(db, None, batch, enabled=True, provider_rows=rows, fetched_at=fetched)
            result['inserted_or_updated'].extend(k for k in batch if changed[k])
            result['unavailable'].extend(k for k in batch if not changed[k])
            result['deferred'] = len(ids) - len(result['inserted_or_updated']) - len(result['unavailable'])
            return True
        except Exception as error:
            # No provider credentials, SQL parameters or private owner data in job reports.
            result['errors'].append(type(error).__name__)
            return False

    reusable = [i for i in ids if i in retained]
    for start in range(0, len(reusable), 20):
        batch = reusable[start:start + 20]
        if not store(batch, [r for i in batch for r in retained[i]], now):
            return result
    pending = [i for i in ids if i not in retained]

    def room():
        return client.requests_made - initial_requests < 2 and client.requests_made < max_requests

    try:
        if pending and room() and not client.quota_is_fresh():
            client.get('/status', use_cache=False)
        for start in range(0, len(pending), 20):
            if not room() or not client.highlights_quota_available():
                break
            batch = pending[start:start + 20]
            fetched = datetime.now(timezone.utc)
            rows = client.fixtures_by_ids(batch)  # Outside database locks/transactions.
            if not store(batch, rows, fetched):
                break
    except (RuntimeError, ValueError, TypeError) as error:
        result['errors'].append(type(error).__name__)
    finally:
        result['extra_requests'] = client.requests_made - initial_requests
    result['deferred'] = len(ids) - len(result['inserted_or_updated']) - len(result['unavailable'])
    return result
