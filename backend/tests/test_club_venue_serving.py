import time
import unittest
from datetime import date, datetime, timedelta, timezone

from database import SessionLocal
from main import get_venue_guide
from models import ClubVenue, PreMatchSpot, Team, Venue, VenueGuideFact


class ClubVenueServingTests(unittest.TestCase):
    def setUp(self):
        stamp = time.time_ns() % 100_000_000
        self.team_id = 1_800_000_000 + stamp
        self.other_team_id = self.team_id + 1
        db = SessionLocal()
        try:
            venue = Venue(name="Serving integration ground", city="Test", country="Test", latitude=51.0, longitude=-1.0)
            db.add(venue); db.flush(); self.venue_id = venue.venue_id
            db.add_all([Team(team_id=self.team_id, team_name="Serving club", venue_id=self.venue_id, active=True), Team(team_id=self.other_team_id, team_name="Ground-share club", venue_id=self.venue_id, active=True)])
            db.flush()
            primary = ClubVenue(team_id=self.team_id, venue_id=self.venue_id, relationship_type="HOME", status="CURRENT")
            other = ClubVenue(team_id=self.other_team_id, venue_id=self.venue_id, relationship_type="GROUND_SHARE", status="CURRENT")
            db.add_all([primary, other]); db.flush(); self.club_venue_id, self.other_club_venue_id = primary.club_venue_id, other.club_venue_id
            today = date.today()
            db.add_all([
                VenueGuideFact(venue_id=self.venue_id, section="at_ground", topic="Physical access", content="Venue-owned fact", source_type="official", source_url="https://example.test/venue", reviewed_at=today, confidence="high", status="current", display_order=1),
                VenueGuideFact(club_venue_id=self.club_venue_id, section="tickets_entry", topic="official_ticket_portal", content="Use the official club ticket route.", source_type="official", source_url="https://example.test/tickets", reviewed_at=today, confidence="high", status="current", display_order=1),
                VenueGuideFact(club_venue_id=self.other_club_venue_id, section="tickets_entry", topic="other_club", content="Must not leak", source_type="official", reviewed_at=today, confidence="high", status="current", display_order=1),
            ])
            spots = [
                self.spot("Third", 3), self.spot("First", 1, classification="SUPPORTER_SPOT", audience="HOME", supporting_line="Popular with home fans before matches."), self.spot("Second", 2, audience="MIXED"),
            ]
            db.add_all(spots); db.commit()
        finally:
            db.close()

    def spot(self, name, order, **changes):
        values = dict(club_venue_id=self.club_venue_id, display_name=name, classification="CLUB_MATCHDAY_VENUE", audience="MIXED", supporting_line="Open to supporters before the match.", maps_destination=f"{name}, Test", confidence="HIGH", status="CURRENT", business_status="OPEN", reviewed_at=date.today(), review_after=date.today() + timedelta(days=30), display_order=order, approved_at=datetime.now(timezone.utc), approved_by="Matchgoer editorial")
        values.update(changes)
        return PreMatchSpot(**values)

    def tearDown(self):
        db = SessionLocal()
        try:
            db.query(PreMatchSpot).filter(PreMatchSpot.club_venue_id.in_([self.club_venue_id, self.other_club_venue_id])).delete(synchronize_session=False)
            db.query(VenueGuideFact).filter(VenueGuideFact.club_venue_id.in_([self.club_venue_id, self.other_club_venue_id])).delete(synchronize_session=False)
            db.query(VenueGuideFact).filter(VenueGuideFact.venue_id == self.venue_id).delete(synchronize_session=False)
            db.query(ClubVenue).filter(ClubVenue.club_venue_id.in_([self.club_venue_id, self.other_club_venue_id])).delete(synchronize_session=False)
            db.query(Team).filter(Team.team_id.in_([self.team_id, self.other_team_id])).delete(synchronize_session=False)
            db.query(Venue).filter(Venue.venue_id == self.venue_id).delete(synchronize_session=False)
            db.commit()
        finally:
            db.close()

    def test_context_merges_venue_and_matching_club_facts(self):
        guide = get_venue_guide(self.venue_id, self.team_id)
        facts = {fact["topic"] for section in guide["sections"] for fact in section["facts"]}
        self.assertEqual(guide["club_venue_id"], self.club_venue_id)
        self.assertEqual(facts, {"Physical access", "official_ticket_portal"})
        self.assertNotIn("other_club", facts)

    def test_direct_and_wrong_context_fail_closed_to_venue_only(self):
        for team_id in (None, self.team_id + 99):
            guide = get_venue_guide(self.venue_id, team_id)
            self.assertIsNone(guide["club_venue_id"])
            self.assertEqual([fact["topic"] for section in guide["sections"] for fact in section["facts"]], ["Physical access"])
            self.assertEqual(guide["before_match"], [])

    def test_spots_are_public_minimal_ordered_and_filtered(self):
        spots = get_venue_guide(self.venue_id, self.team_id)["before_match"]
        self.assertEqual([spot["display_name"] for spot in spots], ["First", "Second", "Third"])
        self.assertEqual(spots[0]["classification"], "SUPPORTER_SPOT")
        self.assertEqual(spots[1]["audience"], "MIXED")
        self.assertEqual(set(spots[0]), {"pre_match_spot_id", "display_name", "classification", "audience", "supporting_line", "directions_url"})
        self.assertIn("query=First%2C+Test", spots[0]["directions_url"])
        self.assertNotIn("origin", spots[0]["directions_url"])


if __name__ == "__main__":
    unittest.main()
