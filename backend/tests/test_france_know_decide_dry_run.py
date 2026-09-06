import unittest
from collections import Counter

from france_know_decide_dry_run import (
    APPROVED_FIXTURE_PROVIDER_VENUES, BTM, CLUBS, GREAT_SUPPORT, GS_EXPLANATION, know_inventory,
)


class FranceDryRunContractTests(unittest.TestCase):
    def test_approved_know_population_and_btm_partition_are_exact(self):
        self.assertEqual(len(CLUBS), 36)
        self.assertEqual(Counter(row[2] for row in CLUBS), {"Ligue 1": 18, "Ligue 2": 18})
        self.assertEqual(len(BTM), 36)
        self.assertEqual(sum(value is not None for value in BTM.values()), 21)
        self.assertEqual(sum(value is None for value in BTM.values()), 15)

    def test_tickets_are_https_and_entry_is_not_invented(self):
        self.assertTrue(all(row[3].startswith("https://") for row in CLUBS))
        teams = {team_id: {"team_name": name, "venue_id": team_id + 1000,
                           "venue_name": f"{name} ground", "city": "City", "country": "France",
                           "provider_venue_id": team_id + 2000, "club_venue_id": team_id + 3000,
                           "relationship_type": "HOME", "relationship_status": "CURRENT",
                           "current_home_fixtures": 17, "current_venue_variants": 1}
                 for name, team_id, _, _ in CLUBS}
        rows = know_inventory(teams)
        self.assertTrue(all(row["entry_description"] is None and row["entry_evidence_url"] is None for row in rows))
        self.assertTrue(all(row["maps_destination"] for row in rows if not row["intentional_null"]))
        self.assertTrue(all(row["maps_destination"] is None for row in rows if row["intentional_null"]))

    def test_great_support_set_is_exact_and_qualitative(self):
        self.assertEqual(len(GREAT_SUPPORT), 12)
        self.assertEqual(len(set(GREAT_SUPPORT.values())), 12)
        self.assertEqual(GS_EXPLANATION, "If supporter culture is important to you, this is one of the clubs worth seeing.")
        self.assertNotIn("attendance", GS_EXPLANATION.casefold())
        self.assertNotIn("capacity", GS_EXPLANATION.casefold())

    def test_paris_fc_uses_reviewed_fixture_provider_identity(self):
        self.assertEqual(APPROVED_FIXTURE_PROVIDER_VENUES, {114: 18861})


if __name__ == "__main__":
    unittest.main()
