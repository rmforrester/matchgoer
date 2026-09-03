import unittest
from pathlib import Path

from decide_inventory import reconcile_row


def row(subject="Hansa Rostock", scope="TEAM", category="EXCEPTIONAL_SUPPORT"):
    return {
        "Country": "Germany",
        "Subject Type": scope,
        "Subject": subject,
        "Category": category,
        "Supporter Label": "Exceptional support",
        "Short Explanation": "Reviewed explanation.",
        "Discovery Value": "Very High",
        "Lead Priority": "Lead",
        "Evidence URL": "https://example.test/evidence",
        "Editorial Status": "APPROVED_EVIDENCE",
        "Notes": "2025/26 completed season.",
    }


class DecideInventoryTests(unittest.TestCase):
    def inventory(self):
        teams = [{"country": "Germany", "team_id": 1321, "team_name": "Hansa Rostock"}]
        return {
            "teams": teams,
            "venues": [],
            "published": [],
            "team_index": {("Germany", "hansa rostock"): {1321}},
            "venue_index": {},
        }

    def test_exact_identity_is_ready_and_preserves_evidence_season(self):
        result = reconcile_row(row(), self.inventory())
        self.assertEqual(result["reconciliation_status"], "READY")
        self.assertEqual(result["matchgoer_subject_id(s)"], "1321")
        self.assertEqual(result["evidence_season"], "2025/26")

    def test_ambiguous_exact_identity_never_auto_publishes(self):
        inventory = self.inventory()
        inventory["team_index"][("Germany", "hansa rostock")] = {1321, 9999}
        result = reconcile_row(row(), inventory)
        self.assertEqual(result["reconciliation_status"], "NEEDS_IDENTITY_REVIEW")
        self.assertEqual(result["matchgoer_subject_id(s)"], "")

    def test_equivalent_published_fact_is_not_duplicated(self):
        inventory = self.inventory()
        inventory["published"] = [{
            "subject_type": "TEAM", "team_a_id": None, "team_b_id": None,
            "team_id": 1321, "venue_id": None, "attribute_key": "EXCEPTIONAL_SUPPORT",
        }]
        self.assertEqual(reconcile_row(row(), inventory)["reconciliation_status"], "ALREADY_PUBLISHED")

    def test_publication_artifact_is_guarded_and_idempotent(self):
        sql = (Path(__file__).parents[2] / "reports" / "decide" / "decide-five-country-publication-20260903.sql").read_text(encoding="utf-8")
        self.assertIn("ON CONFLICT (team_id, attribute_key)", sql)
        self.assertIn("DO NOTHING", sql)
        self.assertIn("IF exact_facts <> 4 OR exact_evidence <> 4", sql)
        self.assertEqual(sql.count("'EXCEPTIONAL_SUPPORT'"), 4)


if __name__ == "__main__":
    unittest.main()
