import unittest

from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine

from ingestion.team_identity import (
    ProviderTeamObservation,
    resolve_provider_team_batch,
)


class TeamIdentityBatchTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        metadata = MetaData()
        self.teams = Table("teams", metadata, Column("team_id", Integer, primary_key=True), Column("team_name", String))
        self.overrides = Table(
            "team_identity_overrides", metadata,
            Column("team_identity_override_id", Integer, primary_key=True), Column("provider", String),
            Column("provider_team_id", Integer), Column("league_id", Integer), Column("season", Integer),
            Column("canonical_team_id", Integer), Column("expected_provider_name", String), Column("review_status", String),
        )
        metadata.create_all(self.engine)
        with self.engine.begin() as connection:
            connection.execute(self.teams.insert(), [
                {"team_id": 1599, "team_name": "Philadelphia Union"},
                {"team_id": -1, "team_name": "Philadelphia Ukrainian Nationals"},
                {"team_id": 3961, "team_name": "Union Villa Krause"},
                {"team_id": 40, "team_name": "Liverpool"},
            ])
            connection.execute(self.overrides.insert().values(
                team_identity_override_id=7, provider="api_football", provider_team_id=1599,
                league_id=257, season=2025, canonical_team_id=-1,
                expected_provider_name="Philadelphia Ukrainian Nationals", review_status="APPROVED",
            ))

    def test_batched_resolution_and_scope(self):
        observations = [
            ProviderTeamObservation("api_football", 1599, "Philadelphia Union", 253, 2026),
            ProviderTeamObservation("api_football", 1599, "Philadelphia Ukrainian Nationals", 257, 2025),
            ProviderTeamObservation("api_football", 1599, "Philadelphia Ukrainian Nationals", 257, 2026),
            ProviderTeamObservation("api_football", 3961, "Unión", 128, 2026),
            ProviderTeamObservation("api_football", 40, "Líverpool", 39, 2026),
            ProviderTeamObservation("api_football", 9999, "New England Club", 39, 2026),
        ]
        reads = []
        with self.engine.connect() as connection:
            from sqlalchemy import event
            event.listen(connection, "before_cursor_execute", lambda *args: reads.append(args[2]))
            receipts = resolve_provider_team_batch(connection, observations)
        outcomes = [receipts[item.key].identity_resolution for item in observations]
        self.assertEqual(outcomes, [
            "IDENTITY_COMPATIBLE", "REVIEWED_SCOPED_OVERRIDE", "NEEDS_IDENTITY_REVIEW",
            "NEEDS_IDENTITY_REVIEW", "IDENTITY_COMPATIBLE", "NEW_PROVIDER_TEAM",
        ])
        self.assertEqual(receipts[observations[1].key].canonical_team_id, -1)
        self.assertEqual(receipts[observations[1].key].approved_override_id, 7)
        self.assertEqual(receipts[observations[5].key].canonical_team_id, 9999)
        self.assertLessEqual(len(reads), 3)

    def test_override_to_missing_canonical_fails_closed(self):
        with self.engine.begin() as connection:
            connection.execute(self.overrides.insert().values(
                team_identity_override_id=8, provider="api_football", provider_team_id=7000,
                league_id=257, season=2025, canonical_team_id=-99,
                expected_provider_name="Missing Canonical", review_status="APPROVED",
            ))
        observation=ProviderTeamObservation("api_football",7000,"Missing Canonical",257,2025)
        with self.engine.connect() as connection:
            receipt=resolve_provider_team_batch(connection,[observation])[observation.key]
        self.assertEqual(receipt.identity_resolution,"NEEDS_IDENTITY_REVIEW")
        self.assertIsNone(receipt.canonical_team_id)

    def tearDown(self):
        self.engine.dispose()


if __name__ == "__main__":
    unittest.main()
