import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ticketing_v2 import AVAILABILITY_STATES, MATCHING_OUTCOMES, SOURCE_STATES, derive_current_state, validate_publication_destination, validate_research_result, validate_state


class TicketingV2StateTests(unittest.TestCase):
    def test_allowed_and_invalid_states(self):
        self.assertEqual(validate_state("ON_SALE", AVAILABILITY_STATES, "availability state"), "ON_SALE")
        self.assertEqual(validate_state("SOURCE_STALE", SOURCE_STATES, "source state"), "SOURCE_STALE")
        self.assertIn("MATCHED_CANONICAL_FIXTURE", MATCHING_OUTCOMES)
        with self.assertRaises(ValueError): validate_state("AVAILABLE_MAYBE", AVAILABILITY_STATES, "availability state")
        with self.assertRaises(ValueError): validate_state("UNRESEARCHED", SOURCE_STATES, "source state")

    def test_expired_state_degrades_to_unknown(self):
        now = datetime.now(timezone.utc)
        result = derive_current_state([{"observed_state":"ON_SALE", "matching_outcome":"MATCHED_CANONICAL_FIXTURE", "observed_at":now-timedelta(days=2), "valid_until":now-timedelta(days=1)}], now)
        self.assertEqual(result["availability_state"], "SALE_STATUS_UNKNOWN")

    def test_competing_newest_observations_fail_closed(self):
        now = datetime.now(timezone.utc)
        rows = [{"observed_state":s,"matching_outcome":"MATCHED_CANONICAL_FIXTURE","observed_at":now,"valid_until":now+timedelta(hours=1)} for s in ("ON_SALE","SOLD_OUT")]
        self.assertEqual(derive_current_state(rows, now)["availability_state"], "MATCHING_REVIEW_REQUIRED")

    def test_history_is_not_mutated(self):
        now = datetime.now(timezone.utc)
        rows=[{"observed_state":"SALE_STATUS_UNKNOWN","matching_outcome":"MATCHED_CANONICAL_FIXTURE","observed_at":now}]
        before=list(rows)
        derive_current_state(rows, now)
        self.assertEqual(rows,before)

    def test_migration_contains_safety_contract(self):
        sql=(Path(__file__).parents[1]/"migrations"/"20260927_ticketing_v2_t1.sql").read_text()
        rollback=(Path(__file__).parents[1]/"migrations"/"20260927_ticketing_v2_t1_rollback.sql").read_text()
        for token in ("REFERENCES club_venues", "REFERENCES fixtures", "REFERENCES ticket_sources", "ticket_source_legacy_facts", "uq_ticket_sources_club_venue_url"):
            self.assertIn(token,sql)
        self.assertNotIn("UNRESEARCHED", SOURCE_STATES)
        self.assertIn("DROP TABLE IF EXISTS ticket_sources",rollback)

    def test_team_owner_migration_is_additive_and_exactly_one_owner(self):
        migration=(Path(__file__).parents[1]/"migrations"/"20261003_ticket_sources_team_owner.sql").read_text()
        rollback=(Path(__file__).parents[1]/"migrations"/"20261003_ticket_sources_team_owner_rollback.sql").read_text()
        for token in (
            "ADD COLUMN team_id", "REFERENCES teams(team_id)",
            "ALTER COLUMN club_venue_id DROP NOT NULL",
            "num_nonnulls(team_id, club_venue_id) = 1",
            "uq_ticket_sources_team_active_primary",
        ):
            self.assertIn(token,migration)
        self.assertNotIn("UPDATE TICKET_SOURCES",migration.upper())
        self.assertIn("cannot roll back team-owned ticket sources",rollback)


