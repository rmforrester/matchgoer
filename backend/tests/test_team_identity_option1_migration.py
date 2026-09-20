import unittest
from pathlib import Path


MIGRATIONS = Path(__file__).parents[1] / "migrations"


class TeamIdentityMigrationContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.forward = (MIGRATIONS / "20260920_team_identity_option1.sql").read_text(encoding="utf-8")
        cls.rollback = (MIGRATIONS / "20260920_team_identity_option1_rollback.sql").read_text(encoding="utf-8")

    def test_negative_integer_sequence_contract(self):
        for fragment in ("AS INTEGER", "START WITH -1", "INCREMENT BY -1", "MAXVALUE -1", "NO CYCLE"):
            self.assertIn(fragment, self.forward)

    def test_additive_table_contract_and_scope_uniqueness(self):
        self.assertIn("CREATE TABLE team_identity_overrides", self.forward)
        self.assertIn("UNIQUE (provider, provider_team_id, league_id, season)", self.forward)
        self.assertIn("REFERENCES teams(team_id) ON DELETE RESTRICT", self.forward)
        self.assertIn("ix_team_identity_overrides_canonical_team_id", self.forward)

    def test_required_constraints_exist(self):
        for fragment in (
            "provider_team_id > 0", "canonical_team_id <> 0", "league_id > 0",
            "season > 0", "btrim(expected_provider_name) <> ''",
            "review_status IN ('APPROVED', 'REVIEW')", "btrim(reason) <> ''",
            "btrim(provenance) <> ''",
        ):
            self.assertIn(fragment, self.forward)

    def test_no_existing_data_rewrite_or_backfill(self):
        upper = self.forward.upper()
        self.assertNotIn("UPDATE TEAMS", upper)
        self.assertNotIn("UPDATE FIXTURES", upper)
        self.assertNotIn("INSERT INTO TEAMS", upper)
        self.assertNotIn("INSERT INTO TEAM_IDENTITY_OVERRIDES", upper)
        self.assertNotIn("ALTER TABLE TEAMS", upper)
        self.assertNotIn("ALTER TABLE FIXTURES", upper)

    def test_sequence_and_table_are_the_only_created_schema_objects(self):
        upper = self.forward.upper()
        self.assertEqual(upper.count("CREATE SEQUENCE"), 1)
        self.assertEqual(upper.count("CREATE TABLE"), 1)
        self.assertNotIn("CREATE TABLE TEAM_NAMES", upper)

    def test_rollback_refuses_dependent_data(self):
        self.assertIn("SELECT 1 FROM team_identity_overrides", self.rollback)
        self.assertIn("SELECT 1 FROM teams WHERE team_id < 0", self.rollback)
        self.assertIn("DROP TABLE team_identity_overrides", self.rollback)
        self.assertIn("DROP SEQUENCE matchgoer_team_id_seq", self.rollback)


if __name__ == "__main__":
    unittest.main()
