"""Existing matchday_tips storage and existing moderator authority; no new schema."""
from fastapi import HTTPException
from sqlalchemy import func
from models import MatchdayTip, Venue
from venue_resolution import resolution, lock_ground
from terraces import require_moderator

STATES = {'PENDING': ('pending', 'reported'), 'APPROVED': ('active',), 'REJECTED': ('rejected',)}
def state(tip):
    return next((key for key, values in STATES.items() if tip.status in values), 'REJECTED')

def public_payload(tip, viewer=None, venue_id=None):
    return dict(tip_id=tip.tip_id, venue_id=venue_id or tip.venue_id, tip=tip.tip,
        helpful_votes=tip.helpful_votes or 0, report_count=tip.report_count or 0,
        status=tip.status, created_at=tip.created_at,
        can_block_author=viewer is not None and tip.author_user_id is not None and tip.author_user_id != viewer)

def create(db, data, identity):
    venue_id=lock_ground(db,data.venue_id)
    if db.get(Venue,venue_id) is None:raise HTTPException(404,'Ground not found')
    author=identity.user_id if identity else None
    # Ground advisory lock serializes aliases and repeated submissions. Never
    # reclassify an approved/rejected row just because the submit button is retried.
    existing=db.query(MatchdayTip).filter(MatchdayTip.venue_id.in_(resolution(db).equivalents(venue_id)),
        MatchdayTip.author_user_id==author,func.trim(MatchdayTip.tip)==data.tip,
        MatchdayTip.status.in_(('pending','reported','active'))).order_by(MatchdayTip.tip_id).first()
    if existing is not None:return public_payload(existing,author,venue_id)
    tip=MatchdayTip(venue_id=venue_id,tip=data.tip,author_user_id=author,status='pending')
    db.add(tip);db.flush();db.refresh(tip)
    return public_payload(tip,author)

def moderator_payload(db,tip):
    venue=db.get(Venue,resolution(db).canonical(tip.venue_id)) if tip.venue_id is not None else None
    return dict(tip_id=tip.tip_id,venue_id=venue.venue_id if venue else None,venue_name=venue.name if venue else 'Ground not recorded',
        venue_city=venue.city if venue else None,venue_country=venue.country if venue else None,tip=tip.tip,
        category=None,created_at=tip.created_at,status=state(tip))

def queue(db,authorization,status,limit,after):
    require_moderator(db,authorization)
    if status not in STATES:raise HTTPException(422,'Choose a valid review status')
    rows=db.query(MatchdayTip).filter(MatchdayTip.status.in_(STATES[status]),MatchdayTip.tip_id>after).order_by(MatchdayTip.tip_id).limit(limit+1).all()
    return dict(tips=[moderator_payload(db,tip) for tip in rows[:limit]],
        pending_count=db.query(MatchdayTip).filter(MatchdayTip.status.in_(STATES['PENDING'])).count(),
        next_id=rows[limit-1].tip_id if len(rows)>limit else None)

def moderate(db,authorization,tip_id,decision,expected_status):
    require_moderator(db,authorization)
    tip=db.query(MatchdayTip).filter_by(tip_id=tip_id).with_for_update().first()
    if tip is None:raise HTTPException(404,'Tip not found')
    target='APPROVED' if decision=='APPROVE' else 'REJECTED'
    if target=='APPROVED' and (tip.venue_id is None or db.get(Venue,resolution(db).canonical(tip.venue_id)) is None):
        raise HTTPException(409,'Ground identity must be resolved before approval')
    if state(tip)!=target and state(tip)!=expected_status:raise HTTPException(409,'This submission changed. Refresh before deciding again.')
    tip.status=STATES[target][0]
    db.flush()
    return moderator_payload(db,tip)
