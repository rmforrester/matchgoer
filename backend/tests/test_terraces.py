import unittest
from datetime import datetime, timedelta, timezone
from io import BytesIO
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException
from PIL import Image
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, DBAPIError
from sqlalchemy.orm import Session

from database import engine
from models import User, UserIdentity, Venue, VenueVisit, Fixture, Team, TerracePhoto, TerracePhotoEvent
from terraces import reserve_photo, require_verified_account, require_moderator, storage_deletion_candidates, storage_deletion_receipts, may_read_photo, PhotoActor, CONSENT_VERSION
from terraces_images import SanitisedPhoto, ImageVariant
from hashlib import sha256


class PhotoFoundationTests(unittest.TestCase):
    def setUp(self):
        self.db = Session(engine)
        self.now = datetime.now(timezone.utc)
        self.owner = User(account_status="registered", is_anonymous=False)
        self.other = User(account_status="registered", is_anonymous=False)
        self.guest = User(account_status="anonymous", is_anonymous=True)
        self.db.add_all([self.owner, self.other, self.guest]); self.db.flush()
        for user in (self.owner, self.other):
            self.db.add(UserIdentity(user_id=user.user_id, issuer="https://synthetic.test/auth/v1",
                                    subject=str(user.user_id), email_verified_at=self.now))
        self.venue = Venue(name="Synthetic football ground", country="Test")
        self.wrong = Venue(name="Different canonical ground", country="Test")
        self.db.add_all([self.venue, self.wrong]); self.db.flush()
        self.visit = VenueVisit(user_id=self.owner.user_id, venue_id=self.venue.venue_id,
                                fixture_id=None, visit_date=None, source="manual")
        self.db.add(self.visit); self.db.flush()
        self.provider = type("Verified", (), {"issuer": "https://synthetic.test/auth/v1", "subject": str(self.owner.user_id)})()
        self.mock = patch("terraces.verify_claim_provider_identity", return_value=self.provider)
        self.verify = self.mock.start()

    def tearDown(self):
        self.mock.stop(); self.db.rollback(); self.db.close()

    def photo(self, colour="red"):
        out = BytesIO(); Image.new("RGB", (20, 16), colour).save(out, format="JPEG")
        # Persistence tests use an independent synthetic processed-image fixture;
        # real decoding/metadata validation lives in test_terraces_images.
        data = out.getvalue()
        return SanitisedPhoto(sha256(data).hexdigest(), len(data), ImageVariant(data, 20, 16), ImageVariant(data, 20, 16))

    def reserve(self, **overrides):
        args = dict(visit_id=self.visit.visit_id, photo=self.photo(), submission_key=str(uuid4()),
                    consent_version=CONSENT_VERSION, public_consent=True, rights_acknowledged=True)
        args.update(overrides)
        return reserve_photo(self.db, "Bearer synthetic", **args)

    def test_historical_context_derived_and_pending_private(self):
        row = self.reserve()
        self.assertEqual(row.owner_user_id, self.owner.user_id)
        self.assertEqual(row.venue_id, self.venue.venue_id)
        self.assertIsNone(row.fixture_id)
        self.assertEqual(row.status, "PENDING")
        self.assertIsNone(row.published_at)
        self.assertTrue(row.display_key.startswith("photos/"))
        self.assertRegex(row.display_key, r"^photos/[0-9a-f]{32}/display\.jpg$")
        self.assertEqual(self.db.query(TerracePhotoEvent).count(), 1)

    def test_retry_idempotency_and_conflicting_retry(self):
        key = str(uuid4()); one = self.reserve(submission_key=key)
        self.assertEqual(self.reserve(submission_key=key).photo_id, one.photo_id)
        self.assertEqual(self.db.query(TerracePhoto).count(), 1)
        with self.assertRaises(HTTPException): self.reserve(submission_key=key, caption="Different request")

    def test_three_live_photos_and_duplicate_limit(self):
        self.reserve()
        with self.assertRaises(HTTPException): self.reserve()
        self.reserve(photo=self.photo("blue")); self.reserve(photo=self.photo("green"))
        with self.assertRaises(HTTPException): self.reserve(photo=self.photo("yellow"))
        self.assertEqual(self.db.query(TerracePhoto).count(), 3)

    def test_verified_gate_guest_missing_identity_and_blocked_account(self):
        self.verify.side_effect = HTTPException(403, "Unverified")
        with self.assertRaises(HTTPException): self.reserve()
        self.verify.side_effect = None
        for user in (self.guest, self.owner):
            self.provider.subject = str(user.user_id)
            if user is self.owner: user.account_status = "suspended"; self.db.flush()
            with self.assertRaises(HTTPException): require_verified_account(self.db, "Bearer synthetic")
        self.assertEqual(self.db.query(TerracePhoto).count(), 0)

    def test_other_owner_cannot_submit_and_consent_caption_checked(self):
        self.provider.subject = str(self.other.user_id)
        with self.assertRaises(HTTPException): self.reserve()
        self.provider.subject = str(self.owner.user_id)
        for args in ({"public_consent": False}, {"rights_acknowledged": False},
                     {"caption": "x" * 201}, {"consent_version": "unapproved"}, {"submission_key": "bad"}):
            with self.subTest(args=args), self.assertRaises(HTTPException): self.reserve(**args)

    def test_moderator_is_internal_id_and_fails_closed(self):
        for permission in (None, 0, str(self.owner.user_id), True, self.other.user_id):
            with self.subTest(permission=permission), self.assertRaises(HTTPException):
                require_moderator(self.db, "Bearer synthetic", moderator_user_id=permission)
        self.assertEqual(require_moderator(self.db, "Bearer synthetic", moderator_user_id=self.owner.user_id).user_id, self.owner.user_id)

    def test_database_canonical_context_cannot_be_spoofed(self):
        row = self.reserve()
        with self.assertRaises(DBAPIError):
            with self.db.begin_nested():
                self.db.execute(text("UPDATE terrace_photos SET venue_id=:wrong WHERE photo_id=:id"), {"wrong": self.wrong.venue_id, "id": row.photo_id})
        self.db.expire_all(); self.assertEqual(self.db.get(TerracePhoto, row.photo_id).venue_id, self.venue.venue_id)

    def test_fixture_identity_dispute_rejected(self):
        home = Team(team_name="Synthetic home"); away = Team(team_name="Synthetic away")
        self.db.add_all([home, away]); self.db.flush()
        fixture = Fixture(fixture_id=800000100, home_team_id=home.team_id, away_team_id=away.team_id,
                          home_team=home.team_name, away_team=away.team_name, fixture_date=self.now,
                          venue_id=self.wrong.venue_id)
        self.db.add(fixture); self.db.flush()
        self.visit.fixture_id = fixture.fixture_id; self.db.flush()
        with self.assertRaises(HTTPException): self.reserve()

    def test_deleted_attendance_unpublishes_without_invented_relink(self):
        row = self.reserve()
        row.status = "APPROVED"; row.approved_at = self.now; row.published_at = self.now; self.db.flush()
        self.db.delete(self.visit); self.db.flush(); self.db.expire_all()
        saved = self.db.get(TerracePhoto, row.photo_id)
        self.assertEqual(saved.status, "REMOVED"); self.assertIsNone(saved.published_at)
        self.assertIsNone(saved.visit_id); self.assertEqual(saved.owner_user_id, self.owner.user_id)
        self.assertIn(saved, storage_deletion_candidates(self.db))

    def test_account_deletion_cascades_contribution_but_retains_purge_receipt(self):
        row = self.reserve(); display = row.display_key
        self.db.delete(self.visit); self.db.flush()
        self.db.delete(self.owner); self.db.flush(); self.db.expire_all()
        self.assertEqual(self.db.query(TerracePhoto).count(), 0)
        event = self.db.query(TerracePhotoEvent).filter_by(event_type="STORAGE_DELETE_REQUIRED").one()
        self.assertIsNone(event.photo_id); self.assertEqual(event.payload["display_key"], display)
        self.assertEqual(len(storage_deletion_receipts(self.db)), 1)

    def test_rejected_seven_day_retention_and_documented_dispute(self):
        row = self.reserve(); row.status="REJECTED"; row.rejected_at=self.now; self.db.flush()
        self.assertEqual(storage_deletion_candidates(self.db, now=self.now+timedelta(days=6)), [])
        self.assertEqual(len(storage_deletion_candidates(self.db, now=self.now+timedelta(days=7))), 1)
        row.dispute_reason="Documented copyright complaint"; self.db.flush()
        self.assertEqual(storage_deletion_candidates(self.db, now=self.now+timedelta(days=30)), [])

    def test_attendance_dedup_delete_unpublishes_and_does_not_transfer_ownership(self):
        row = self.reserve(); kept = VenueVisit(user_id=self.owner.user_id, venue_id=self.venue.venue_id,
                                               visit_date=None, source="manual")
        self.db.add(kept); self.db.flush(); self.db.delete(self.visit); self.db.flush(); self.db.expire_all()
        self.assertEqual(self.db.get(TerracePhoto, row.photo_id).status, "REMOVED")
        self.assertIsNone(self.db.get(TerracePhoto, row.photo_id).visit_id)
        self.assertIsNotNone(self.db.get(VenueVisit, kept.visit_id))

    def test_fourth_direct_database_insert_rejected_and_rollback_keeps_three(self):
        one=self.reserve(); self.reserve(photo=self.photo("blue")); self.reserve(photo=self.photo("green"))
        with self.assertRaises(DBAPIError):
            with self.db.begin_nested():
                values = dict(one.__dict__); values.pop("_sa_instance_state"); values.pop("photo_id")
                values.update(submission_key=str(uuid4()), source_sha256="f"*64,
                              display_key=f"photos/{uuid4().hex}/display.jpg")
                values["thumbnail_key"] = values["display_key"].replace("display.jpg", "thumbnail.jpg")
                self.db.add(TerracePhoto(**values)); self.db.flush()
        self.assertEqual(self.db.query(TerracePhoto).count(), 3)

    def test_private_access_fails_closed_and_public_requires_approval_and_publication(self):
        row=self.reserve()
        self.assertFalse(may_read_photo(row))
        self.assertFalse(may_read_photo(row,PhotoActor(self.other.user_id)))
        self.assertTrue(may_read_photo(row,PhotoActor(self.owner.user_id)))
        self.assertTrue(may_read_photo(row,PhotoActor(self.other.user_id),moderator_user_id=self.other.user_id))
        row.status="APPROVED";row.approved_at=self.now
        self.assertFalse(may_read_photo(row))
        row.published_at=self.now
        self.assertTrue(may_read_photo(row))
        row.status="REMOVED";row.removed_at=self.now;row.published_at=None
        self.assertFalse(may_read_photo(row,PhotoActor(self.owner.user_id)))
