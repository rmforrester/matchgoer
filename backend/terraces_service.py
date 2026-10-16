"""Photo lifecycle on existing Phase A tables. This service owns its commits."""
import base64
import json
from datetime import datetime,timedelta,timezone
from fastapi import HTTPException
from sqlalchemy import exists,and_,or_,select,func
from models import TerracePhoto as Photo,TerracePhotoEvent as Event,VenueVisit,Fixture,UserProfile,Venue
from terraces import require_verified_account,require_photo_submitter,require_moderator,configured_moderator_user_id,reserve_photo,may_read_photo,CONSENT_VERSION
from terraces_storage import StorageUnavailable

def now():return datetime.now(timezone.utc)
def event(db,photo,kind,actor=None,payload=None,completed=False):
    row=Event(photo_id=photo.photo_id if photo else None,actor_user_id=actor.user_id if actor else None,event_type=kind,payload=payload or {},completed_at=now() if completed else None)
    db.add(row);return row
def ready_clause():
    return exists(select(Event.event_id).where(Event.photo_id==Photo.photo_id,Event.event_type=='STORAGE_READY',Event.completed_at.is_not(None)))
def ready(db,photo):
    return db.query(Event.event_id).filter(Event.photo_id==photo.photo_id,Event.event_type=='STORAGE_READY',Event.completed_at.is_not(None)).first() is not None
def lock(db,photo_id):
    row=db.query(Photo).filter_by(photo_id=photo_id).with_for_update().populate_existing().first()
    if not row:raise HTTPException(404,'Photograph not found')
    return row
def status(row):return {'photo_id':row.photo_id,'status':row.status}

def submit(db,storage,authorization,visit_id,processed,metadata,key):
    actor=require_photo_submitter(db,authorization)
    row=reserve_photo(db,authorization,visit_id=visit_id,photo=processed,submission_key=key,
                      caption=metadata.get('caption'),consent_version=metadata['consent_version'],
                      public_consent=metadata['public_consent'],rights_acknowledged=metadata['rights_acknowledged'])
    identifier=row.photo_id
    # Commit a durable canonical reservation BEFORE any external object write.
    db.commit()
    row=lock(db,identifier)
    if row.status in ('REJECTED','REMOVED') or row.storage_deleted_at is not None:
        raise HTTPException(409,'This submission cannot be uploaded again')
    if ready(db,row):return status(row)
    try:
        storage.put(row.display_key,processed.display.data)
        storage.put(row.thumbnail_key,processed.thumbnail.data)
        event(db,row,'STORAGE_READY',actor,completed=True)
        # Publication and readiness commit together; identity is resolved server-side.
        if actor.user_id == configured_moderator_user_id() and row.owner_user_id == actor.user_id and row.status == 'PENDING' and not row.dispute_reason:
            row.status='APPROVED';row.approved_at=now();row.published_at=row.approved_at
            event(db,row,'MODERATOR_APPROVED',actor,{'method':'automatic','reason':'moderator_submission'},completed=True)
        db.commit()
        return status(row)
    except StorageUnavailable:
        event(db,row,'UPLOAD_CLEANUP_REQUIRED',actor,{'display_key':row.display_key,'thumbnail_key':row.thumbnail_key})
        db.commit()
        # Best effort is not reported as success. Durable row/event survives a
        # crash or commit uncertainty and is available to the cleanup executor.
        try:cleanup_upload(db,storage,identifier)
        except StorageUnavailable:db.rollback()
        raise HTTPException(503,'Photo upload did not finish. Retry with the same submission key.') from None

def cleanup_upload(db,storage,photo_id):
    row=lock(db,photo_id)
    pending=db.query(Event).filter(Event.photo_id==photo_id,Event.event_type=='UPLOAD_CLEANUP_REQUIRED',Event.completed_at.is_(None)).all()
    if not pending:return False
    if ready(db,row) or row.dispute_reason:
        if ready(db,row):
            for item in pending:item.completed_at=now()
            db.commit()
        return False
    storage.delete(row.display_key);storage.delete(row.thumbnail_key)
    for item in pending:item.completed_at=now()
    event(db,row,'UPLOAD_CLEANED',completed=True);db.commit();return True

def approve(db,authorization,photo_id):
    actor=require_moderator(db,authorization);row=lock(db,photo_id)
    if row.status=='APPROVED':return status(row)
    if row.status!='PENDING' or not ready(db,row) or row.storage_deleted_at is not None:
        raise HTTPException(409,'Only a complete pending photograph can be approved')
    row.status='APPROVED';row.approved_at=now();row.published_at=row.approved_at
    event(db,row,'MODERATOR_APPROVED',actor,completed=True);db.commit();return status(row)

def reject(db,authorization,photo_id,reason):
    actor=require_moderator(db,authorization);row=lock(db,photo_id)
    if row.status=='REJECTED':return status(row)
    if row.status!='PENDING':raise HTTPException(409,'Only pending photographs can be rejected')
    row.status='REJECTED';row.rejected_at=now();row.published_at=None
    event(db,row,'MODERATOR_REJECTED',actor,{'reason':reason},completed=True);db.commit();return status(row)

