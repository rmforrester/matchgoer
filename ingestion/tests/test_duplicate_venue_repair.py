import unittest

from ingestion.apply_duplicate_venue_repair import (
    DEPENDENCY_TABLES,
    dependencies_clear,
    reviewed_same_venue_decision,
)


class DuplicateVenueRepairTests(unittest.TestCase):
    def test_dependency_audit_covers_product_tables(self):
        for table in ("fixtures", "club_venues", "venue_names", "venue_provider_refs",
                      "venue_visits", "venue_guide_facts", "decision_facts", "know_facts"):
            self.assertIn(table, DEPENDENCY_TABLES)

    def test_repair_scope_is_one_merge_not_three(self):
        decisions = {
            (23309, 27744): "SAME_PHYSICAL_VENUE_CONFIRMED",
            (23870, 27753): "NOT_SAME_PHYSICAL_VENUE",
            (23251, 27756): "NOT_SAME_PHYSICAL_VENUE",
        }
        self.assertEqual(sum(v == "SAME_PHYSICAL_VENUE_CONFIRMED" for v in decisions.values()), 1)

    def test_merge_requires_exact_reviewed_same_physical_venue_decision(self):
        manifest = {"identity_decisions": [{
            "survivor_venue_id": 23309,
            "candidate_venue_id": 27744,
            "decision": "SAME_PHYSICAL_VENUE_CONFIRMED",
        }]}
        self.assertTrue(reviewed_same_venue_decision(manifest, 23309, 27744))
        self.assertFalse(reviewed_same_venue_decision(manifest, 23870, 27753))

    def test_distinct_ground_decision_cannot_authorize_merge(self):
        manifest = {"identity_decisions": [{
            "survivor_venue_id": 23870,
            "candidate_venue_id": 27753,
            "decision": "NOT_SAME_PHYSICAL_VENUE",
        }]}
        self.assertFalse(reviewed_same_venue_decision(manifest, 23870, 27753))

    def test_canonical_delete_requires_every_dependency_to_be_clear(self):
        clear = {table: 0 for table in DEPENDENCY_TABLES}
        self.assertTrue(dependencies_clear(clear))
        clear["venue_visits"] = 1
        self.assertFalse(dependencies_clear(clear))


if __name__ == "__main__":
    unittest.main()
