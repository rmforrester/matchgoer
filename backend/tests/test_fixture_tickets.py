import unittest
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace as NS

from fixture_tickets import resolve_fixture_ticket_action, resolve_fixture_ticket_presentation

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

def source(identifier=100, **changes):
    values = {"club_venue_id": identifier, "source_role": "PRIMARY", "operational_status": "ACTIVE", "source_state": "VERIFIED_OFFICIAL_TICKET_NAVIGATION_SOURCE", "ticketing_model": "ONLINE_NAVIGATION", "source_url": "https://tickets.example.test/home", "source_label": "Official ticket hub"}
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

    def test_v2_online_source_wins_without_duplicate_legacy_cta(self):
        result = resolve_fixture_ticket_presentation(fixture(), [relationship()], [fact()], [source()])
        self.assertEqual(result["serving"], "V2")
        self.assertEqual(result["action"]["url"], "https://tickets.example.test/home")
        self.assertIsNone(result["guidance"])

    def test_v2_physical_source_is_guidance_not_fake_link(self):
        physical = source(source_state="PAY_AT_GATE_OR_OFFLINE_SOURCE", ticketing_model="OFFLINE", source_url=None, source_label="Tickets from the club office on matchday")
        result = resolve_fixture_ticket_presentation(fixture(), [relationship()], [], [physical])
        self.assertIsNone(result["action"])
        self.assertEqual(result["guidance"]["message"], "Tickets from the club office on matchday")

    def test_no_v2_source_preserves_legacy_fallback(self):
        result = resolve_fixture_ticket_presentation(fixture(), [relationship()], [fact()], [])
        self.assertEqual(result["serving"], "LEGACY")
        self.assertEqual(result["action"]["url"], "https://tickets.example.test/home")

    def test_unsafe_or_ambiguous_v2_source_fails_closed(self):
        unsafe = source(source_state="SOURCE_NEEDS_REVIEW")
        result = resolve_fixture_ticket_presentation(fixture(), [relationship()], [fact()], [unsafe])
        self.assertEqual(result["serving"], "V2_FAIL_CLOSED")
        self.assertIsNone(result["action"])
        duplicate = resolve_fixture_ticket_presentation(fixture(), [relationship()], [fact()], [source(), source()])
        self.assertIsNone(duplicate["action"])

    def test_v2_source_cannot_leak_to_other_relationship(self):
        result = resolve_fixture_ticket_presentation(fixture(), [relationship()], [], [source(identifier=101)])
        self.assertEqual(result["serving"], "LEGACY")
        self.assertIsNone(result["action"])

if __name__ == "__main__": unittest.main()
