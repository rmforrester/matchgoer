import unittest
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace as NS

from know_v1 import compose_fixture_know, evidence_policy_satisfied, fact_matches_context
from models import MatchdayTip

TODAY = date(2026, 9, 10)


def evidence(identifier=1, *, title="Official club", status="ACCEPTED", disposition="SUPPORTS"):
    return NS(evidence_id=identifier, source_type="OFFICIAL", source_title=title,
              source_url="https://example.test/source", source_date=TODAY,
              review_status=status, disposition=disposition)


def fact(identifier, module, *, owner="team", owner_id=10, sensitivity="STANDARD", evidence_rows=None, order=1):
    values = dict(team_id=None, club_venue_id=None, venue_id=None, fixture_id=None)
    values[f"{owner}_id"] = owner_id
    return NS(**values, know_fact_id=identifier, module=module, headline=None, content=f"Fact {identifier}",
              display_order=order, publication_status="PUBLISHED", confidence="HIGH",
              claim_sensitivity=sensitivity, reviewed_at=TODAY,
              review_after=TODAY + timedelta(days=30), expires_at=None,
              approved_at=datetime(2026, 9, 9, tzinfo=timezone.utc), approved_by="editor",
              evidence=evidence_rows if evidence_rows is not None else [evidence()])


def spot(identifier=1, order=1):
    return NS(pre_match_spot_id=identifier, club_venue_id=100, display_name=f"Spot {identifier}",
              classification="SUPPORTER_SPOT", audience="HOME", supporting_line=None,
              location_context="On the stadium grounds.", maps_destination=None,
              confidence="HIGH", status="CURRENT", business_status="OPEN", reviewed_at=TODAY,
              review_after=TODAY + timedelta(days=30), display_order=order,
              approved_at=datetime(2026, 9, 9, tzinfo=timezone.utc), approved_by="editor")


class KnowEvidenceTests(unittest.TestCase):
    def test_new_tip_model_default_is_pending_while_active_history_remains_queryable(self):
        self.assertEqual(MatchdayTip.status.default.arg, "pending")
        self.assertEqual(NS(status="active").status, "active")

    def test_standard_and_sensitive_evidence_policy(self):
        self.assertTrue(evidence_policy_satisfied(fact(1, "CLUB")))
        self.assertFalse(evidence_policy_satisfied(fact(2, "SUPPORTERS", sensitivity="SENSITIVE")))
        self.assertTrue(evidence_policy_satisfied(fact(3, "SUPPORTERS", sensitivity="SENSITIVE",
                                                       evidence_rows=[evidence(1), evidence(2, title="Local history")])) )

    def test_contradictory_and_pending_evidence_do_not_count(self):
        item = fact(1, "CLUB", evidence_rows=[evidence(disposition="CONTRADICTS"), evidence(2, status="PENDING")])
        self.assertFalse(evidence_policy_satisfied(item))


class FixtureKnowCompositionTests(unittest.TestCase):
    def setUp(self):
        self.fixture = NS(fixture_id=30, home_team_id=10, venue_id=20)
        self.relationship = NS(club_venue_id=100, team_id=10, venue_id=20, relationship_type="HOME",
                               status="CURRENT", valid_from=None, valid_until=None)

    def test_every_subject_type_resolves_only_for_exact_context(self):
        facts = [
            fact(1, "CLUB", owner="team", owner_id=10),
            fact(2, "MATCHDAY", owner="club_venue", owner_id=100),
            fact(3, "GOOD_TO_KNOW", owner="venue", owner_id=20),
            fact(4, "GOOD_TO_KNOW", owner="fixture", owner_id=30, order=2),
        ]
        self.assertTrue(all(fact_matches_context(item, self.fixture, self.relationship) for item in facts))
        result = compose_fixture_know(self.fixture, self.relationship, facts, [], today=TODAY)
        self.assertEqual([item["know_fact_id"] for item in result["club"]], [1])
        self.assertEqual([item["know_fact_id"] for item in result["matchday"]], [2])
        self.assertEqual([item["know_fact_id"] for item in result["good_to_know"]], [3, 4])

    def test_team_move_ground_share_and_fixture_isolation(self):
        wrong = [
            fact(1, "CLUB", owner="team", owner_id=11),
            fact(2, "MATCHDAY", owner="club_venue", owner_id=101),
            fact(3, "GOOD_TO_KNOW", owner="venue", owner_id=21),
            fact(4, "GOOD_TO_KNOW", owner="fixture", owner_id=31),
        ]
        result = compose_fixture_know(self.fixture, self.relationship, wrong, [], today=TODAY)
        self.assertFalse(any(result[key] for key in ("club", "supporters", "matchday", "dont_miss", "good_to_know")))

    def test_modules_are_optional_without_filler_and_btm_only_is_valid(self):
        result = compose_fixture_know(self.fixture, self.relationship, [], [spot()], today=TODAY)
        self.assertEqual(result["club"], [])
        self.assertEqual(result["before_match"][0]["location_context"], "On the stadium grounds.")
        self.assertIsNone(result["before_match"][0]["directions_url"])
        self.assertNotIn("not yet confirmed", str(result).lower())

    def test_btm_order_and_directions_contract_are_unchanged(self):
        mapped = spot(2, 2); mapped.maps_destination = "Distinct place"
        result = compose_fixture_know(self.fixture, self.relationship, [], [mapped, spot(1, 1)], today=TODAY)
        self.assertEqual([item["pre_match_spot_id"] for item in result["before_match"]], [1, 2])
        self.assertIsNone(result["before_match"][0]["directions_url"])
        self.assertIn("google.com/maps/search", result["before_match"][1]["directions_url"])

    def test_journey_level_dont_miss_collision_fails_closed(self):
        rows = [fact(1, "DONT_MISS", owner="team", owner_id=10), fact(2, "DONT_MISS", owner="venue", owner_id=20)]
        self.assertEqual(compose_fixture_know(self.fixture, self.relationship, rows, [], today=TODAY)["dont_miss"], [])


if __name__ == "__main__":
    unittest.main()
