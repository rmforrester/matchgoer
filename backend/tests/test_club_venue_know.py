import unittest
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace as NS
from urllib.parse import parse_qs, urlparse

from club_venue_know import (
    google_maps_search_url,
    guide_facts_for_relationship,
    publishable_spots,
    resolve_club_venue,
    spot_is_publishable,
)


TODAY = date(2026, 8, 26)
APPROVED = datetime(2026, 8, 25, tzinfo=timezone.utc)


def relationship(identifier=1, team=10, venue=100, status="CURRENT", **changes):
    values = dict(club_venue_id=identifier, team_id=team, venue_id=venue, status=status,
                  relationship_type="HOME", valid_from=None, valid_until=None)
    values.update(changes)
    return NS(**values)


def spot(identifier=1, owner=1, order=1, **changes):
    values = dict(pre_match_spot_id=identifier, club_venue_id=owner, display_name="The Club Bar",
                  classification="CLUB_MATCHDAY_VENUE", audience="MIXED",
                  supporting_line="Open to supporters before the match.", maps_destination="The Club Bar, Testville",
                  confidence="HIGH", status="CURRENT", business_status="OPEN",
                  reviewed_at=TODAY, review_after=TODAY + timedelta(days=30), display_order=order,
                  approved_at=APPROVED, approved_by="editor@example.test")
    values.update(changes)
    return NS(**values)


class ClubVenueResolutionTests(unittest.TestCase):
    def test_matching_team_and_venue_resolves(self):
        item = relationship()
        self.assertIs(resolve_club_venue(10, 100, [item], on_date=TODAY), item)

    def test_wrong_venue_missing_and_ambiguous_fail_closed(self):
        item = relationship()
        self.assertIsNone(resolve_club_venue(10, 101, [item], on_date=TODAY))
        self.assertIsNone(resolve_club_venue(10, 100, [], on_date=TODAY))
        self.assertIsNone(resolve_club_venue(10, 100, [item, relationship(2)], on_date=TODAY))

    def test_dates_and_status_are_enforced(self):
        self.assertIsNone(resolve_club_venue(10, 100, [relationship(status="HISTORICAL")], on_date=TODAY))
        self.assertIsNone(resolve_club_venue(10, 100, [relationship(valid_from=TODAY + timedelta(days=1))], on_date=TODAY))
        self.assertIsNone(resolve_club_venue(10, 100, [relationship(valid_until=TODAY - timedelta(days=1))], on_date=TODAY))

    def test_ground_share_is_club_isolated(self):
        a, b = relationship(1, team=10), relationship(2, team=11, relationship_type="GROUND_SHARE")
        self.assertIs(resolve_club_venue(10, 100, [a, b], on_date=TODAY), a)
        self.assertEqual([x.display_name for x in publishable_spots(a, [spot(owner=1), spot(2, owner=2)])], ["The Club Bar"])

    def test_move_does_not_inherit_children_and_history_remains(self):
        old = relationship(1, venue=100, status="HISTORICAL", valid_until=TODAY - timedelta(days=1))
        new = relationship(2, venue=101, valid_from=TODAY)
        self.assertIs(resolve_club_venue(10, 101, [old, new], on_date=TODAY), new)
        self.assertEqual(publishable_spots(new, [spot(owner=1)]), [])
        self.assertEqual(old.status, "HISTORICAL")

    def test_everton_and_worcester_ground_identities_do_not_transfer(self):
        goodison = relationship(1, team=45, venue=494, status="HISTORICAL")
        hill = relationship(2, team=45, venue=22033)
        claines = relationship(3, team=9010, venue=11867, status="HISTORICAL")
        sixways = relationship(4, team=9010, venue=30000)
        self.assertEqual(publishable_spots(hill, [spot(owner=1)]), [])
        self.assertEqual(publishable_spots(sixways, [spot(owner=3)]), [])
        self.assertIs(resolve_club_venue(45, 22033, [goodison, hill], on_date=TODAY), hill)
        self.assertIs(resolve_club_venue(9010, 30000, [claines, sixways], on_date=TODAY), sixways)