class TicketingResearchContractTests(unittest.TestCase):
    def row(self, **changes):
        row = {"canonical_team_id":"1", "route_type":"ONLINE_OFFICIAL_SHOP", "actionable_url":"https://club.test/tickets", "source_url":"https://club.test/tickets", "source_date":"2026-09-28", "evidence":"official club source", "resolution_state":"RESOLVED_ONLINE", "instructions":"", "venue_applicability":""}
        row.update(changes)
        return row

    def test_official_ticket_shop(self): validate_research_result(self.row())
    def test_authorized_provider_storefront(self): validate_research_result(self.row(route_type="ONLINE_AUTHORIZED_PROVIDER", actionable_url="https://provider.test/club"))
    def test_actionable_official_hub(self): validate_research_result(self.row(route_type="ONLINE_OFFICIAL_HUB", actionable_url="https://club.test/ticket-info"))
    def test_stable_hub_before_rotating_event(self): validate_research_result(self.row(route_type="ONLINE_OFFICIAL_HUB", actionable_url="https://club.test/tickets", source_url="https://club.test/matches/rotating-event"))
    def test_provider_without_destination_fails(self):
        with self.assertRaises(ValueError): validate_research_result(self.row(route_type="ONLINE_AUTHORIZED_PROVIDER", actionable_url=""))
    def test_physical_presale(self): validate_research_result(self.row(route_type="PHYSICAL_PRE_SALE_POINT", actionable_url="", resolution_state="RESOLVED_PHYSICAL", instructions="Club office weekdays"))
    def test_matchday_box_office(self): validate_research_result(self.row(route_type="PHYSICAL_MATCHDAY_BOX_OFFICE", actionable_url="", resolution_state="RESOLVED_PHYSICAL", instructions="Matchday window", venue_applicability="current fixture venue"))
    def test_official_app_requires_actionable_destination(self):
        with self.assertRaises(ValueError): validate_research_result(self.row(route_type="ONLINE_OFFICIAL_APP", actionable_url=""))
    def test_reserve_team_cannot_inherit_without_its_own_evidence(self):
        with self.assertRaises(ValueError): validate_research_result(self.row(canonical_team_id="reserve-2", evidence=""))
    def test_fixture_specific_physical_route_requires_venue(self):
        with self.assertRaises(ValueError): validate_research_result(self.row(route_type="PHYSICAL_MATCHDAY_BOX_OFFICE", actionable_url="", resolution_state="RESOLVED_PHYSICAL", instructions="Gate sales"))
    def test_no_safe_route_is_valid_and_unfilled(self): validate_research_result(self.row(route_type="DIRECT_CLUB_ORDER", actionable_url="", resolution_state="NO_SAFE_ROUTE_FOUND"))


class TicketingPublicationDestinationTests(unittest.TestCase):
    def online(self):
        return {"source_url":"https://club.test/tickets", "source_label":"Official tickets"}

    def good_probe(self, **changes):
        probe={"tls_valid":True, "status":200, "final_url":"https://club.test/tickets", "actionable_ticket_destination":True, "irrelevant_redirect":False}
        probe.update(changes)
        return probe

    def test_live_actionable_destination_passes(self): validate_publication_destination(self.online(), self.good_probe())
    def test_bad_tls_fails(self):
        with self.assertRaisesRegex(ValueError, "TLS"): validate_publication_destination(self.online(), self.good_probe(tls_valid=False))
    def test_dead_destination_fails(self):
        with self.assertRaisesRegex(ValueError, "HTTP"): validate_publication_destination(self.online(), self.good_probe(status=404))
    def test_generic_destination_fails(self):
        with self.assertRaisesRegex(ValueError, "generic"): validate_publication_destination(self.online(), self.good_probe(actionable_ticket_destination=False))
    def test_irrelevant_redirect_fails(self):
        with self.assertRaisesRegex(ValueError, "redirected"): validate_publication_destination(self.online(), self.good_probe(irrelevant_redirect=True))
    def test_offline_cannot_override_actionable_official_page(self):
        with self.assertRaisesRegex(ValueError, "supersede"): validate_publication_destination({"source_url":"", "source_label":"Kartencenter", "actionable_official_url":"https://club.test/tickets"}, None)
    def test_offline_online_label_contradiction_fails(self):
        with self.assertRaisesRegex(ValueError, "contradicts"): validate_publication_destination({"source_url":"", "source_label":"Club Ticket-Onlineshop"}, None)


if __name__ == "__main__": unittest.main()
