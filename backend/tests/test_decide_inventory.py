import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from decide_inventory import (
    PAIR_SEPARATOR, REVIEWED_VENUE_ALIASES, publication_summary, reconcile_row, write_publication_sql,
)


def row(subject="Hansa Rostock", scope="TEAM", category="EXCEPTIONAL_SUPPORT", evidence_url="https://example.test/evidence"):
    return {
        "Country": "Germany",
        "Subject Type": scope,
        "Subject": subject,
        "Category": category,
        "Supporter Label": "Exceptional support",
        "Short Explanation": "Reviewed explanation.",
        "Discovery Value": "Very High",
        "Lead Priority": "Lead",
        "Evidence URL": evidence_url,
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
        result = reconcile_row(row(evidence_url=""), self.inventory())
        with TemporaryDirectory() as directory:
            output = Path(directory) / "publication.sql"
            write_publication_sql(output, [result])
            sql = output.read_text(encoding="utf-8")
        self.assertIn("ON CONFLICT DO NOTHING", sql)
        self.assertIn("approved.evidence_url IS NOT NULL", sql)
        self.assertNotIn("https://example.test/evidence", sql)

    def test_ready_fact_without_evidence_is_publishable_without_fabricated_evidence(self):
        result = reconcile_row(row(evidence_url=""), self.inventory())
        counts = publication_summary([result])
        self.assertEqual(counts["facts_to_insert"], 1)
        self.assertEqual(counts["evidence_rows_to_insert"], 0)
        self.assertEqual(counts["new_facts_without_evidence_metadata"], 1)
        self.assertEqual(counts["active_facts_without_evidence_metadata"], 1)

    def test_evidence_backed_fact_retains_evidence(self):
        result = reconcile_row(row(), self.inventory())
        self.assertEqual(result["evidence_url"], "https://example.test/evidence")
        self.assertEqual(publication_summary([result])["evidence_rows_to_insert"], 1)

    def test_absent_pair_is_dormant_not_in_inventory(self):
        missing = row(subject=f"Hansa Rostock{PAIR_SEPARATOR}Missing Club", scope="TEAM_PAIR", category="SIGNIFICANT_RIVALRY")
        result = reconcile_row(missing, self.inventory())
        self.assertEqual(result["reconciliation_status"], "NOT_IN_CURRENT_INVENTORY")

    def test_all_catalogue_rows_are_preserved_in_summary(self):
        results = [reconcile_row(row(subject=f"Missing {index}"), self.inventory()) for index in range(255)]
        counts = publication_summary(results)
        self.assertEqual(counts["total_approved"], 255)
        self.assertEqual(counts["dormant_not_in_inventory"], 255)

    def test_deterministic_alias_does_not_accept_multiple_candidates(self):
        inventory = self.inventory()
        inventory["teams"].append({"country": "Germany", "team_id": 9999, "team_name": "Hansa Rostock City"})
        inventory["team_index"] = {}
        result = reconcile_row(row(), inventory)
        self.assertEqual(result["reconciliation_status"], "NEEDS_IDENTITY_REVIEW")

    def test_reviewed_duplicate_venue_identity_uses_authoritative_relationship_target(self):
        self.assertEqual(REVIEWED_VENUE_ALIASES[("England", "The Hawthorns")], 597)
        self.assertEqual(REVIEWED_VENUE_ALIASES[("Spain", "Santiago Bernabéu")], 23269)

    def test_victoria_park_does_not_map_to_victory_park(self):
        source = row(subject="Victoria Park", scope="VENUE", category="CLASSIC_GROUND")
        source["Country"] = "England"
        inventory = self.inventory()
        inventory["venues"] = [{"country": "England", "venue_id": 21314, "name": "Victory Park"}]
        result = reconcile_row(source, inventory)
        self.assertEqual(result["reconciliation_status"], "NOT_IN_CURRENT_INVENTORY")
        self.assertEqual(result["matchgoer_subject_id(s)"], "")

    def test_historical_brescia_does_not_map_to_union_brescia(self):
        source = row(subject="Atalanta — Brescia", scope="TEAM_PAIR", category="SIGNIFICANT_RIVALRY")
        source["Country"] = "Italy"
        result = reconcile_row(source, self.inventory())
        self.assertEqual(result["reconciliation_status"], "NOT_IN_CURRENT_INVENTORY")

    def test_reggina_does_not_map_to_reggiana(self):
        source = row(subject="Reggina — Messina", scope="TEAM_PAIR", category="SIGNIFICANT_RIVALRY")
        source["Country"] = "Italy"
        result = reconcile_row(source, self.inventory())
        self.assertEqual(result["reconciliation_status"], "NOT_IN_CURRENT_INVENTORY")


if __name__ == "__main__":
    unittest.main()