def purge_photo(db,storage,photo_id,at=None):
    at=at or now();row=lock(db,photo_id)
    if row.storage_deleted_at or row.dispute_reason:return False
    if row.status!='REMOVED' and not (row.status=='REJECTED' and row.rejected_at<=at-timedelta(days=7)):return False
    storage.delete(row.display_key);storage.delete(row.thumbnail_key)
    row.storage_deleted_at=at;event(db,row,'STORAGE_DELETED',completed=True);db.commit();return True

def remove(db,storage,authorization,photo_id,*,moderator=False):
    actor=require_moderator(db,authorization) if moderator else require_verified_account(db,authorization)
    row=lock(db,photo_id)
    if not moderator and row.owner_user_id!=actor.user_id:raise HTTPException(404,'Photograph not found')
    if row.status!='REMOVED':
        row.status='REMOVED';row.removed_at=now();row.published_at=None
        event(db,row,'REMOVAL_REQUESTED',actor,completed=True);db.commit()
    try:purge_photo(db,storage,photo_id)
    except StorageUnavailable:db.rollback()
    row=db.get(Photo,photo_id)
    return {**status(row),'public_visibility':'removed','physical_cleanup':'complete' if row.storage_deleted_at else 'pending'}

def report(db,authorization,photo_id,reason):
    actor=require_verified_account(db,authorization);row=lock(db,photo_id)
    if row.status!='APPROVED' or not row.published_at or row.storage_deleted_at or not ready(db,row):
        raise HTTPException(404,'Published photograph not found')
    prior=db.query(Event).filter_by(photo_id=photo_id,actor_user_id=actor.user_id,event_type='PHOTO_REPORTED').filter(Event.completed_at.is_(None)).first()
    if prior:return {'report_id':prior.event_id,'status':'pending'}
    item=event(db,row,'PHOTO_REPORTED',actor,{'reason':reason});db.flush();identifier=item.event_id;db.commit()
    return {'report_id':identifier,'status':'pending'}

def resolve_report(db,authorization,event_id,note):
    actor=require_moderator(db,authorization)
    row=db.query(Event).filter_by(event_id=event_id,event_type='PHOTO_REPORTED').with_for_update().first()
    if not row:raise HTTPException(404,'Report not found')
    if row.completed_at is None:
        row.completed_at=now();event(db,db.get(Photo,row.photo_id) if row.photo_id else None,'REPORT_RESOLVED',actor,{'report_id':event_id,'note':note},completed=True);db.commit()
    return {'report_id':event_id,'status':'resolved'}

def hold(db,authorization,photo_id,reason):
    actor=require_moderator(db,authorization);row=lock(db,photo_id)
    row.dispute_reason=reason
    event(db,row,'HOLD_CHANGED',actor,{'held':bool(reason)},completed=True);db.commit();return {'held':bool(reason)}

def cleanup(db,storage,*,limit=50,at=None):
    """Existing maintenance/manual command invokes this; no new scheduler."""
    at=at or now();done=0;pending=0
    ids=[x[0] for x in db.query(Photo.photo_id).filter(Photo.storage_deleted_at.is_(None),Photo.dispute_reason.is_(None),or_(Photo.status=='REMOVED',and_(Photo.status=='REJECTED',Photo.rejected_at<=at-timedelta(days=7)))).order_by(Photo.photo_id).limit(limit).all()]
    for identifier in ids:
        try:done+=bool(purge_photo(db,storage,identifier,at))
        except StorageUnavailable:db.rollback();pending+=1
    # Account cascades preserve key-only receipts, including hold status added
    # by the B1 trigger migration. Unknown legacy hold state fails closed.
    ids=[x[0] for x in db.query(Event.event_id).filter_by(event_type='STORAGE_DELETE_REQUIRED').filter(Event.completed_at.is_(None),Event.payload['legal_hold'].as_boolean()==False).order_by(Event.event_id).limit(limit).all()]
    for identifier in ids:
        row=db.query(Event).filter_by(event_id=identifier).with_for_update().first()
        if row.payload.get('legal_hold') is not False:continue
        try:
            storage.delete(row.payload['display_key']);storage.delete(row.payload['thumbnail_key'])
            row.completed_at=at;db.commit();done+=1
        except StorageUnavailable:db.rollback();pending+=1
    ids=[x[0] for x in db.query(Photo.photo_id).filter(Photo.status=='PENDING',Photo.dispute_reason.is_(None),Photo.submitted_at<=at-timedelta(minutes=5),~ready_clause()).order_by(Photo.photo_id).limit(limit).all()]
    for identifier in ids:
        row=lock(db,identifier)
        if not ready(db,row) and not row.dispute_reason:
            event(db,row,'UPLOAD_CLEANUP_REQUIRED',payload={'display_key':row.display_key,'thumbnail_key':row.thumbnail_key});db.commit()
            try:done+=bool(cleanup_upload(db,storage,identifier))
            except StorageUnavailable:db.rollback();pending+=1
    return {'cleaned':done,'retry_pending':pending}

