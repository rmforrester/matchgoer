import time
import unittest

from fastapi import HTTPException
from sqlalchemy.orm import Session

from database import engine
from identity import ResolvedIdentity
from main import get_account_context, update_registered_profile
from models import AnonymousSession, Fixture, InterestedFixture, SocialEvent, User, UserProfile
from schemas import ProfileUpdate


class AccountUxContractTests(unittest.TestCase):
    def setUp(self):
        self.db = Session(bind=engine)
        self.user_ids = []

    def tearDown(self):
        self.db.rollback()
        for user_id in reversed(self.user_ids):
            cleanup = Session(bind=engine)
            try:
                cleanup.query(InterestedFixture).filter_by(user_id=user_id).delete()
                cleanup.query(SocialEvent).filter_by(user_id=user_id).delete()
                cleanup.query(UserProfile).filter_by(user_id=user_id).delete()
                cleanup.query(AnonymousSession).filter_by(user_id=user_id).delete()
                cleanup.query(User).filter_by(user_id=user_id).delete()
                cleanup.commit()
            finally:
                cleanup.close()
        self.db.close()

    def user(self, *, registered=False):
        user = User(
            is_anonymous=not registered,
            account_status="registered" if registered else "anonymous",
        )
        self.db.add(user)
        self.db.commit()
        self.user_ids.append(user.user_id)
        return user

    def test_account_context_distinguishes_empty_shell_from_meaningful_activity(self):
        registered = self.user(registered=True)
        anonymous = self.user()
        session_id = f"phase4e-context-{time.time_ns()}"
        self.db.add(AnonymousSession(session_id=session_id, user_id=anonymous.user_id))
        self.db.commit()
        identity = ResolvedIdentity(registered.user_id, "registered", True, "bearer", "issuer", "subject")

        empty = get_account_context(identity=identity, session_id=session_id)
        self.assertTrue(empty["anonymous_session_present"])
        self.assertFalse(empty["anonymous_activity"])

        fixture_id = self.db.query(Fixture.fixture_id).first()[0]
        self.db.add(SocialEvent(user_id=anonymous.user_id, fixture_id=fixture_id, event_type="fixture_view"))
        self.db.commit()
        incidental = get_account_context(identity=identity, session_id=session_id)
        self.assertFalse(incidental["anonymous_activity"])

        self.db.add(InterestedFixture(user_id=anonymous.user_id, fixture_id=fixture_id))
        self.db.commit()
        meaningful = get_account_context(identity=identity, session_id=session_id)
        self.assertTrue(meaningful["anonymous_activity"])

    def test_registered_profile_upsert_and_case_insensitive_username_conflict(self):
        first = self.user(registered=True)
        second = self.user(registered=True)
        first_identity = ResolvedIdentity(first.user_id, "registered", True, "bearer")
        second_identity = ResolvedIdentity(second.user_id, "registered", True, "bearer")
        payload = ProfileUpdate(
            username="GroundHopper_1",
            display_name="Ground Hopper",
            supported_club=None,
            broad_location="London",
            bio="Away days and old stands.",
        )
        created = update_registered_profile(data=payload, identity=first_identity)
        self.assertTrue(created["profile_complete"])
        self.assertEqual(created["username"], "GroundHopper_1")

        with self.assertRaises(HTTPException) as raised:
            update_registered_profile(
                data=ProfileUpdate(
                    username="groundhopper_1",
                    display_name="Another Supporter",
                    supported_club=None,
                    broad_location=None,
                    bio=None,
                ),
                identity=second_identity,
            )
        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(raised.exception.detail["code"], "USERNAME_UNAVAILABLE")

    def test_username_character_rule_and_registered_requirement(self):
        anonymous = self.user()
        with self.assertRaises(HTTPException) as raised:
            update_registered_profile(
                data=ProfileUpdate(username="valid_name", display_name="Valid Name"),
                identity=ResolvedIdentity(anonymous.user_id, "anonymous", False, "anonymous"),
            )
        self.assertEqual(raised.exception.detail["code"], "REGISTERED_ACCOUNT_REQUIRED")

        registered = self.user(registered=True)
        with self.assertRaises(HTTPException) as invalid:
            update_registered_profile(
                data=ProfileUpdate(username="bad-name", display_name="Valid Name"),
                identity=ResolvedIdentity(registered.user_id, "registered", True, "bearer"),
            )
        self.assertEqual(invalid.exception.detail["code"], "INVALID_USERNAME")


if __name__ == "__main__":
    unittest.main()
