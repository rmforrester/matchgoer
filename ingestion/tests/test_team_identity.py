import unittest

from ingestion.team_identity import (
    CanonicalTeam,
    IdentityResolution,
    TeamIdentityError,
    TeamIdentityOverride,
    allocate_internal_team_id,
    normalize_team_name,
    resolve_team_identity,
    validate_internal_team_id,
    validate_provider_team_id,
)


class _Scalar:
    def __init__(self, value): self.value = value
    def scalar_one(self): return self.value


class _Connection:
    def __init__(self, values): self.values = iter(values); self.statements = []
    def execute(self, statement):
        self.statements.append(str(statement))
        return _Scalar(next(self.values))


class TeamIdentityTests(unittest.TestCase):
    def setUp(self):
        self.union = CanonicalTeam(1599, "Philadelphia Union")
        self.override = TeamIdentityOverride(
            "api_football", 1599, 1118, 2025, -1,
            "Philadelphia Ukrainian Nationals", "APPROVED",
        )

    def resolve(self, **changes):
        values = dict(
            provider="api_football", provider_team_id=1599,
            observed_name="Philadelphia Union", league_id=253, season=2026,
            canonical_team=self.union, overrides=(self.override,),
        )
        values.update(changes)
        return resolve_team_identity(**values)

    def test_allocator_descends_and_remains_negative(self):
        connection = _Connection([-1, -2])
        self.assertEqual(allocate_internal_team_id(connection), -1)
        self.assertEqual(allocate_internal_team_id(connection), -2)
        self.assertTrue(all("matchgoer_team_id_seq" in item for item in connection.statements))

    def test_provider_ids_are_positive_and_zero_is_rejected(self):
        self.assertEqual(validate_provider_team_id(1599), 1599)
        for value in (0, -1):
            with self.assertRaises(TeamIdentityError): validate_provider_team_id(value)

    def test_internal_ids_are_negative_and_namespaces_do_not_overlap(self):
        self.assertEqual(validate_internal_team_id(-1), -1)
        for value in (0, 1):
            with self.assertRaises(TeamIdentityError): validate_internal_team_id(value)

    def test_name_normalization_is_conservative(self):
        self.assertEqual(normalize_team_name("  ÅIFK—FC  "), "aifk fc")
        self.assertNotEqual(normalize_team_name("Philadelphia Union"), normalize_team_name("Philadelphia Ukrainian Nationals"))

    def test_compatible_existing_team_and_trivial_variant(self):
        self.assertEqual(self.resolve().outcome, IdentityResolution.IDENTITY_COMPATIBLE)
        result = self.resolve(observed_name="PHILADELPHIA—UNION")
        self.assertEqual(result.outcome, IdentityResolution.IDENTITY_COMPATIBLE)
        self.assertEqual(result.canonical_team_id, 1599)

    def test_incompatible_existing_team_fails_closed(self):
        result = self.resolve(observed_name="Philadelphia Ukrainian Nationals")
        self.assertEqual(result.outcome, IdentityResolution.NEEDS_IDENTITY_REVIEW)
        self.assertIsNone(result.canonical_team_id)

    def test_unseen_positive_provider_team_retains_same_id(self):
        result = self.resolve(provider_team_id=999999, observed_name="New Club FC", canonical_team=None, overrides=())
        self.assertEqual(result.outcome, IdentityResolution.NEW_PROVIDER_TEAM)
        self.assertEqual(result.canonical_team_id, 999999)

    def test_exact_approved_override_resolves_philadelphia_npsl(self):
        result = self.resolve(
            observed_name="Philadelphia Ukrainian Nationals",
            league_id=1118, season=2025,
        )
        self.assertEqual(result.outcome, IdentityResolution.REVIEWED_SCOPED_OVERRIDE)
        self.assertEqual(result.canonical_team_id, -1)

    def test_override_does_not_leak_across_league(self):
        result = self.resolve(observed_name="Philadelphia Ukrainian Nationals", league_id=253, season=2025)
        self.assertEqual(result.outcome, IdentityResolution.NEEDS_IDENTITY_REVIEW)

    def test_override_does_not_leak_across_season(self):
        result = self.resolve(observed_name="Philadelphia Ukrainian Nationals", league_id=1118, season=2026)
        self.assertEqual(result.outcome, IdentityResolution.NEEDS_IDENTITY_REVIEW)

    def test_override_does_not_leak_across_provider(self):
        result = self.resolve(
            provider="another_provider", observed_name="Philadelphia Ukrainian Nationals",
            league_id=1118, season=2025,
        )
        self.assertEqual(result.outcome, IdentityResolution.NEEDS_IDENTITY_REVIEW)

    def test_unapproved_override_does_not_apply(self):
        review = TeamIdentityOverride("api_football", 1599, 1118, 2025, -1, "Philadelphia Ukrainian Nationals", "REVIEW")
        result = self.resolve(observed_name="Philadelphia Ukrainian Nationals", league_id=1118, season=2025, overrides=(review,))
        self.assertEqual(result.outcome, IdentityResolution.NEEDS_IDENTITY_REVIEW)

    def test_union_style_conflict_fails_closed(self):
        result = resolve_team_identity(
            provider="api_football", provider_team_id=3961,
            observed_name="Atletico Union", league_id=256, season=2026,
            canonical_team=CanonicalTeam(3961, "Union Villa Krause"), overrides=(),
        )
        self.assertEqual(result.outcome, IdentityResolution.NEEDS_IDENTITY_REVIEW)

    def test_existing_positive_ids_are_unchanged(self):
        result = self.resolve()
        self.assertEqual(result.canonical_team_id, 1599)


if __name__ == "__main__":
    unittest.main()
