import threading
import time
import unittest
from datetime import date, datetime, timezone

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from sqlalchemy.orm import Session

from account_claim import claim_anonymous_user
from database import engine
from identity import ResolvedIdentity, SupabaseAuthConfig, VerifiedProviderIdentity, resolve_identity
from main import get_fixture_social, update_meeting_intent
from models import (
    AnonymousSession,
    AwayDayReview,
    Fixture,
    FixtureMeetingIntent,
    InterestedFixture,
    MatchBoardPost,
    MatchBoardReport,
    MatchdayTip,
    SocialEvent,
    User,
    UserIdentity,
    UserProfile,
    VenueVisit,
)
from schemas import MeetingIntentUpdate


ISSUER = "https://phase4c.test/auth/v1"
AUDIENCE = "authenticated"


class StaticSigningKey:
    def __init__(self, key):
        self.key = key


class StaticJwksClient:
    def __init__(self, key):
        self.key = key

    def get_signing_key_from_jwt(self, _token):
        return StaticSigningKey(self.key)


def provider(subject):
    return VerifiedProviderIdentity(
        issuer=ISSUER,
        subject=subject,
        email=f"{subject}@example.test",
        email_verified_at=datetime.now(timezone.utc),
        provider="email",
    )


class AccountClaimTests(unittest.TestCase):
    def setUp(self):
        self.db = Session(bind=engine)
        fixture = self.db.query(Fixture).filter(Fixture.venue_id.is_not(None)).first()
        if fixture is None:
            self.skipTest("A fixture linked to a venue is required")
        self.fixture_id = fixture.fixture_id
        self.venue_id = fixture.venue_id
        self.created_users = []

    def tearDown(self):
        self.db.rollback()
        for user_id in reversed(self.created_users):
            cleanup = Session(bind=engine)
            try:
                post_ids = [row[0] for row in cleanup.query(MatchBoardPost.post_id).filter(MatchBoardPost.author_user_id == user_id)]
                cleanup.query(MatchBoardReport).filter(
                    (MatchBoardReport.reporter_user_id == user_id)
                    | (MatchBoardReport.post_id.in_(post_ids) if post_ids else False)
                ).delete(synchronize_session=False)
                cleanup.query(FixtureMeetingIntent).filter(FixtureMeetingIntent.user_id == user_id).delete()
                cleanup.query(MatchBoardPost).filter(MatchBoardPost.author_user_id == user_id).delete()
                cleanup.query(SocialEvent).filter(SocialEvent.user_id == user_id).delete()
                cleanup.query(MatchdayTip).filter(MatchdayTip.author_user_id == user_id).delete()
                cleanup.query(InterestedFixture).filter(InterestedFixture.user_id == user_id).delete()
                cleanup.query(VenueVisit).filter(VenueVisit.user_id == user_id).delete()
                cleanup.query(AwayDayReview).filter(AwayDayReview.user_id == user_id).delete()
                cleanup.query(UserProfile).filter(UserProfile.user_id == user_id).delete()
                cleanup.query(UserIdentity).filter(UserIdentity.user_id == user_id).delete()
                cleanup.query(AnonymousSession).filter(AnonymousSession.user_id == user_id).delete()
                cleanup.query(User).filter(User.user_id == user_id).delete()
                cleanup.commit()
            finally:
                cleanup.close()
        self.db.close()

    def new_anonymous(self, suffix=None):
        suffix = suffix or str(time.time_ns())
        user = User(is_anonymous=True, account_status="anonymous")
        self.db.add(user)
        self.db.flush()
        session = AnonymousSession(session_id=f"phase4c-{suffix}", user_id=user.user_id)
        self.db.add(session)
        self.db.commit()
        self.created_users.append(user.user_id)
        return user.user_id, session.session_id

    def claim(self, session_id, subject="new-supporter", **kwargs):
        db = Session(bind=engine)
        try:
            return claim_anonymous_user(
                db,
                session_id=session_id,
                provider_identity=provider(subject),
                **kwargs,
            )
        finally:
            db.close()

    def assert_error(self, status, code, callback):
        with self.assertRaises(HTTPException) as raised:
            callback()
        self.assertEqual(raised.exception.status_code, status)
        self.assertEqual(raised.exception.detail["code"], code)

    def test_claim_preserves_same_owner_and_all_phase_4c_owned_rows(self):
        user_id, session_id = self.new_anonymous("preserve")
        profile = UserProfile(user_id=user_id, display_name="Phase C", username="phase-c")
        interest = InterestedFixture(user_id=user_id, fixture_id=self.fixture_id)
        self.db.add_all([profile, interest])
        self.db.flush()
        self.db.add_all(
            [
                FixtureMeetingIntent(user_id=user_id, fixture_id=self.fixture_id),
                VenueVisit(user_id=user_id, venue_id=self.venue_id, fixture_id=self.fixture_id, visit_date=date.today(), source="fixture"),
                AwayDayReview(user_id=user_id, venue_id=self.venue_id, fixture_id=self.fixture_id, recommend=True, overall_score=4),
                MatchdayTip(venue_id=self.venue_id, author_user_id=user_id, tip="Phase 4C preservation tip"),
                SocialEvent(user_id=user_id, fixture_id=self.fixture_id, event_type="interested_added"),
            ]
        )
        post = MatchBoardPost(fixture_id=self.fixture_id, author_user_id=user_id, body="Phase 4C preservation post")
        self.db.add(post)
        self.db.flush()
        self.db.add(MatchBoardReport(reporter_user_id=user_id, post_id=post.post_id, reason="other"))
        self.db.commit()

        owned_models = (UserProfile, InterestedFixture, FixtureMeetingIntent, VenueVisit, AwayDayReview, MatchdayTip, SocialEvent, MatchBoardPost, MatchBoardReport)
        before = {model.__name__: self._owned_count(model, user_id) for model in owned_models}
        visit_before = self.db.query(VenueVisit).filter_by(user_id=user_id).one()
        review_before = self.db.query(AwayDayReview).filter_by(user_id=user_id).one()
        preserved_values = {
            "visit_id": visit_before.visit_id,
            "visit_fixture_id": visit_before.fixture_id,
            "review_id": review_before.review_id,
            "review_fixture_id": review_before.fixture_id,
            "review_score": review_before.overall_score,
            "review_recommend": review_before.recommend,
        }
        result = self.claim(session_id, "preserved-subject")

        verify = Session(bind=engine)
        try:
            claimed = verify.get(User, user_id)
            session = verify.get(AnonymousSession, session_id)
            mapping = verify.query(UserIdentity).filter_by(issuer=ISSUER, subject="preserved-subject").one()
            self.assertEqual(mapping.user_id, user_id)
            self.assertEqual(claimed.account_status, "registered")
            self.assertFalse(claimed.is_anonymous)
            self.assertIsNotNone(session.revoked_at)
            self.assertEqual(before, {model.__name__: self._owned_count(model, user_id, verify) for model in owned_models})
            visit_after = verify.query(VenueVisit).filter_by(user_id=user_id).one()
            review_after = verify.query(AwayDayReview).filter_by(user_id=user_id).one()
            self.assertEqual(
                preserved_values,
                {
                    "visit_id": visit_after.visit_id,
                    "visit_fixture_id": visit_after.fixture_id,
                    "review_id": review_after.review_id,
                    "review_fixture_id": review_after.fixture_id,
                    "review_score": review_after.overall_score,
                    "review_recommend": review_after.recommend,
                },
            )
            self.assertEqual(result.user_id, user_id)
            self.assertTrue(result.profile_complete)
        finally:
            verify.close()

    def _owned_count(self, model, user_id, db=None):
        db = db or self.db
        column = {
            MatchdayTip: MatchdayTip.author_user_id,
            MatchBoardPost: MatchBoardPost.author_user_id,
            MatchBoardReport: MatchBoardReport.reporter_user_id,
        }.get(model, getattr(model, "user_id", None))
        return db.query(model).filter(column == user_id).count()

    def test_empty_account_claim_and_same_identity_retry_are_idempotent(self):
        user_id, session_id = self.new_anonymous("empty")
        first = self.claim(session_id, "empty-subject")
        retry = self.claim(session_id, "empty-subject")
        self.assertFalse(first.idempotent)
        self.assertTrue(retry.idempotent)
        self.assertEqual(retry.user_id, user_id)
        self.assertEqual(
            self.db.query(UserIdentity).filter_by(issuer=ISSUER, subject="empty-subject").count(),
            1,
        )

    def test_pending_meeting_intent_after_claim_and_onboarding_is_idempotent(self):
        user_id, session_id = self.new_anonymous("pending-meeting")
        self.db.add(InterestedFixture(user_id=user_id, fixture_id=self.fixture_id))
        self.db.commit()

        claimed = self.claim(session_id, "pending-meeting-subject")
        self.assertFalse(claimed.profile_complete)
        profile_db = Session(bind=engine)
        try:
            profile_db.add(UserProfile(user_id=user_id, display_name="Pending Supporter", username="pending_supporter"))
            profile_db.commit()
        finally:
            profile_db.close()

        identity = ResolvedIdentity(user_id, "registered", True, "bearer")
        first = update_meeting_intent(self.fixture_id, MeetingIntentUpdate(open_to_meet=True), identity)
        retry = update_meeting_intent(self.fixture_id, MeetingIntentUpdate(open_to_meet=True), identity)
        refreshed = get_fixture_social(self.fixture_id, identity)

        verify = Session(bind=engine)
        try:
            self.assertTrue(first["open_to_meet"] and first["interested"])
            self.assertTrue(retry["open_to_meet"] and retry["interested"])
            self.assertTrue(refreshed["open_to_meet"] and refreshed["interested"])
            self.assertEqual(verify.query(FixtureMeetingIntent).filter_by(user_id=user_id, fixture_id=self.fixture_id).count(), 1)
            self.assertEqual(verify.query(InterestedFixture).filter_by(user_id=user_id, fixture_id=self.fixture_id).count(), 1)
        finally:
            verify.close()

    def test_identity_mapped_to_another_user_is_never_merged(self):
        user_a, session_a = self.new_anonymous("a")
        user_b = User(is_anonymous=False, account_status="registered", registered_at=datetime.now(timezone.utc))
        self.db.add(user_b)
        self.db.flush()
        self.created_users.append(user_b.user_id)
        self.db.add(UserIdentity(user_id=user_b.user_id, issuer=ISSUER, subject="existing-subject"))
        self.db.commit()
        self.assert_error(409, "IDENTITY_ALREADY_LINKED", lambda: self.claim(session_a, "existing-subject"))
        self.db.expire_all()
        self.assertEqual(self.db.get(User, user_a).account_status, "anonymous")
        self.assertIsNone(self.db.get(AnonymousSession, session_a).revoked_at)

    def test_claimed_account_cannot_claim_a_different_identity(self):
        _user_id, session_id = self.new_anonymous("different")
        self.claim(session_id, "first-subject")
        self.assert_error(409, "ACCOUNT_ALREADY_REGISTERED", lambda: self.claim(session_id, "second-subject"))

    def test_failures_roll_back_mapping_user_and_session_changes(self):
        for stage in ("after_identity", "after_user"):
            user_id, session_id = self.new_anonymous(f"rollback-{stage}")

            def fail(current_stage):
                if current_stage == stage:
                    raise RuntimeError("injected claim failure")

            with self.assertRaises(RuntimeError):
                self.claim(session_id, f"rollback-{stage}", failure_hook=fail)
            check = Session(bind=engine)
            try:
                self.assertEqual(check.get(User, user_id).account_status, "anonymous")
                self.assertTrue(check.get(User, user_id).is_anonymous)
                self.assertIsNone(check.get(AnonymousSession, session_id).revoked_at)
                self.assertEqual(check.query(UserIdentity).filter_by(issuer=ISSUER, subject=f"rollback-{stage}").count(), 0)
            finally:
                check.close()

    def test_concurrent_same_claim_creates_one_mapping(self):
        user_id, session_id = self.new_anonymous("concurrent")
        results = []
        errors = []

        def run():
            try:
                results.append(self.claim(session_id, "concurrent-subject"))
            except Exception as exc:  # recorded for an assertion with useful failure output
                errors.append(exc)

        threads = [threading.Thread(target=run) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(errors, [])
        self.assertEqual(sorted(result.idempotent for result in results), [False, True])
        self.assertEqual(self.db.query(UserIdentity).filter_by(issuer=ISSUER, subject="concurrent-subject", user_id=user_id).count(), 1)

    def test_old_cookie_is_rejected_after_claim(self):
        _user_id, session_id = self.new_anonymous("revoked")
        self.claim(session_id, "revoked-subject")
        check = Session(bind=engine)
        try:
            self.assert_error(
                401,
                "NO_ACTIVE_IDENTITY",
                lambda: resolve_identity(check, authorization=None, session_id=session_id, required=True),
            )
        finally:
            check.close()

    def test_post_claim_bearer_resolves_same_internal_user_and_wins_over_cookie(self):
        user_id, session_id = self.new_anonymous("bearer")
        self.claim(session_id, "bearer-subject")
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        now = int(time.time())
        token = jwt.encode(
            {"iss": ISSUER, "sub": "bearer-subject", "aud": AUDIENCE, "iat": now, "exp": now + 60},
            private_key,
            algorithm="RS256",
            headers={"kid": "phase4c"},
        )
        check = Session(bind=engine)
        try:
            resolved = resolve_identity(
                check,
                authorization=f"Bearer {token}",
                session_id=session_id,
                required=True,
                config=SupabaseAuthConfig(True, ISSUER, AUDIENCE, "https://unused.test/jwks", 1, 60),
                jwks_client=StaticJwksClient(private_key.public_key()),
            )
            self.assertEqual(resolved.user_id, user_id)
            self.assertEqual(resolved.account_status, "registered")
            self.assertEqual(resolved.auth_mode, "bearer")
        finally:
            check.close()


if __name__ == "__main__":
    unittest.main()
