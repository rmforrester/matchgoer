import time
import unittest
from datetime import date, datetime, timedelta, timezone

from database import SessionLocal
from main import get_away_day_score, get_venue_guide, get_venue_tips
from models import AwayDayReview, Fixture, MatchdayTip, User, Venue, VenueGuideFact


class VenueGuideTests(unittest.TestCase):
    def setUp(self):
        stamp = time.time_ns() % 100_000_000
        self.fixture_id = 1_700_000_000 + stamp
        self.other_fixture_id = self.fixture_id + 1
        db = SessionLocal()
        try:
            self.venue = Venue(
                name="Stadion Suche Stawy (development proof)",
                address="Development-only address",
                city="Krakow development fixture",
                country="Test",
                latitude=50.066111,
                longitude=20.057222,
            )
            self.other_venue = Venue(name="Empty guide development venue", city="Test", country="Test")
            db.add_all([self.venue, self.other_venue])
            db.flush()
            self.venue_id, self.other_venue_id = self.venue.venue_id, self.other_venue.venue_id
            fixture_date = datetime.now(timezone.utc) + timedelta(days=30)
            db.add_all([
                Fixture(fixture_id=self.fixture_id, fixture_date=fixture_date, venue_id=self.venue_id, home_team="Hutnik development", away_team="Test opposition", league_name="KNOW proof"),
                Fixture(fixture_id=self.other_fixture_id, fixture_date=fixture_date, venue_id=self.other_venue_id, home_team="No guide", away_team="Test opposition", league_name="KNOW proof"),
            ])
            today = date.today()
            facts = [
                self.fact("getting_there", "Transport", "Development transport guidance", "matchgoer_research", reviewed_at=today),
                self.fact("tickets_entry", "Tickets", "Development ticket guidance", "official", reviewed_at=today, source_url="https://example.test/tickets"),
                self.fact("before_match", "Pre-match", "Development pre-match guidance", "supporter", reviewed_at=today),
                self.fact("at_ground", "Facilities", "Development at-ground guidance", "official", reviewed_at=today),
                self.fact("getting_back", "Return journey", "Development return guidance", "matchgoer_research", reviewed_at=today),
                self.fact("at_ground", "Draft fact", "Must not publish", "official", status="draft"),
                self.fact("at_ground", "Archived fact", "Must not publish", "official", status="archived"),
                self.fact("tickets_entry", "Conflict", "Research loses deterministically", "matchgoer_research", reviewed_at=today),
                self.fact("tickets_entry", "Conflict", "Official wins deterministically", "official", reviewed_at=today - timedelta(days=1)),
                self.fact("at_ground", "Needs review", "Visible with review warning", "official", status="needs_review", reviewed_at=today),
                self.fact("getting_back", "Expired", "Visible as expired", "official", reviewed_at=today - timedelta(days=10), expires_at=today - timedelta(days=1)),
            ]
            db.add_all(facts)
            self.user = User(is_anonymous=False, account_status="registered")
            db.add(self.user)
            db.flush()
            db.add(MatchdayTip(venue_id=self.venue_id, tip="Existing development supporter tip"))
            db.add(AwayDayReview(user_id=self.user.user_id, venue_id=self.venue_id, overall_score=8, recommend=True))
            db.commit()
            self.user_id = self.user.user_id
        finally:
            db.close()

    def fact(self, section, topic, content, source_type, *, status="current", reviewed_at=None, source_url=None, expires_at=None):
        return VenueGuideFact(
            venue_id=self.venue_id,
            section=section,
            topic=topic,
            content=content,
            source_type=source_type,
            source_url=source_url,
            reviewed_at=reviewed_at,
            confidence="medium",
            status=status,
            expires_at=expires_at,
        )

    def tearDown(self):
        db = SessionLocal()
        try:
            db.query(AwayDayReview).filter(AwayDayReview.venue_id.in_([self.venue_id, self.other_venue_id])).delete(synchronize_session=False)
            db.query(MatchdayTip).filter(MatchdayTip.venue_id.in_([self.venue_id, self.other_venue_id])).delete(synchronize_session=False)
            db.query(VenueGuideFact).filter(VenueGuideFact.venue_id.in_([self.venue_id, self.other_venue_id])).delete(synchronize_session=False)
            db.query(Fixture).filter(Fixture.fixture_id.in_([self.fixture_id, self.other_fixture_id])).delete(synchronize_session=False)
            db.query(User).filter(User.user_id == self.user_id).delete(synchronize_session=False)
            db.query(Venue).filter(Venue.venue_id.in_([self.venue_id, self.other_venue_id])).delete(synchronize_session=False)
            db.commit()
        finally:
            db.close()

    def test_hutnik_development_proof_groups_all_five_sections(self):
        guide = get_venue_guide(self.venue_id)
        self.assertEqual([section["key"] for section in guide["sections"]], [
            "getting_there", "tickets_entry", "before_match", "at_ground", "getting_back"
        ])
        self.assertTrue(guide["has_current_information"])

    def test_provenance_publication_staleness_and_conflicts(self):
        guide = get_venue_guide(self.venue_id)
        facts = {fact["topic"]: fact for section in guide["sections"] for fact in section["facts"]}
        self.assertEqual(facts["Tickets"]["provenance"]["label"], "Official")
        self.assertEqual(facts["Transport"]["provenance"]["label"], "Researched by Matchgoer")
        self.assertEqual(facts["Pre-match"]["provenance"]["label"], "Supporter tip")
        self.assertIsNone(facts["Pre-match"]["provenance"]["source_url"])
        self.assertNotIn("Draft fact", facts)
        self.assertNotIn("Archived fact", facts)
        self.assertEqual(facts["Needs review"]["freshness"], "needs_review")
        self.assertEqual(facts["Expired"]["freshness"], "expired")
        self.assertEqual(facts["Conflict"]["content"], "Official wins deterministically")

    def test_venue_isolation_and_empty_guide(self):
        guide = get_venue_guide(self.other_venue_id)
        self.assertEqual(guide, {"venue_id": self.other_venue_id, "club_venue_id": None, "has_current_information": False, "sections": [], "before_match": []})

    def test_existing_tips_and_reviews_are_unchanged(self):
        tips = get_venue_tips(self.venue_id)
        score = get_away_day_score(self.venue_id)
        self.assertEqual([tip.tip for tip in tips], ["Existing development supporter tip"])
        self.assertEqual(score["review_count"], 1)
        self.assertEqual(score["away_day_score"], 8.0)


if __name__ == "__main__":
    unittest.main()