def photo_payload(db,storage,row,*,private=False):
    profile=db.get(UserProfile,row.owner_user_id)
    fixture=db.get(Fixture,row.fixture_id) if row.fixture_id else None
    visit=db.get(VenueVisit,row.visit_id) if row.visit_id else None
    venue=db.get(Venue,row.venue_id)
    result={'photo_id':row.photo_id,'venue_id':row.venue_id,'venue_name':venue.name if venue else None,'fixture_id':row.fixture_id,'caption':row.caption,
            'display_name':profile.display_name if profile else 'Matchgoer','published_at':row.published_at,
            'match_date':fixture.fixture_date if fixture else visit.visit_date if visit else None,
            'home_team':fixture.home_team if fixture else None,'away_team':fixture.away_team if fixture else None}
    if private:result.update(status=row.status,submitted_at=row.submitted_at,held=bool(row.dispute_reason),upload_state='ready' if ready(db,row) else 'incomplete')
    if ready(db,row) and row.storage_deleted_at is None and row.status!='REMOVED':
        try:
            display=storage.signed(row.display_key);thumbnail=storage.signed(row.thumbnail_key)
            result.update(image_url=display,thumbnail_url=thumbnail,expires_in=90,image_state='available')
        except StorageUnavailable:
            # A failed image delivery must not erase confirmed list/status metadata.
            result.update(image_state='unavailable')
    return result

def public_photo_query(db):
    # One eligibility predicate for lists and matchday counts.
    return db.query(Photo).filter(Photo.status=='APPROVED',Photo.approved_at.is_not(None),Photo.published_at.is_not(None),Photo.storage_deleted_at.is_(None),Photo.dispute_reason.is_(None),ready_clause())


def public_matchday_metadata(db,row):
    query=public_photo_query(db).filter(Photo.venue_id==row.venue_id)
    if row.fixture_id is not None:
        query=query.filter(Photo.fixture_id==row.fixture_id)
    elif row.visit_id is not None:
        # A recorded visit is a reliable shared identity; never infer by date/ground.
        # The visit ID is used internally only, never added to public output.
        query=query.filter(Photo.fixture_id.is_(None),Photo.visit_id==row.visit_id)
    else:return {}
    total=query.with_entities(func.count(Photo.photo_id)).scalar()
    return {'matchday_photo_count':total} if total else {}


def public_page(db,storage,*,venue_id=None,fixture_id=None,cursor=None,limit=12,selection=None):
    query=public_photo_query(db)
    if venue_id is not None:query=query.filter(Photo.venue_id==venue_id)
    if fixture_id is not None:query=query.filter(Photo.fixture_id==fixture_id)
    if selection == 'discover':
        if cursor is not None or venue_id is not None or fixture_id is not None:
            raise HTTPException(422,'Discover selection cannot be combined with filters or a cursor')
        # Hard cap bounds SQL results, memory and work; never sign unselected candidates.
        candidates=query.order_by(Photo.published_at.desc(),Photo.photo_id.desc()).limit(120).all()
        representatives={}
        for row in candidates:representatives.setdefault(row.venue_id,row)
        selected=[];contributors=set();remaining=list(representatives.values())
        while remaining and len(selected)<min(limit,5):
            timestamp=remaining[0].published_at
            # Contributor preference only within exact timestamp ties: no stale displacement.
            row=next((p for p in remaining if p.published_at==timestamp and p.owner_user_id not in contributors),remaining[0])
            selected.append(row);contributors.add(row.owner_user_id);remaining.remove(row)
        selected.sort(key=lambda p:(p.published_at,p.photo_id),reverse=True)
        return {'photos':[{**photo_payload(db,storage,row),**public_matchday_metadata(db,row)} for row in selected],'next_cursor':None}
    if cursor:
        try:
            if len(cursor)>256:raise ValueError()
            timestamp,identifier=json.loads(base64.urlsafe_b64decode(cursor+'='*(-len(cursor)%4)))
            timestamp=datetime.fromisoformat(timestamp)
            if timestamp.tzinfo is None or type(identifier) is not int or identifier<1:raise ValueError()
        except (ValueError,TypeError,KeyError):raise HTTPException(400,'Invalid photo cursor') from None
        query=query.filter(or_(Photo.published_at<timestamp,and_(Photo.published_at==timestamp,Photo.photo_id<identifier)))
    rows=query.order_by(Photo.published_at.desc(),Photo.photo_id.desc()).limit(limit+1).all()
    more=len(rows)>limit;rows=rows[:limit]
    next_cursor=base64.urlsafe_b64encode(json.dumps([rows[-1].published_at.isoformat(),rows[-1].photo_id]).encode()).decode().rstrip('=') if more else None
    return {'photos':[photo_payload(db,storage,row) for row in rows],'next_cursor':next_cursor}
