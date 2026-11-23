import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from fastapi import HTTPException
from fastapi import Response
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import account_deletion as deletion
from identity import ResolvedIdentity, required_privacy_identity
from models import User, VenueVisit, InterestedFixture, AwayDayReview, SocialEvent


class DeletionRequestTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        User.__table__.create(self.engine)
        for model in (VenueVisit, InterestedFixture, AwayDayReview, SocialEvent): model.__table__.create(self.engine)
        deletion.AccountDeletionRequest.__table__.create(self.engine)
        self.db = Session(self.engine)
        self.db.add_all([User(user_id=1, account_status="registered", is_anonymous=False),
                         User(user_id=2, account_status="registered", is_anonymous=False)])
        self.db.commit()
        self.identity = ResolvedIdentity(1, "registered", True, "bearer")
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.db.close)

    def test_confirmed_owner_and_exact_seven_day_deadline(self):
        now = datetime(2026, 11, 1, 12, tzinfo=timezone.utc)
        row = deletion.request_deletion(self.db, self.identity, True, now)
        self.assertEqual(row.user_id, 1)
        self.assertEqual(row.due_at, now + timedelta(days=7))
        self.assertEqual(row.status, "pending")
        self.assertIsNone(row.completed_at)
        self.assertEqual(self.db.get(User, 1).account_status, "registered")
        self.assertEqual(self.db.query(User).count(), 2)

    def test_repeated_submission_reuses_pending_request(self):
        row = deletion.request_deletion(self.db, self.identity, True)
        self.db.commit()
        second = deletion.request_deletion(self.db, self.identity, True)
        self.assertEqual(row.request_id, second.request_id)
        self.assertEqual(self.db.query(deletion.AccountDeletionRequest).count(), 1)

    def test_other_owner_cannot_read_request(self):
        deletion.request_deletion(self.db, self.identity, True)
        self.assertIsNone(deletion.latest(self.db, 2))

    def test_confirmation_required(self):
        with self.assertRaises(HTTPException) as error:
            deletion.request_deletion(self.db, self.identity, False)
        self.assertEqual(error.exception.status_code, 422)
        self.assertEqual(self.db.query(deletion.AccountDeletionRequest).count(), 0)

    def test_inactive_or_unknown_owner_rejected(self):
        for status in ("merged", "deleted"):
            self.db.get(User, 1).account_status = status
            self.db.flush()
            with self.assertRaises(HTTPException):
                deletion.request_deletion(self.db, self.identity, True)
        with self.assertRaises(HTTPException):
            deletion.request_deletion(self.db, ResolvedIdentity(999, "registered", True, "bearer"), True)

    def test_request_body_cannot_choose_owner_or_coerce_confirmation(self):
        from pydantic import ValidationError
        for body in ({"confirmed": True, "user_id": 2}, {"confirmed": "true"}, {}):
            with self.assertRaises(ValidationError):
                deletion.Confirmation(**body)

    def test_queue_rejects_non_moderator_before_reading(self):
        db = MagicMock()
        with patch.object(deletion, "SessionLocal") as factory, patch.object(deletion, "require_moderator", side_effect=HTTPException(403, "Forbidden")):
            factory.return_value.__enter__.return_value = db
            with self.assertRaises(HTTPException) as error:
                deletion.pending_requests(Response(), None)
        self.assertEqual(error.exception.status_code, 403)
        db.query.assert_not_called()

    def test_receipt_is_unpredictable_and_only_its_hash_is_stored(self):
        row = deletion.request_deletion(self.db, self.identity, True)
        receipt = deletion.issue_receipt(row)
        import hashlib
        self.assertEqual(len(receipt), 43)
        self.assertEqual(row.receipt_hash, hashlib.sha256(receipt.encode()).hexdigest())
        self.assertNotEqual(row.receipt_hash, receipt)
        self.assertNotIn("receipt_hash", deletion.payload(row))

    def test_guest_request_does_not_require_email_or_claim_history(self):
        self.db.get(User, 1).account_status = "anonymous"
        self.db.get(User, 1).is_anonymous = True
        guest = ResolvedIdentity(1, "anonymous", False, "cookie")
        row = deletion.request_deletion(self.db, guest, True)
        self.assertEqual(row.user_id, 1)
        self.assertEqual(self.db.get(User, 1).account_status, "anonymous")

    def test_receipt_schema_rejects_urls_and_identifiers(self):
        from pydantic import ValidationError
        for value in ("https://example.test/token", "11", "", "x" * 44):
            with self.assertRaises(ValidationError):
                deletion.Receipt(receipt=value)

    def test_guest_account_mode_change_is_rejected_before_database_access(self):
        for identity, guest in [(self.identity, True), (ResolvedIdentity(1, "anonymous", False, "cookie"), False)]:
            with self.subTest(guest=guest), patch.object(deletion, "SessionLocal") as factory:
                with self.assertRaises(HTTPException) as error:
                    deletion.create_request(deletion.Confirmation(confirmed=True, guest_history=guest), Response(), identity, None)
                self.assertEqual(error.exception.status_code, 409)
                factory.assert_not_called()

    def test_routes_require_existing_identity_dependency(self):
        for route in deletion.router.routes:
            if route.path.endswith("/deletion-request"):
                self.assertTrue(any(dependency.call is required_privacy_identity for dependency in route.dependant.dependencies))


if __name__ == "__main__":
    unittest.main()
