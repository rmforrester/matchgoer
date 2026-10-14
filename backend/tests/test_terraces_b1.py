import unittest
from unittest.mock import patch
from datetime import datetime,timedelta,timezone
from uuid import uuid4
from hashlib import sha256
from sqlalchemy.orm import Session
from sqlalchemy import text
from fastapi import HTTPException
from database import engine
from models import User,UserIdentity,Venue,VenueVisit,UserProfile,TerracePhoto as Photo,TerracePhotoEvent as Event
from terraces import CONSENT_VERSION
from terraces_images import SanitisedPhoto,ImageVariant
from terraces_storage import StorageUnavailable
import terraces_service as service

class FakeStorage:
    def __init__(self):self.objects={};self.fail_put=None;self.fail_delete=False;self.puts=0;self.deletes=0
    def put(self,key,data):
        self.puts+=1
        if self.fail_put==self.puts:raise StorageUnavailable()
        if key in self.objects and self.objects[key]!=data:raise StorageUnavailable()
        self.objects[key]=data
    def delete(self,key):
        self.deletes+=1
        if self.fail_delete:raise StorageUnavailable()
        self.objects.pop(key,None)
    def signed(self,key):return 'https://synthetic.test/signed/'+key

class PhotoB1Tests(unittest.TestCase):
    def setUp(self):
        self.connection=engine.connect();self.outer=self.connection.begin()
        self.db=Session(bind=self.connection,join_transaction_mode='create_savepoint')
        self.owner=User(account_status='registered',is_anonymous=False)
        self.other=User(account_status='registered',is_anonymous=False)
        self.guest=User(account_status='anonymous',is_anonymous=True)
        self.db.add_all([self.owner,self.other,self.guest]);self.db.flush()
        for user in (self.owner,self.other):
            self.db.add(UserIdentity(user_id=user.user_id,issuer='https://synthetic.test/auth/v1',subject=str(user.user_id),email_verified_at=datetime.now(timezone.utc)))
            self.db.add(UserProfile(user_id=user.user_id,display_name='Synthetic supporter'))
        self.venue=Venue(name='Synthetic ground',country='Test');self.db.add(self.venue);self.db.flush()
        self.visit=VenueVisit(user_id=self.owner.user_id,venue_id=self.venue.venue_id,source='manual',visit_date=None)
        self.db.add(self.visit);self.db.flush()
        self.provider=type('Provider',(),{'issuer':'https://synthetic.test/auth/v1','subject':str(self.owner.user_id)})()
        self.authentication=patch('terraces.verify_claim_provider_identity',return_value=self.provider);self.authentication.start()
        self.configuration=patch.dict('os.environ',{'TERRACES_MODERATOR_USER_ID':str(self.owner.user_id),'TERRACES_UPLOAD_USER_IDS':str(self.owner.user_id)});self.configuration.start()
        self.storage=FakeStorage();self.meta={'public_consent':True,'rights_acknowledged':True,'consent_version':CONSENT_VERSION,'caption':None}
    def tearDown(self):
        self.configuration.stop();self.authentication.stop();self.db.close();self.outer.rollback();self.connection.close()
    def submit(self,label='one',key=None):
        image=SanitisedPhoto(sha256(label.encode()).hexdigest(),1,ImageVariant(b'display',1,1),ImageVariant(b'thumbnail',1,1))
        return service.submit(self.db,self.storage,'Bearer synthetic',self.visit.visit_id,image,self.meta,key or str(uuid4()))
    def test_pending_private_historical_owned_context(self):
        result=self.submit();row=self.db.get(Photo,result['photo_id'])
        self.assertEqual(row.status,'PENDING');self.assertEqual(row.venue_id,self.venue.venue_id);self.assertIsNone(row.fixture_id)
        self.assertTrue(service.ready(self.db,row));self.assertEqual(len(self.storage.objects),2)
        self.assertEqual(service.public_page(self.db,self.storage)['photos'],[])
    def test_guest_other_owner_and_unverified_rejected(self):
        for user in (self.other,self.guest):
            self.provider.subject=str(user.user_id)
            with self.assertRaises(HTTPException):self.submit()
            self.db.rollback()
        self.provider.subject=str(self.owner.user_id)
        self.authentication.stop()
        with patch('terraces.verify_claim_provider_identity',side_effect=HTTPException(403,'Unverified')),self.assertRaises(HTTPException):self.submit()
        self.authentication.start()
        self.assertEqual(self.storage.objects,{})
    def test_three_limit_duplicates_and_exact_retry(self):
        key=str(uuid4());first=self.submit(key=key);self.assertEqual(self.submit(key=key),first);self.assertEqual(self.storage.puts,2)
        with self.assertRaises(HTTPException):self.submit()
        self.submit('two');self.submit('three')
        with self.assertRaises(HTTPException):self.submit('four')
        self.assertEqual(self.db.query(Photo).count(),3)
    def test_partial_failure_cleaned_then_same_key_can_retry(self):
        key=str(uuid4());self.storage.fail_put=2
        with self.assertRaises(HTTPException) as error:self.submit(key=key)
        self.assertEqual(error.exception.status_code,503);self.assertEqual(self.storage.objects,{})
        row=self.db.query(Photo).one();self.assertFalse(service.ready(self.db,row));self.assertEqual(row.status,'PENDING')
        self.storage.fail_put=None;self.submit(key=key);self.assertEqual(self.db.query(Photo).count(),1)
        self.assertTrue(service.ready(self.db,row))
    def test_partial_cleanup_failure_retains_retry_receipt(self):
        self.storage.fail_put=2;self.storage.fail_delete=True
        with self.assertRaises(HTTPException):self.submit()
        row=self.db.query(Photo).one();self.assertTrue(self.storage.objects)
        self.assertEqual(self.db.query(Event).filter_by(event_type='UPLOAD_CLEANUP_REQUIRED').filter(Event.completed_at.is_(None)).count(),1)
        self.storage.fail_delete=False;service.cleanup_upload(self.db,self.storage,row.photo_id);self.assertEqual(self.storage.objects,{})
    def test_approval_permission_readiness_and_no_resurrection(self):
        identifier=self.submit()['photo_id']
        self.provider.subject=str(self.other.user_id)
        with self.assertRaises(HTTPException):service.approve(self.db,'Bearer synthetic',identifier)
        self.provider.subject=str(self.owner.user_id)
        service.approve(self.db,'Bearer synthetic',identifier)
        self.assertEqual(len(service.public_page(self.db,self.storage)['photos']),1)
        service.remove(self.db,self.storage,'Bearer synthetic',identifier)
        self.assertEqual(service.public_page(self.db,self.storage)['photos'],[])
        with self.assertRaises(HTTPException):service.approve(self.db,'Bearer synthetic',identifier)
    def test_rejection_seven_day_retention_and_legal_hold(self):
        identifier=self.submit()['photo_id'];service.reject(self.db,'Bearer synthetic',identifier,'Not suitable')
        row=self.db.get(Photo,identifier);at=row.rejected_at
        self.assertFalse(service.purge_photo(self.db,self.storage,identifier,at+timedelta(days=6)))
        service.hold(self.db,'Bearer synthetic',identifier,'Documented dispute')
        self.assertFalse(service.purge_photo(self.db,self.storage,identifier,at+timedelta(days=8)))
        service.hold(self.db,'Bearer synthetic',identifier,None)
        self.assertTrue(service.purge_photo(self.db,self.storage,identifier,at+timedelta(days=8)))
        self.assertEqual(self.storage.objects,{})
    def test_removal_other_owner_denied_and_physical_retry(self):
        identifier=self.submit()['photo_id'];service.approve(self.db,'Bearer synthetic',identifier)
        self.provider.subject=str(self.other.user_id)
        with self.assertRaises(HTTPException):service.remove(self.db,self.storage,'Bearer synthetic',identifier)
        self.provider.subject=str(self.owner.user_id);self.storage.fail_delete=True
        result=service.remove(self.db,self.storage,'Bearer synthetic',identifier)
        self.assertEqual(result['physical_cleanup'],'pending');self.assertEqual(service.public_page(self.db,self.storage)['photos'],[])
        self.storage.fail_delete=False;service.cleanup(self.db,self.storage);self.assertEqual(self.storage.objects,{})
    def test_report_dedup_moderator_resolution_and_permissions(self):
        identifier=self.submit()['photo_id']
        with self.assertRaises(HTTPException):service.report(self.db,'Bearer synthetic',identifier,'Problem')
        service.approve(self.db,'Bearer synthetic',identifier);self.provider.subject=str(self.other.user_id)
        item=service.report(self.db,'Bearer synthetic',identifier,'Problem')
        self.assertEqual(service.report(self.db,'Bearer synthetic',identifier,'Again'),item)
        with self.assertRaises(HTTPException):service.resolve_report(self.db,'Bearer synthetic',item['report_id'],'Reviewed')
        self.provider.subject=str(self.owner.user_id);self.assertEqual(service.resolve_report(self.db,'Bearer synthetic',item['report_id'],'Reviewed')['status'],'resolved')
    def test_public_minimisation_and_stable_pagination(self):
        identifiers=[self.submit(str(n))['photo_id'] for n in range(3)]
        for identifier in identifiers:service.approve(self.db,'Bearer synthetic',identifier)
        first=service.public_page(self.db,self.storage,limit=2);second=service.public_page(self.db,self.storage,limit=2,cursor=first['next_cursor'])
        self.assertEqual(len(first['photos']),2);self.assertEqual(len(second['photos']),1)
        self.assertFalse(set(x['photo_id'] for x in first['photos'])&set(x['photo_id'] for x in second['photos']))
        for row in first['photos']+second['photos']:
            for key in ('owner_user_id','visit_id','email','source_sha256','display_key','gps'):self.assertNotIn(key,row)
            self.assertIsNone(row['match_date'])
        with self.assertRaises(HTTPException):service.public_page(self.db,self.storage,cursor='not-valid')
    def test_attendance_deletion_unpublishes_and_cleanup_purges(self):
        identifier=self.submit()['photo_id'];service.approve(self.db,'Bearer synthetic',identifier)
        self.db.delete(self.visit);self.db.commit();self.db.expire_all()
        self.assertEqual(self.db.get(Photo,identifier).status,'REMOVED');self.assertEqual(service.public_page(self.db,self.storage)['photos'],[])
        service.cleanup(self.db,self.storage);self.assertEqual(self.storage.objects,{})
    def test_account_deletion_receipt_preserves_hold_and_keys(self):
        identifier=self.submit()['photo_id'];service.hold(self.db,'Bearer synthetic',identifier,'Legal hold')
        self.db.delete(self.visit);self.db.flush();self.db.delete(self.owner);self.db.commit();self.db.expire_all()
        self.assertIsNone(self.db.get(Photo,identifier))
        item=self.db.query(Event).filter_by(event_type='STORAGE_DELETE_REQUIRED').one()
        self.assertTrue(item.payload['legal_hold']);self.assertIsNone(item.photo_id)
        service.cleanup(self.db,self.storage);self.assertEqual(len(self.storage.objects),2)
    def test_account_deletion_without_hold_purges_physical_variants(self):
        self.submit();self.db.delete(self.visit);self.db.flush();self.db.delete(self.owner);self.db.commit()
        service.cleanup(self.db,self.storage);self.assertEqual(self.storage.objects,{})
    def test_unknown_orphan_hold_fails_closed(self):
        self.submit();self.db.delete(self.visit);self.db.flush();self.db.delete(self.owner);self.db.commit()
        item=self.db.query(Event).filter_by(event_type='STORAGE_DELETE_REQUIRED').one()
        item.payload={k:v for k,v in item.payload.items() if k!='legal_hold'};self.db.commit()
        service.cleanup(self.db,self.storage);self.assertEqual(len(self.storage.objects),2)
    def test_abandoned_upload_cleans_objects_without_publishing(self):
        identifier=self.submit()['photo_id'];row=self.db.get(Photo,identifier)
        self.db.query(Event).filter_by(photo_id=identifier,event_type='STORAGE_READY').delete()
        row.submitted_at=service.now()-timedelta(minutes=6);self.db.commit()
        service.cleanup(self.db,self.storage);self.assertEqual(self.storage.objects,{})
        self.assertEqual(service.public_page(self.db,self.storage)['photos'],[])
        self.assertEqual(self.db.get(Photo,identifier).status,'PENDING')
    def test_readiness_commit_failure_retains_private_cleanup_reservation(self):
        from sqlalchemy.exc import DBAPIError
        original=self.db.commit;calls=0
        def failing_commit():
            nonlocal calls
            calls+=1
            if calls==2:
                self.db.rollback();raise DBAPIError('synthetic',{},Exception('synthetic commit failure'))
            original()
        with patch.object(self.db,'commit',side_effect=failing_commit),self.assertRaises(DBAPIError):self.submit()
        row=self.db.query(Photo).one();self.assertFalse(service.ready(self.db,row))
        self.assertEqual(service.public_page(self.db,self.storage)['photos'],[])
        self.assertEqual(len(self.storage.objects),2)
        row.submitted_at=service.now()-timedelta(minutes=6);self.db.commit()
        service.cleanup(self.db,self.storage);self.assertEqual(self.storage.objects,{})
    def test_daily_cleanup_is_idempotent(self):
        identifier=self.submit()['photo_id'];service.remove(self.db,self.storage,'Bearer synthetic',identifier)
        before=self.storage.deletes
        self.assertEqual(service.cleanup(self.db,self.storage),{'cleaned':0,'retry_pending':0})
        self.assertEqual(service.cleanup(self.db,self.storage),{'cleaned':0,'retry_pending':0})
        self.assertEqual(self.storage.deletes,before)
    def test_daily_cleanup_respects_exact_seven_day_boundary(self):
        identifier=self.submit()['photo_id'];service.reject(self.db,'Bearer synthetic',identifier,'Not suitable')
        rejected=self.db.get(Photo,identifier).rejected_at
        self.assertEqual(service.cleanup(self.db,self.storage,at=rejected+timedelta(days=7)-timedelta(seconds=1))['cleaned'],0)
        self.assertEqual(len(self.storage.objects),2)
        self.assertEqual(service.cleanup(self.db,self.storage,at=rejected+timedelta(days=7))['cleaned'],1)
        self.assertEqual(self.storage.objects,{})
