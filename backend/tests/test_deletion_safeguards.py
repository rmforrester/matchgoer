"""Synthetic local PostgreSQL only: privacy ownership, bounded scope and manual rehearsal."""
import unittest
import copy
from datetime import datetime, timezone
from unittest.mock import patch
from fastapi import HTTPException
from sqlalchemy import text, select
from sqlalchemy.orm import Session
import account_deletion as deletion
import identity
from database import engine
from models import (User, UserIdentity, UserProfile, VenueVisit, InterestedFixture, AwayDayReview, Fixture,
                    SocialEvent, AnonymousSession, AccountConversionHandoff, MatchBoardPost,
                    MatchBoardReport, MatchdayTip, TerracePhoto, TerracePhotoEvent)
from backend.tests import test_account_claim as claims_fixture
from backend.tests import test_identity as identity_fixture
from backend.tests import test_terraces_b1 as photo_fixture


def local_only():
    assert engine.url.host == '127.0.0.1' and engine.url.database.startswith('build8_synthetic_')


class PrivacyIdentityTests(unittest.TestCase):
    setUpClass = classmethod(identity_fixture.IdentityResolutionTests.setUpClass.__func__)
    setUp = identity_fixture.IdentityResolutionTests.setUp
    tearDown = identity_fixture.IdentityResolutionTests.tearDown
    token = identity_fixture.IdentityResolutionTests.token

    def resolve(self, token, privacy=True, cookie=None):
        return identity.resolve_identity(self.db, authorization='Bearer '+token, session_id=cookie,
            required=True, config=self.config, jwks_client=identity_fixture.StaticJwksClient(self.private_key.public_key()), privacy_only=privacy)

    def test_verified_suspended_owner_has_privacy_access_only(self):
        local_only()
        self.registered.account_status='suspended';self.db.flush()
        result=self.resolve(self.token(),cookie=self.cookie.session_id)
        self.assertEqual(result.user_id,self.registered.user_id)
        self.assertTrue(result.is_registered)
        with self.assertRaises(HTTPException):self.resolve(self.token(),privacy=False)
        request=deletion.request_deletion(self.db,result,True)
        self.assertEqual(request.request_type,'account')
        self.assertEqual(self.registered.account_status,'suspended')
        self.assertIsNone(deletion.latest(self.db,self.anonymous.user_id))

    def test_privacy_does_not_relax_token_or_mapping_checks(self):
        self.registered.account_status='suspended';self.db.flush()
        for token in [self.token(exp=1),self.token(aud='wrong'),self.token(iss='https://wrong.test'),self.token('unmapped'),self.token()+'broken']:
            with self.subTest(token_kind='synthetic'),self.assertRaises(HTTPException):self.resolve(token)

    def test_suspended_cookie_merged_and_deleted_cannot_gain_access(self):
        self.anonymous.account_status='suspended';self.db.flush()
        with self.assertRaises(HTTPException):
            identity.resolve_identity(self.db,authorization=None,session_id=self.cookie.session_id,required=True,privacy_only=True)
        for status in ['merged','deleted']:
            self.registered.account_status=status;self.db.flush()
            with self.assertRaises(HTTPException):self.resolve(self.token())
    def test_completed_receipt_expires_after_ninety_days_but_pending_remains_visible(self):
        from datetime import timedelta
        row=deletion.AccountDeletionRequest(completed_at=datetime(2026,1,1,tzinfo=timezone.utc))
        self.assertTrue(deletion.receipt_available(row,datetime(2026,1,1,tzinfo=timezone.utc)+timedelta(days=90,seconds=-1)))
        self.assertFalse(deletion.receipt_available(row,datetime(2026,1,1,tzinfo=timezone.utc)+timedelta(days=90)))
        row.completed_at=None
        self.assertTrue(deletion.receipt_available(row))



