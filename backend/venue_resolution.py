"""Explicit reviewed physical identity. Never infer from provider IDs or names.

One small link projection per Session; no process cache or per-photo queries.
Historical ORM objects must not be modified merely to project canonical identity.
"""
from collections import Counter
from types import SimpleNamespace
from fastapi import HTTPException
from sqlalchemy import text, func, Integer
from models import Venue
from ingestion.venue_identity import CanonicalVenues


class VenueResolution(CanonicalVenues):
    def __init__(self, links):
        try:
            super().__init__(links)
        except ValueError:
            raise HTTPException(409, detail="Ground identity needs review") from None

    def visit(self, visit):
        return SimpleNamespace(visit_id=visit.visit_id, venue_id=self.canonical(visit.venue_id),
                               visit_date=visit.visit_date, fixture=visit.fixture)


def resolution(db):
    if 'venue_resolution' not in db.info:
        rows = db.query(Venue.venue_id, Venue.canonical_venue_id).filter(Venue.canonical_venue_id.is_not(None)).limit(10001).all()
        if len(rows) > 10000:
            raise HTTPException(409, detail="Ground identity needs review")
        db.info['venue_resolution'] = VenueResolution(rows)
    return db.info['venue_resolution']


def resolve_venue(db, venue_id):
    original = db.get(Venue, venue_id)
    if original is None:
        raise HTTPException(404, detail="Venue not found")
    root = resolution(db).canonical(venue_id)
    if db.get(Venue, root) is None:
        raise HTTPException(409, detail="Ground identity needs review")
    return root


def lock_ground(db, venue_id):
    root = resolve_venue(db, venue_id)
    # All equivalent-ID attendance/rating writes share the same lock, including
    # when no existing row can be locked. Held until commit/rollback.
    db.execute(text('SELECT pg_advisory_xact_lock(18261, :venue)'), {'venue': root})
    return root


def unique_owner_reviews(reviews):
    """Exclude ambiguous owners from community aggregates; never choose a winner."""
    counts = Counter(row.user_id for row in reviews)
    return [row for row in reviews if counts[row.user_id] == 1]


def personal_review(reviews):
    if len(reviews) > 1:
        raise HTTPException(409, detail="Your reviews for this ground need review before editing")
    return reviews[0] if reviews else None


def canonical_venues(db, rows):
    """Preserve alias search matches, return root metadata once, without dirtying ORM."""
    identity = resolution(db)
    ids = {identity.canonical(row.venue_id) for row in rows}
    return db.query(Venue).filter(Venue.venue_id.in_(ids)).order_by(Venue.name, Venue.venue_id).all() if ids else []


def community_summaries(db, venue_ids):
    from models import AwayDayReview
    physical = func.coalesce(Venue.canonical_venue_id, Venue.venue_id)
    # Ambiguous historical author/physical-ground pairs are excluded, not merged.
    owners = db.query(physical.label('venue_id'), AwayDayReview.user_id,
                      func.max(AwayDayReview.overall_score).label('score'),
                      func.max(AwayDayReview.recommend.cast(Integer)).label('recommend')).join(
        Venue, Venue.venue_id == AwayDayReview.venue_id).filter(AwayDayReview.venue_id.in_(venue_ids)).group_by(
        physical, AwayDayReview.user_id).having(func.count(AwayDayReview.review_id) == 1).subquery()
    return {venue_id: (average, count, yes, total) for venue_id, average, count, yes, total in db.query(
        owners.c.venue_id, func.avg(owners.c.score), func.count(),
        func.sum(owners.c.recommend), func.count(owners.c.recommend)).group_by(owners.c.venue_id).all()}


def canonical_fixtures(db, rows):
    from models import Fixture
    identity = resolution(db)
    roots = {identity.canonical(row.venue_id) for row in rows if row.venue_id is not None}
    venues = {row.venue_id: row for row in db.query(Venue).filter(Venue.venue_id.in_(roots)).all()} if roots else {}
    return [SimpleNamespace(**{column.name: (identity.canonical(row.venue_id) if column.name == 'venue_id' else getattr(row, column.name))
                               for column in Fixture.__table__.columns}, venue=venues.get(identity.canonical(row.venue_id))) for row in rows]


def canonical_row(db, row):
    values = {column.name: (resolution(db).canonical(row.venue_id) if column.name == 'venue_id' else getattr(row, column.name))
              for column in row.__table__.columns}
    if row.__table__.name == 'club_venues':
        values['team'] = row.team
    return SimpleNamespace(**values)
