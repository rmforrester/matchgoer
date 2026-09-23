import unittest
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace as NS

from fixture_tickets import resolve_fixture_ticket_action

TODAY = date.today()

def fixture(**changes):
    values = {"home_team_id": 1, "away_team_id": 2, "venue_id": 10, "fixture_date": datetime.now(timezone.utc) + timedelta(days=7)}
    values.update(changes); return NS(**values)

def relationship(identifier=100, **changes):
    values = {"club_venue_id": identifier, "team_id": 1, "venue_id": 10, "relationship_type": "HOME", "status": "CURRENT", "valid_from": None, "valid_until": None}
    values.update(changes); return NS(**values)

def fact(identifier=100, **changes):
    values = {"club_venue_id": identifier, "venue_id": None, "section": "tickets_entry", "topic": "official_ticket_portal", "source_type": "official", "status": "current", "source_url": "https://tickets.example.test/home", "source_label": "Club tickets", "expires_at": None, "review_after": TODAY + timedelta(days=30)}
    values.update(changes); return NS(**values)

class FixtureTicketTests(unittest.TestCase):
    def test_valid_exact_home_relationship_is_eligible(self):
        self.assertEqual(resolve_fixture_ticket_action(fixture(), [relationship()], [fact()])["url"], "https://tickets.example.test/home")

    def test_missing_retired_stale_unofficial_or_insecure_action_is_absent(self):
        self.assertIsNone(resolve_fixture_ticket_action(fixture(), [relationship()], []))
        for changes in ({"status": "archived"}, {"review_after": TODAY - timedelta(days=1)}, {"source_type": "supporter"}, {"source_url": "http://tickets.example.test"}):
            self.assertIsNone(resolve_fixture_ticket_action(fixture(), [relationship()], [fact(**changes)]))

    def test_away_owned_or_venue_owned_action_does_not_leak(self):
        self.assertIsNone(resolve_fixture_ticket_action(fixture(), [relationship()], [fact(identifier=101)]))
        self.assertIsNone(resolve_fixture_ticket_action(fixture(), [relationship()], [fact(club_venue_id=None, venue_id=10)]))

    def test_ground_share_and_temporary_home_require_exact_team_and_venue(self):
        for kind in ("GROUND_SHARE", "TEMPORARY_HOME"):
            self.assertIsNotNone(resolve_fixture_ticket_action(fixture(), [relationship(relationship_type=kind)], [fact()]))
        self.assertIsNone(resolve_fixture_ticket_action(fixture(venue_id=11), [relationship()], [fact()]))
        self.assertIsNone(resolve_fixture_ticket_action(fixture(home_team_id=2), [relationship()], [fact()]))

    def test_neutral_or_ambiguous_context_fails_closed(self):
        self.assertIsNone(resolve_fixture_ticket_action(fixture(), [], [fact()]))
        self.assertIsNone(resolve_fixture_ticket_action(fixture(), [relationship(100), relationship(101)], [fact(100), fact(101)]))

    def test_national_team_uses_same_exact_relationship_rule(self):
        f = fixture(home_team_id=1108, venue_id=23198)
        r = relationship(team_id=1108, venue_id=23198)
        self.assertIsNotNone(resolve_fixture_ticket_action(f, [r], [fact()]))

if __name__ == "__main__": unittest.main()