class TransferScopeTests(unittest.TestCase):
    setUp = claims_fixture.AccountClaimTests.setUp
    tearDown = claims_fixture.AccountClaimTests.tearDown
    new_anonymous = claims_fixture.AccountClaimTests.new_anonymous
    new_registered = claims_fixture.AccountClaimTests.new_registered
    claim = claims_fixture.AccountClaimTests.claim

    def prepare(self, suffix):
        local_only()
        uid,cookie=self.new_anonymous(suffix)
        visit=VenueVisit(user_id=uid,venue_id=self.venue_id,source='manual')
        interest=InterestedFixture(user_id=uid,fixture_id=self.fixture_id,going=True)
        self.db.add_all([visit,interest]);self.db.flush()
        row=deletion.request_deletion(self.db,identity.ResolvedIdentity(uid,'anonymous',False,'anonymous'),True)
        request_id=row.request_id;scope=copy.deepcopy(row.record_scope);due=row.due_at
        self.db.commit()
        return uid,cookie,request_id,scope,due

    def test_new_registration_does_not_expand_guest_request(self):
        uid,cookie,rid,scope,due=self.prepare('scope-new')
        self.claim(cookie,'scope-new')
        self.db.expire_all();row=self.db.get(deletion.AccountDeletionRequest,rid)
        self.assertEqual(row.record_scope,scope);self.assertEqual(row.due_at,due)
        self.assertEqual(row.transfer_lineage,[{'target_user_id':uid,'kind':'registration'}])
        with self.assertRaises(HTTPException):deletion.guarded_guest_scope(self.db,row)
        account=deletion.request_deletion(self.db,identity.ResolvedIdentity(uid,'registered',True,'bearer'),True)
        self.assertNotEqual(row.request_id,account.request_id)
        self.assertEqual(account.request_type,'account');self.db.commit()

    def test_existing_account_collision_keeps_original_scope_and_requires_review(self):
        target=self.new_registered('scope-target')
        existing=InterestedFixture(user_id=target,fixture_id=self.fixture_id,going=False)
        existing_visit=VenueVisit(user_id=target,venue_id=self.venue_id,source='manual')
        self.db.add_all([existing,existing_visit]);self.db.commit();target_visit=existing_visit.visit_id
        uid,cookie,rid,scope,due=self.prepare('scope-merge')
        from account_claim import issue_account_conversion_handoff
        handoff,_=issue_account_conversion_handoff(self.db,session_id=cookie)
        self.claim(cookie,'scope-target',handoff_token=handoff);self.claim(cookie,'scope-target',handoff_token=handoff)
        self.db.expire_all();row=self.db.get(deletion.AccountDeletionRequest,rid)
        self.assertEqual(row.user_id,uid);self.assertEqual(row.record_scope,scope);self.assertEqual(row.due_at,due)
        self.assertEqual(row.transfer_lineage,[{'target_user_id':target,'kind':'merge'}])
        self.assertEqual(self.db.get(VenueVisit,target_visit).user_id,target)
        self.assertEqual(self.db.query(InterestedFixture).filter_by(user_id=target).count(),1)
        with self.assertRaises(HTTPException):deletion.guarded_guest_scope(self.db,row)
        self.assertIsNone(deletion.latest(self.db,target,'account'))

    def test_transfer_failure_rolls_back_lineage_and_history_together(self):
        uid,cookie,rid,scope,due=self.prepare('scope-fail')
        def fail(stage):
            if stage=='after_user':raise RuntimeError('synthetic failure')
        with self.assertRaises(RuntimeError):self.claim(cookie,'scope-fail',failure_hook=fail)
        self.db.expire_all();row=self.db.get(deletion.AccountDeletionRequest,rid)
        self.assertEqual(row.transfer_lineage,[]);self.assertEqual(row.record_scope,scope)
        self.assertEqual(self.db.get(User,uid).account_status,'anonymous')

    def test_unchanged_guest_scope_excludes_later_history_and_rejects_missing_rows(self):
        uid,cookie,rid,scope,due=self.prepare('scope-guard')
        row=self.db.get(deletion.AccountDeletionRequest,rid)
        later=VenueVisit(user_id=uid,venue_id=self.venue_id,source='manual',visit_date=datetime(2020,1,1).date())
        self.db.add(later);self.db.flush()
        self.assertEqual(deletion.guarded_guest_scope(self.db,row),scope)
        self.assertNotIn(later.visit_id,scope['visits'])
        self.db.delete(self.db.get(VenueVisit,scope['visits'][0]));self.db.flush()
        with self.assertRaises(HTTPException):deletion.guarded_guest_scope(self.db,row)
        self.db.rollback()


