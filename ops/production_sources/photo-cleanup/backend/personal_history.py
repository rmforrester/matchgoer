"""Owner-only collection operations using the existing visit records and locks.

A ground_collection row retains an independent ground save without pretending
that the supporter still has an attended matchday. It is never photo attendance.
No shared fixture, ground, club, review or editorial row is changed here.
"""
import hashlib
import json

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert

from models import VenueVisit, InterestedFixture, FixtureMeetingIntent
from venue_resolution import lock_ground, resolution

COLLECTION_SOURCE = "ground_collection"


def lock_owner(db, user_id):
    # Attendance, collection removal and Change Match use one lock order.
    db.execute(text("SELECT pg_advisory_xact_lock(18263, :owner)"), {"owner": user_id})


def independent(visit):
    return visit.source != "fixture_confirmation"


def keep_ground(db, user_id, venue_id):
    equivalents = resolution(db).equivalents(venue_id)
    existing = db.query(VenueVisit).filter(
        VenueVisit.user_id == user_id, VenueVisit.venue_id.in_(equivalents),
        VenueVisit.fixture_id.is_(None), VenueVisit.visit_date.is_(None),
    ).first()
    if existing is None:
        db.execute(insert(VenueVisit).values(
            user_id=user_id, venue_id=venue_id, fixture_id=None,
            visit_date=None, source=COLLECTION_SOURCE,
        ).on_conflict_do_nothing())


def remove_plans(db, user_id, fixture_ids):
    if fixture_ids:
        db.query(FixtureMeetingIntent).filter(
            FixtureMeetingIntent.user_id == user_id,
            FixtureMeetingIntent.fixture_id.in_(fixture_ids),
        ).delete(synchronize_session=False)
        db.query(InterestedFixture).filter(
            InterestedFixture.user_id == user_id,
            InterestedFixture.fixture_id.in_(fixture_ids),
        ).delete(synchronize_session=False)


def remove_matchday(db, user_id, visit_id, *, remove_plan=True):
    lock_owner(db, user_id)
    visit = db.query(VenueVisit).filter_by(user_id=user_id, visit_id=visit_id).first()
    if visit is None or visit.source == COLLECTION_SOURCE:
        return {"visit_id": visit_id, "removed": False}
    venue_id = lock_ground(db, visit.venue_id)
    visit = db.query(VenueVisit).filter_by(user_id=user_id, visit_id=visit_id).with_for_update().populate_existing().first()
    if visit is None:
        return {"visit_id": visit_id, "removed": False}
    preserve = independent(visit)
    fixture_id = visit.fixture_id
    if remove_plan:
        remove_plans(db, user_id, [fixture_id] if fixture_id is not None else [])
    # Existing attendance-removal triggers retire only this visit's photos.
    db.delete(visit)
    db.flush()
    if preserve:
        keep_ground(db, user_id, venue_id)
    return {"visit_id": visit_id, "venue_id": venue_id, "fixture_id": fixture_id,
            "removed": True, "attended": False, "independent_ground_preserved": preserve}


def collection_rows(db, user_id, venue_id, *, locked=False):
    venue_id = lock_ground(db, venue_id) if locked else venue_id
    query = db.query(VenueVisit).filter(
        VenueVisit.user_id == user_id,
        VenueVisit.venue_id.in_(resolution(db).equivalents(venue_id)),
    ).order_by(VenueVisit.visit_id)
    return query.with_for_update().all() if locked else query.all()


def collection_preview(rows):
    values = [(v.visit_id, v.venue_id, v.fixture_id, str(v.visit_date), v.source) for v in rows]
    return {"matchday_count": sum(v.source != COLLECTION_SOURCE for v in rows),
            "revision": hashlib.sha256(json.dumps(values).encode()).hexdigest()}


def remove_ground(db, user_id, venue_id, expected_revision):
    lock_owner(db, user_id)
    rows = collection_rows(db, user_id, venue_id, locked=True)
    preview = collection_preview(rows)
    if not rows:
        return {"venue_id": venue_id, "removed": False, "removed_matchdays": 0}
    if preview["revision"] != expected_revision:
        raise HTTPException(409, "Your matchdays changed. Refresh and confirm Remove Ground again.")
    remove_plans(db, user_id, [v.fixture_id for v in rows if v.fixture_id is not None])
    for visit in rows:
        db.delete(visit)
    db.flush()
    return {"venue_id": venue_id, "removed": True, "removed_matchdays": preview["matchday_count"]}
