import unittest
from unittest.mock import patch
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy.exc import DBAPIError
from models import TerracePhoto as Photo,TerracePhotoEvent as Event,VenueVisit
from backend.tests import test_terraces_b1 as fixtures
import terraces_service as service


class ModeratorAutoApprovalTests(unittest.TestCase):
    setUp=fixtures.PhotoB1Tests.setUp
    tearDown=fixtures.PhotoB1Tests.tearDown
    submit=fixtures.PhotoB1Tests.submit

    def test_ready_publication_and_distinct_audit_are_atomic_and_idempotent(self):
        key=str(uuid4());put=self.storage.put
        def checked_put(*args):
            row=self.db.query(Photo).one()
            self.assertEqual(row.status,'PENDING');self.assertIsNone(row.published_at)
            put(*args)
        with patch.object(self.storage,'put',side_effect=checked_put):result=self.submit(key=key,moderator=True)
        self.assertEqual(result['status'],'APPROVED');row=self.db.get(Photo,result['photo_id'])
        self.assertTrue(service.ready(self.db,row));self.assertEqual(row.approved_at,row.published_at)
        self.assertEqual(len(service.public_page(self.db,self.storage)['photos']),1)
        audit=self.db.query(Event).filter_by(photo_id=row.photo_id,event_type='MODERATOR_APPROVED').one()
        self.assertEqual(audit.actor_user_id,self.owner.user_id);self.assertEqual(audit.payload['method'],'automatic');self.assertIsNotNone(audit.completed_at)
        self.assertEqual(self.submit(key=key,moderator=True),result);self.assertEqual(self.storage.puts,2)
        self.assertEqual(self.db.query(Event).filter_by(event_type='MODERATOR_APPROVED').count(),1)

    def test_supporter_requires_manual_approval_with_different_audit(self):
        result=self.submit();self.assertEqual(result['status'],'PENDING')
        self.assertEqual(service.public_page(self.db,self.storage)['photos'],[])
        service.approve(self.db,'Bearer synthetic',result['photo_id'])
        audit=self.db.query(Event).filter_by(photo_id=result['photo_id'],event_type='MODERATOR_APPROVED').one()
        self.assertNotIn('method',audit.payload)

    def test_missing_invalid_configuration_and_spoofed_identity_fail_closed(self):
        for index,value in enumerate(('','invalid','0','-1','1347,830')):
            self.visit=VenueVisit(user_id=self.owner.user_id,venue_id=self.venue.venue_id,source='manual')
            self.db.add(self.visit);self.db.flush()
            with patch.dict('os.environ',{'TERRACES_MODERATOR_USER_ID':value}):
                self.assertEqual(self.submit('config-'+str(index),moderator=True)['status'],'PENDING')
        self.provider.subject=str(self.other.user_id)
        with self.assertRaises(HTTPException):self.submit('spoof',moderator=True)
        with patch('terraces.verify_claim_provider_identity',side_effect=HTTPException(401,'Unverified')),self.assertRaises(HTTPException):self.submit('unverified',moderator=True)

    def test_failure_does_not_publish_and_exact_retry_approves_once(self):
        key=str(uuid4());self.storage.fail_put=2
        with self.assertRaises(HTTPException):self.submit(key=key,moderator=True)
        row=self.db.query(Photo).one();self.assertEqual(row.status,'PENDING');self.assertIsNone(row.published_at)
        self.assertEqual(self.db.query(Event).filter_by(event_type='MODERATOR_APPROVED').count(),0)
        self.assertEqual(service.public_page(self.db,self.storage)['photos'],[])
        self.storage.fail_put=None;self.assertEqual(self.submit(key=key,moderator=True)['status'],'APPROVED')
        self.assertEqual(self.db.query(Photo).count(),1)

    def test_publication_commit_failure_leaves_private_reservation_and_retry(self):
        key=str(uuid4());commit=self.db.commit;calls=0
        def fail_publication():
            nonlocal calls
            calls+=1
            if calls==2:raise DBAPIError('synthetic statement',{},Exception('synthetic failure'))
            commit()
        with patch.object(self.db,'commit',side_effect=fail_publication),self.assertRaises(DBAPIError):
            self.submit(key=key,moderator=True)
        self.db.rollback() # Same rollback performed by the API transaction boundary.
        row=self.db.query(Photo).one()
        self.assertEqual(row.status,'PENDING');self.assertIsNone(row.published_at)
        self.assertFalse(service.ready(self.db,row));self.assertEqual(service.public_page(self.db,self.storage)['photos'],[])
        self.assertEqual(self.db.query(Event).filter_by(event_type='MODERATOR_APPROVED').count(),0)
        self.assertEqual(self.submit(key=key,moderator=True)['status'],'APPROVED')
        self.assertEqual(self.db.query(Event).filter_by(event_type='MODERATOR_APPROVED').count(),1)

    def test_quota_consent_removal_reporting_and_partial_batch(self):
        result=self.submit('first',moderator=True)
        self.meta['public_consent']=False
        with self.assertRaises(HTTPException):self.submit('no-consent',moderator=True)
        self.meta['public_consent']=True
        self.storage.fail_put=self.storage.puts+1
        with self.assertRaises(HTTPException):self.submit('failed-second',moderator=True)
        self.assertEqual(len(service.public_page(self.db,self.storage)['photos']),1)
        self.storage.fail_put=None
        service.report(self.db,'Bearer synthetic',result['photo_id'],'Synthetic concern')
        service.remove(self.db,self.storage,'Bearer synthetic',result['photo_id'])
        self.assertEqual(service.public_page(self.db,self.storage)['photos'],[])
        for label in ('second','third'):self.submit(label,moderator=True)
        with self.assertRaises(HTTPException):self.submit('fourth',moderator=True)