class ManualFulfilmentRehearsal(unittest.TestCase):
    setUp = photo_fixture.PhotoB1Tests.setUp
    tearDown = photo_fixture.PhotoB1Tests.tearDown
    submit = photo_fixture.PhotoB1Tests.submit

    def test_disposable_owner_cleanup_provider_failure_retry_and_receipt(self):
        local_only()
        fixture=self.db.execute(text('SELECT fixture_id FROM fixtures LIMIT 1')).scalar_one()
        pid=self.submit()['photo_id'];photo=self.db.get(TerracePhoto,pid)
        keys=[photo.display_key,photo.thumbnail_key]
        self.db.add_all([AwayDayReview(user_id=self.owner.user_id,venue_id=self.venue.venue_id),
                         InterestedFixture(user_id=self.owner.user_id,fixture_id=fixture),
                         SocialEvent(user_id=self.owner.user_id,fixture_id=fixture,event_type='fixture_view')])
        parent=MatchBoardPost(author_user_id=self.owner.user_id,fixture_id=fixture,body='Synthetic private text')
        self.db.add(parent);self.db.flush()
        reply=MatchBoardPost(author_user_id=self.other.user_id,fixture_id=fixture,parent_post_id=parent.post_id,body='Other supporter reply')
        self.db.add(reply);self.db.flush()
        row=deletion.request_deletion(self.db,identity.ResolvedIdentity(self.owner.user_id,'registered',True,'bearer'),True)
        row.apple_revocation='not_required';receipt=deletion.issue_receipt(row);self.db.commit()
        # Fingerprint another owner and canonical inventory, not only total counts.
        import hashlib,json
        def unrelated_fingerprint():
            material={}
            for model in [User,UserIdentity,UserProfile,VenueVisit,InterestedFixture,AwayDayReview]:
                material[model.__tablename__]=[dict(r) for r in self.db.execute(select(model.__table__).where(model.user_id==self.other.user_id)).mappings()]
            material['fixtures']=[dict(r) for r in self.db.execute(select(Fixture.__table__).order_by(Fixture.fixture_id)).mappings()]
            material['reply']=[dict(r) for r in self.db.execute(select(MatchBoardPost.__table__).where(MatchBoardPost.post_id==reply.post_id)).mappings()]
            return hashlib.sha256(json.dumps(material,sort_keys=True,default=str).encode()).hexdigest()
        before=unrelated_fingerprint()
        owner_id=self.owner.user_id
        owner_restore=dict(self.db.execute(select(User.__table__).where(User.user_id==owner_id)).mappings().one())
        fake_auth={self.owner.user_id:True,self.other.user_id:True};confirmations=[]
        # Provider outage leaves durable pending status and all DB records intact.
        self.storage.fail_delete=True
        with self.assertRaises(Exception):self.storage.delete(keys[0])
        self.assertEqual(row.status,'pending');self.assertIsNotNone(self.db.get(TerracePhoto,pid))
        self.storage.fail_delete=False
        for key in keys:self.storage.delete(key)
        self.assertFalse(any(key in self.storage.objects for key in keys))
        self.db.query(TerracePhotoEvent).filter_by(photo_id=pid).delete();self.db.delete(photo);self.db.flush()
        # Preserve another author's reply via a non-authenticating structural tombstone.
        tombstone=User(account_status='deleted',is_anonymous=False);self.db.add(tombstone);self.db.flush()
        self.db.add(UserProfile(user_id=tombstone.user_id,display_name='Deleted matchgoer'));self.db.flush()
        parent.author_user_id=tombstone.user_id;parent.body='Post deleted';parent.deleted_at=datetime.now(timezone.utc);self.db.flush()
        for model in [AwayDayReview,InterestedFixture,SocialEvent,VenueVisit]:
            self.db.query(model).filter_by(user_id=self.owner.user_id).delete(synchronize_session=False)
        self.db.query(UserIdentity).filter_by(user_id=self.owner.user_id).delete()
        self.db.query(UserProfile).filter_by(user_id=self.owner.user_id).delete()
        fake_auth.pop(self.owner.user_id)
        self.assertIn(self.other.user_id,fake_auth)
        row.user_id=None;row.status='completed';row.completed_at=datetime.now(timezone.utc)
        self.db.delete(self.owner);self.db.flush()
        confirmations.append(row.request_id);row.confirmed_at=datetime.now(timezone.utc);self.db.commit()
        self.assertEqual(len(confirmations),1)
        self.assertIsNone(self.db.get(User,self.owner.user_id))
        self.assertEqual(unrelated_fingerprint(),before)
        import hashlib
        self.assertEqual(self.db.query(deletion.AccountDeletionRequest).filter_by(receipt_hash=hashlib.sha256(receipt.encode()).hexdigest()).one().status,'completed')
        # Actual local row restoration, isolated before it can serve any application.
        # This proves a selective ledger replay, not a full provider backup restore.
        self.db.execute(User.__table__.insert().values(**owner_restore));self.db.flush()
        self.assertEqual(self.db.execute(select(User.user_id).where(User.user_id==owner_id)).scalar_one(),owner_id)
        deletion_ledger={owner_id}
        self.db.execute(User.__table__.delete().where(User.user_id.in_(deletion_ledger)));self.db.flush()
        self.assertIsNone(self.db.execute(select(User.user_id).where(User.user_id==owner_id)).scalar_one_or_none())
        self.assertEqual(unrelated_fingerprint(),before)



if __name__ == '__main__':unittest.main()
