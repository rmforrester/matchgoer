"""Disposable PostgreSQL only; existing fake private Storage and provider identity."""
import unittest
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi import Response
from sqlalchemy.exc import IntegrityError
from backend.tests import test_terraces_api as fixtures
from identity import ResolvedIdentity
from models import Fixture, MatchBoardPost, TerracePhoto, VenueVisit
import account_deletion as deletion
import supporter_blocks as blocks
import terraces_api
import terraces_service


class Build8IntegrationTests(unittest.TestCase):
    setUp = fixtures.PhotoApiTests.setUp
    tearDown = fixtures.PhotoApiTests.tearDown
    submit = fixtures.PhotoApiTests.submit

    def actor(self, user):
        return ResolvedIdentity(user.user_id, "registered", True, "bearer")

    def test_block_filters_lists_detail_and_counts_without_removing_photos(self):
        photo_id = self.submit()["photo_id"]
        terraces_service.approve(self.db, "Bearer synthetic", photo_id)
        before = dict(self.storage.objects)
        viewer = self.actor(self.other)
        blocks.block_author(self.db, viewer, "photo", photo_id)
        blocks.block_author(self.db, viewer, "photo", photo_id)
        self.assertEqual(self.db.query(blocks.SupporterBlock).count(), 1)
        self.assertEqual(terraces_service.public_page(self.db, self.storage, viewer_user_id=self.other.user_id)["photos"], [])
        self.assertEqual(len(terraces_service.public_page(self.db, self.storage)["photos"]), 1)
        row = self.db.get(TerracePhoto, photo_id)
        self.assertEqual(terraces_service.public_matchday_metadata(self.db, row, self.other.user_id), {})
        self.assertEqual(self.storage.objects, before)
        self.assertEqual(self.db.get(TerracePhoto, photo_id).status, "APPROVED")
        self.assertEqual(self.db.get(VenueVisit, self.visit.visit_id).user_id, self.owner.user_id)

    def test_moderator_private_read_is_not_replaced_by_public_eligibility(self):
        self.visit = VenueVisit(user_id=self.other.user_id, venue_id=self.venue.venue_id, source="manual")
        self.db.add(self.visit); self.db.flush()
        self.provider.subject = str(self.other.user_id)
        with patch.dict("os.environ", {"TERRACES_UPLOAD_USER_IDS": str(self.other.user_id)}):
            photo_id = self.submit(moderator=True)["photo_id"]
        self.provider.subject = str(self.owner.user_id)
        result = terraces_api.photo_detail(photo_id, Response(), "Bearer synthetic")
        self.assertEqual(result["status"], "PENDING")

    def test_web_board_posts_publish_without_a_moderation_column(self):
        import main
        from schemas import MatchBoardPostCreate
        self.assertNotIn("moderation_status", MatchBoardPost.__table__.columns)
        fixture = self.db.get(Fixture, 900000001)
        fixture.status = "NS"; fixture.fixture_date = datetime.now(timezone.utc) + timedelta(days=1)
        self.db.commit()
        with patch.object(main, "SessionLocal", return_value=self.db), patch.object(self.db, "close"):
            created = main.create_board_post(fixture.fixture_id, MatchBoardPostCreate(body="Synthetic web advice"), self.actor(self.owner))
            other = main.get_fixture_social(fixture.fixture_id, self.actor(self.other))
            self.assertEqual(other["posts"][0]["body"], "Synthetic web advice")
            self.assertNotIn("pending_moderation", other["posts"][0])
            self.assertEqual(self.db.get(MatchBoardPost, created["post_id"]).author_user_id, self.owner.user_id)

    def test_migrated_request_table_preserves_owner_and_blocks_premature_completion(self):
        row = deletion.request_deletion(self.db, self.actor(self.owner), True)
        deletion.issue_receipt(row)
        self.db.commit()
        again = deletion.request_deletion(self.db, self.actor(self.owner), True)
        self.assertEqual(again.request_id, row.request_id)
        self.assertIsNone(deletion.latest(self.db, self.other.user_id))
        row.status = "completed"; row.completed_at = datetime.now(timezone.utc)
        with self.assertRaises(IntegrityError):
            self.db.flush()
        self.db.rollback()

    def test_deadline_constraint_does_not_depend_on_database_daylight_saving_timezone(self):
        from sqlalchemy import text
        self.db.execute(text("SET LOCAL TIME ZONE 'America/New_York'"))
        requested = datetime(2026, 10, 29, 12, tzinfo=timezone.utc)
        row = deletion.request_deletion(self.db, self.actor(self.owner), True, requested)
        self.db.flush()
        self.assertEqual(row.due_at, requested + timedelta(days=7))


if __name__ == "__main__":
    unittest.main()