class PreMatchPublicationTests(unittest.TestCase):
    def test_one_and_three_render_in_order(self):
        rel = relationship()
        self.assertEqual(len(publishable_spots(rel, [spot()])), 1)
        items = [spot(3, order=3), spot(1, order=1), spot(2, order=2)]
        self.assertEqual([x.pre_match_spot_id for x in publishable_spots(rel, items)], [1, 2, 3])

    def test_fourth_position_is_ineligible(self):
        self.assertFalse(spot_is_publishable(spot(order=4), today=TODAY))

    def test_classification_and_audience_remain_distinct(self):
        supporter = spot(classification="SUPPORTER_SPOT", audience="HOME", supporting_line="Popular with home fans.")
        club = spot(2, classification="CLUB_MATCHDAY_VENUE", audience="MIXED")
        self.assertNotEqual(supporter.classification, club.classification)
        self.assertNotEqual(supporter.audience, club.audience)
        self.assertNotIn("home fans", club.supporting_line)

    def test_high_and_explicitly_approved_medium_publish(self):
        self.assertTrue(spot_is_publishable(spot(confidence="HIGH"), today=TODAY))
        self.assertTrue(spot_is_publishable(spot(confidence="MEDIUM"), today=TODAY))
        self.assertFalse(spot_is_publishable(spot(confidence="MEDIUM", approved_at=None, approved_by=None), today=TODAY))

    def test_low_and_noncurrent_never_publish(self):
        self.assertFalse(spot_is_publishable(spot(confidence="LOW"), today=TODAY))
        for status in ("NEEDS_REVIEW", "DRAFT", "ARCHIVED"):
            self.assertFalse(spot_is_publishable(spot(status=status), today=TODAY))

    def test_overdue_closed_and_unknown_fail_closed(self):
        self.assertFalse(spot_is_publishable(spot(review_after=TODAY - timedelta(days=1)), today=TODAY))
        self.assertFalse(spot_is_publishable(spot(business_status="CLOSED"), today=TODAY))
        self.assertFalse(spot_is_publishable(spot(business_status="UNKNOWN"), today=TODAY))

    def test_not_applicable_area_can_publish(self):
        self.assertTrue(spot_is_publishable(spot(classification="SUPPORTER_AREA", business_status="NOT_APPLICABLE"), today=TODAY))

    def test_approval_pair_and_blank_actor_fail_closed(self):
        self.assertFalse(spot_is_publishable(spot(approved_at=None), today=TODAY))
        self.assertFalse(spot_is_publishable(spot(approved_by=" "), today=TODAY))

    def test_maps_url_has_destination_and_no_origin(self):
        url = google_maps_search_url("Bishop Blaize, Stretford")
        query = parse_qs(urlparse(url).query)
        self.assertEqual(query, {"api": ["1"], "query": ["Bishop Blaize, Stretford"]})
        self.assertNotIn("origin", url)


class EvidenceAndFactTests(unittest.TestCase):
    def test_contradiction_is_auditable_and_does_not_mutate(self):
        item = spot()
        evidence = NS(disposition="CONTRADICTS", evidence_note="Reported closed", review_status="PENDING")
        self.assertEqual(evidence.disposition, "CONTRADICTS")
        self.assertEqual(item.status, "CURRENT")

    def test_venue_and_matching_club_facts_coexist(self):
        rel = relationship()
        venue_fact = NS(fact_id=1, venue_id=100, club_venue_id=None, section="at_ground", topic="Physical")
        club_fact = NS(fact_id=2, venue_id=None, club_venue_id=1, section="tickets_entry", topic="Tickets")
        other = NS(fact_id=3, venue_id=None, club_venue_id=2, section="at_ground", topic="Other")
        self.assertEqual([x.fact_id for x in guide_facts_for_relationship(100, rel, [venue_fact, club_fact, other])], [1, 2])

    def test_venue_fact_survives_missing_relationship(self):
        venue_fact = NS(fact_id=1, venue_id=23037, club_venue_id=None, section="at_ground", topic="Physical")
        club_fact = NS(fact_id=2, venue_id=None, club_venue_id=1, section="tickets_entry", topic="Tickets")
        self.assertEqual(guide_facts_for_relationship(23037, None, [venue_fact, club_fact]), [venue_fact])

    def test_cross_owner_topic_conflict_is_omitted(self):
        rel = relationship()
        venue_fact = NS(fact_id=1, venue_id=100, club_venue_id=None, section="tickets_entry", topic="Entry")
        club_fact = NS(fact_id=2, venue_id=None, club_venue_id=1, section="tickets_entry", topic="entry")
        safe = NS(fact_id=3, venue_id=None, club_venue_id=1, section="at_ground", topic="Accessibility")
        self.assertEqual(guide_facts_for_relationship(100, rel, [venue_fact, club_fact, safe]), [safe])


if __name__ == "__main__":
    unittest.main()
