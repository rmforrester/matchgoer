import time
import unittest
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

from database import SessionLocal
from identity import ResolvedIdentity
from main import (
    create_board_post,
    delete_board_post,
    get_fixture_social,
    report_board_post,
    update_meeting_intent,
)
from models import (
    Fixture,
    FixtureMeetingIntent,
    InterestedFixture,
    MatchBoardPost,
    MatchBoardReport,
    SocialEvent,
    User,
    UserProfile,
)
from schemas import MatchBoardPostCreate, MatchBoardReportCreate, MeetingIntentUpdate


class SocialPermissionTests(unittest.TestCase):
    def setUp(self):
        stamp = time.time_ns() % 100_000_000
        self.open_fixture_id = 1_800_000_000 + stamp
        self.closed_fixture_id = self.open_fixture_id + 1
        db = SessionLocal()
        try:
            db.add_all([
                Fixture(
                    fixture_id=self.open_fixture_id,
                    fixture_date=datetime.now(timezone.utc) + timedelta(days=2),
                    status="NS",
                    home_team="Phase 4F Home",
                    away_team="Phase 4F Away",
                    league_name="Phase 4F QA",
                ),
                Fixture(
                    fixture_id=self.closed_fixture_id,
                    fixture_date=datetime.now(timezone.utc) + timedelta(days=2),
                    status="FT",
                    home_team="Closed Home",
                    away_team="Closed Away",
                    league_name="Phase 4F QA",
                ),
            ])
            self.anonymous = User(is_anonymous=True, account_status="anonymous")
            self.owner = User(is_anonymous=False, account_status="registered")
            self.other = User(is_anonymous=False, account_status="registered")
            db.add_all([self.anonymous, self.owner, self.other])
            db.flush()
            db.add_all([
                UserProfile(user_id=self.anonymous.user_id, display_name="Legacy Anonymous", username="legacy_anon"),
                UserProfile(user_id=self.owner.user_id, display_name="Owner Display", username="phase4f_owner"),
                UserProfile(user_id=self.other.user_id, display_name="Other Display", username="phase4f_other"),
            ])
            db.commit()
            self.user_ids = [self.anonymous.user_id, self.owner.user_id, self.other.user_id]
        finally:
            db.close()
        self.anonymous_identity = ResolvedIdentity(self.anonymous.user_id, "anonymous", False, "anonymous")
        self.owner_identity = ResolvedIdentity(self.owner.user_id, "registered", True, "bearer")
        self.other_identity = ResolvedIdentity(self.other.user_id, "registered", True, "bearer")

    def tearDown(self):
        db = SessionLocal()
        try:
            post_ids = [row[0] for row in db.query(MatchBoardPost.post_id).filter(MatchBoardPost.fixture_id.in_([self.open_fixture_id, self.closed_fixture_id]))]
            if post_ids:
                db.query(MatchBoardReport).filter(MatchBoardReport.post_id.in_(post_ids)).delete(synchronize_session=False)
            db.query(MatchBoardPost).filter(MatchBoardPost.fixture_id.in_([self.open_fixture_id, self.closed_fixture_id])).delete(synchronize_session=False)
            db.query(FixtureMeetingIntent).filter(FixtureMeetingIntent.fixture_id.in_([self.open_fixture_id, self.closed_fixture_id])).delete(synchronize_session=False)
            db.query(InterestedFixture).filter(InterestedFixture.fixture_id.in_([self.open_fixture_id, self.closed_fixture_id])).delete(synchronize_session=False)
            db.query(SocialEvent).filter(SocialEvent.fixture_id.in_([self.open_fixture_id, self.closed_fixture_id])).delete(synchronize_session=False)
            db.query(UserProfile).filter(UserProfile.user_id.in_(self.user_ids)).delete(synchronize_session=False)
            db.query(User).filter(User.user_id.in_(self.user_ids)).delete(synchronize_session=False)
            db.query(Fixture).filter(Fixture.fixture_id.in_([self.open_fixture_id, self.closed_fixture_id])).delete(synchronize_session=False)
            db.commit()
        finally:
            db.close()

    def assert_http_error(self, status, callback):
        with self.assertRaises(HTTPException) as raised:
            callback()
        self.assertEqual(raised.exception.status_code, status)
        return raised.exception

    def test_anonymous_can_read_aggregates_and_posts_but_cannot_write(self):
        self.assert_http_error(403, lambda: update_meeting_intent(
            self.open_fixture_id, MeetingIntentUpdate(open_to_meet=True), self.anonymous_identity
        ))
        self.assert_http_error(403, lambda: create_board_post(
            self.open_fixture_id, MatchBoardPostCreate(body="Anonymous post"), self.anonymous_identity
        ))
        board = get_fixture_social(self.open_fixture_id, self.anonymous_identity)
        self.assertEqual(board["open_to_meet_count"], 0)
        self.assertEqual(board["posts"], [])

    def test_registered_meeting_intent_is_idempotent_and_implies_interested(self):
        first = update_meeting_intent(
            self.open_fixture_id, MeetingIntentUpdate(open_to_meet=True), self.owner_identity
        )
        second = update_meeting_intent(
            self.open_fixture_id, MeetingIntentUpdate(open_to_meet=True), self.owner_identity
        )
        self.assertTrue(first["interested"] and first["open_to_meet"])
        self.assertEqual(second["open_to_meet_count"], 1)
        removed = update_meeting_intent(
            self.open_fixture_id, MeetingIntentUpdate(open_to_meet=False), self.owner_identity
        )
        self.assertTrue(removed["interested"])
        self.assertFalse(removed["open_to_meet"])

    def test_registered_post_ownership_reporting_and_anonymous_capability_flags(self):
        created = create_board_post(
            self.open_fixture_id,
            MatchBoardPostCreate(body="Phase 4F ownership post"),
            self.owner_identity,
        )
        post_id = created["post_id"]
        anonymous_board = get_fixture_social(self.open_fixture_id, self.anonymous_identity)
        payload = anonymous_board["posts"][0]
        self.assertEqual(payload["author"]["username"], "phase4f_owner")
        self.assertFalse(payload["can_delete"])
        self.assertFalse(payload["can_report"])
        self.assert_http_error(403, lambda: delete_board_post(post_id, self.anonymous_identity))
        self.assert_http_error(403, lambda: delete_board_post(post_id, self.other_identity))
        self.assert_http_error(400, lambda: report_board_post(
            post_id, MatchBoardReportCreate(reason="other"), self.owner_identity
        ))
        report_board_post(post_id, MatchBoardReportCreate(reason="spam"), self.other_identity)
        self.assert_http_error(409, lambda: report_board_post(
            post_id, MatchBoardReportCreate(reason="spam"), self.other_identity
        ))
        deleted = delete_board_post(post_id, self.owner_identity)
        self.assertTrue(deleted["deleted"])

    def test_completed_board_is_readable_but_rejects_posts(self):
        db = SessionLocal()
        try:
            post = MatchBoardPost(
                fixture_id=self.closed_fixture_id,
                author_user_id=self.owner.user_id,
                body="Preserved completed-match post",
            )
            db.add(post)
            db.commit()
        finally:
            db.close()
        board = get_fixture_social(self.closed_fixture_id, self.anonymous_identity)
        self.assertTrue(board["board_closed"])
        self.assertEqual(board["posts"][0]["body"], "Preserved completed-match post")
        self.assert_http_error(409, lambda: create_board_post(
            self.closed_fixture_id,
            MatchBoardPostCreate(body="Too late"),
            self.owner_identity,
        ))


if __name__ == "__main__":
    unittest.main()
