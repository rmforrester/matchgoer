"""Disabled-by-default backend contracts. No frontend or hosted activation."""
import asyncio,base64,binascii,json,os,subprocess,sys
from pathlib import Path
from datetime import datetime,timezone
from fastapi import APIRouter,Depends,Header,HTTPException,Request,Query,Response
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel,ConfigDict,StrictBool,Field,ValidationError
from sqlalchemy.orm import Session
from sqlalchemy.exc import DBAPIError
from database import SessionLocal
from models import TerracePhoto as Photo,TerracePhotoEvent as Event,VenueVisit
from terraces import require_verified_account,require_photo_submitter,require_moderator,may_read_photo
from terraces_images import MAX_INPUT_BYTES,SanitisedPhoto,ImageVariant
from terraces_storage import LazyPrivatePhotoStorage as PrivatePhotoStorage,StorageUnavailable
import terraces_service as service

def controlled_photo_access(authorization:str|None=Header(default=None)):
    # Controlled testing covers reads too: approved test images must not become public.
    return transaction(lambda db:require_photo_submitter(db,authorization))

router=APIRouter(prefix='/terraces',tags=['From the Terraces'],dependencies=[Depends(controlled_photo_access)])
slots=asyncio.Semaphore(2)
class Metadata(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    caption:str|None=Field(default=None,max_length=200)
    public_consent:StrictBool
    rights_acknowledged:StrictBool
    consent_version:str
class Note(BaseModel):
    model_config=ConfigDict(extra='forbid')
    reason:str=Field(min_length=1,max_length=200)
class Hold(BaseModel):
    model_config=ConfigDict(extra='forbid')
    reason:str|None=Field(default=None,min_length=1,max_length=500)

def decode(data):
    environment={k:v for k,v in os.environ.items() if k in ('PATH','SYSTEMROOT','WINDIR','PYTHONPATH')}
    environment['PYTHONDONTWRITEBYTECODE']='1'
    flags=subprocess.CREATE_NO_WINDOW if sys.platform=='win32' else 0
    try:
        result=subprocess.run([sys.executable,str(Path(__file__).with_name('terraces_image_worker.py'))],input=data,capture_output=True,env=environment,timeout=15,creationflags=flags)
        if result.returncode:raise ValueError()
        payload=json.loads(result.stdout)
        variants=[ImageVariant(base64.b64decode(payload[n]['data'],validate=True),payload[n]['width'],payload[n]['height']) for n in ('display','thumbnail')]
        return SanitisedPhoto(payload['sha256'],payload['bytes'],*variants)
    except (subprocess.TimeoutExpired,ValueError,KeyError,TypeError,binascii.Error):
        raise HTTPException(422,'Photograph could not be safely processed') from None

def transaction(call):
    with SessionLocal() as db:
        try:return call(db)
        except StorageUnavailable:
            db.rollback();raise HTTPException(503,'Photographs are temporarily unavailable') from None
        except DBAPIError:
            db.rollback();raise HTTPException(503,'Photographs are temporarily unavailable. Please retry.') from None
        except Exception:
            db.rollback();raise

@router.post('/visits/{visit_id}/photos',status_code=201)
async def submit(visit_id:int,request:Request,response:Response,authorization:str|None=Header(default=None),idempotency_key:str=Header(),x_terraces_metadata:str=Header()):
    # Verify identity/owned attendance BEFORE reading/decoding untrusted bytes.
    def check(db):
        actor=require_photo_submitter(db,authorization)
        if not db.query(VenueVisit).filter_by(visit_id=visit_id,user_id=actor.user_id).first():raise HTTPException(404,'Owned recorded matchday not found')
    await run_in_threadpool(transaction,check)
    try:
        if len(x_terraces_metadata)>2048:raise ValueError()
        raw=base64.b64decode(x_terraces_metadata+'='*(-len(x_terraces_metadata)%4),altchars=b'-_',validate=True)
        metadata=Metadata.model_validate_json(raw).model_dump()
    except (ValueError,ValidationError,binascii.Error):raise HTTPException(422,'Invalid photo caption or sharing consent') from None
    # Never queue an unbounded number of image workers/requests.
    try:await asyncio.wait_for(slots.acquire(),timeout=.1)
    except asyncio.TimeoutError:raise HTTPException(429,'Photo processing is busy. Please retry.') from None
    try:
        stream=request.stream().__aiter__();data=bytearray();deadline=asyncio.get_running_loop().time()+30
        while True:
            remaining=deadline-asyncio.get_running_loop().time()
            if remaining<=0:raise HTTPException(408,'Photo upload timed out')
            try:chunk=await asyncio.wait_for(stream.__anext__(),timeout=min(5,remaining))
            except StopAsyncIteration:break
            except asyncio.TimeoutError:raise HTTPException(408,'Photo upload timed out') from None
            if len(data)+len(chunk)>MAX_INPUT_BYTES:raise HTTPException(413,'Photographs must be no larger than 10 MB')
            data.extend(chunk)
        processed=await run_in_threadpool(decode,bytes(data));data.clear()
        result=await run_in_threadpool(transaction,lambda db:service.submit(db,PrivatePhotoStorage(),authorization,visit_id,processed,metadata,idempotency_key))
        response.headers['Cache-Control']='no-store';return result
    finally:slots.release()

@router.get('/photos')
def public_photos(response:Response,venue_id:int|None=None,fixture_id:int|None=None,cursor:str|None=None,limit:int=Query(12,ge=1,le=24)):
    response.headers['Cache-Control']='no-store'
    return transaction(lambda db:service.public_page(db,PrivatePhotoStorage(),venue_id=venue_id,fixture_id=fixture_id,cursor=cursor,limit=limit))

@router.get('/visits/{visit_id}/photos')
def owned_photos(visit_id:int,response:Response,authorization:str|None=Header(default=None)):
    def action(db):
        actor=require_verified_account(db,authorization)
        if not db.query(VenueVisit).filter_by(visit_id=visit_id,user_id=actor.user_id).first():raise HTTPException(404,'Recorded matchday not found')
        return {'photos':[service.photo_payload(db,PrivatePhotoStorage(),row,private=True) for row in db.query(Photo).filter_by(visit_id=visit_id,owner_user_id=actor.user_id).order_by(Photo.submitted_at,Photo.photo_id).all()]}
    response.headers['Cache-Control']='no-store';return transaction(action)

@router.get('/photos/{photo_id}')
def photo_detail(photo_id:int,response:Response,authorization:str|None=Header(default=None)):
    def action(db):
        actor=require_verified_account(db,authorization) if authorization else None
        row=db.get(Photo,photo_id)
        if not row or not may_read_photo(row,actor) or not service.ready(db,row):raise HTTPException(404,'Photograph not found')
        private=not (row.status=='APPROVED' and row.published_at is not None)
        return service.photo_payload(db,PrivatePhotoStorage(),row,private=private)
    response.headers['Cache-Control']='no-store';return transaction(action)

@router.delete('/photos/{photo_id}')
def remove(photo_id:int,authorization:str|None=Header(default=None)):
    return transaction(lambda db:service.remove(db,PrivatePhotoStorage(),authorization,photo_id))
@router.post('/photos/{photo_id}/reports')
def report(photo_id:int,note:Note,authorization:str|None=Header(default=None)):
    return transaction(lambda db:service.report(db,authorization,photo_id,note.reason))

@router.get('/moderator/photos')
def moderator_photos(response:Response,state:str=Query('PENDING',pattern='^(PENDING|APPROVED|REJECTED)$'),limit:int=Query(24,ge=1,le=50),after_id:int=Query(0,ge=0),authorization:str|None=Header(default=None)):
    def action(db):
        require_moderator(db,authorization)
        query=db.query(Photo).filter(Photo.status==state,Photo.photo_id>after_id)
        if state=='PENDING':query=query.filter(service.ready_clause())
        if state=='APPROVED':query=query.filter(Photo.published_at.is_not(None))
        rows=query.order_by(Photo.photo_id).limit(limit+1).all()
        return {'pending_count':db.query(Photo).filter(Photo.status=='PENDING',service.ready_clause()).count(),'photos':[service.photo_payload(db,PrivatePhotoStorage(),row,private=True) for row in rows[:limit]],'next_id':rows[limit-1].photo_id if len(rows)>limit else None}
    response.headers['Cache-Control']='no-store';return transaction(action)
@router.post('/moderator/photos/{photo_id}/approve')
def approve(photo_id:int,authorization:str|None=Header(default=None)):
    return transaction(lambda db:service.approve(db,authorization,photo_id))
@router.post('/moderator/photos/{photo_id}/reject')
def reject(photo_id:int,note:Note,authorization:str|None=Header(default=None)):
    return transaction(lambda db:service.reject(db,authorization,photo_id,note.reason))
@router.delete('/moderator/photos/{photo_id}')
def moderator_remove(photo_id:int,authorization:str|None=Header(default=None)):
    return transaction(lambda db:service.remove(db,PrivatePhotoStorage(),authorization,photo_id,moderator=True))
@router.put('/moderator/photos/{photo_id}/hold')
def set_hold(photo_id:int,body:Hold,authorization:str|None=Header(default=None)):
    return transaction(lambda db:service.hold(db,authorization,photo_id,body.reason))
@router.get('/moderator/reports')
def reports(response:Response,limit:int=Query(24,ge=1,le=50),after_id:int=Query(0,ge=0),authorization:str|None=Header(default=None)):
    def action(db):
        require_moderator(db,authorization)
        rows=db.query(Event).filter(Event.event_type=='PHOTO_REPORTED',Event.completed_at.is_(None),Event.event_id>after_id).order_by(Event.event_id).limit(limit+1).all()
        return {'reports':[{'report_id':r.event_id,'photo_id':r.photo_id,'reason':r.payload.get('reason'),'created_at':r.created_at} for r in rows[:limit]],'next_id':rows[limit-1].event_id if len(rows)>limit else None}
    response.headers['Cache-Control']='no-store';return transaction(action)
@router.post('/moderator/reports/{event_id}/resolve')
def resolve(event_id:int,note:Note,authorization:str|None=Header(default=None)):
    return transaction(lambda db:service.resolve_report(db,authorization,event_id,note.reason))
