import unittest

from provider_identity_guard import validate_provider_relationship_contract, verify_provider_relationship


def receipt(outcome="IDENTITY_COMPATIBLE", canonical=1599, league=253, season=2026, override=None):
    return {
        "provider": "api_football", "provider_team_id": 1599,
        "canonical_team_id": canonical, "observed_name": "Philadelphia Union",
        "canonical_name": "Philadelphia Union" if canonical == 1599 else "Philadelphia Ukrainian Nationals",
        "league_id": league, "season": season, "identity_resolution": outcome,
        "approved_override_id": override, "resolver_version": "team-identity-option1-v1",
    }


def relationship(value=None):
    value = value or receipt()
    return {"provider_derived": True, "team_id": value["canonical_team_id"], "team_name": value["canonical_name"], "identity_receipt": value}


class Result:
    def __init__(self, rows): self.rows = rows
    def mappings(self): return self
    def one_or_none(self): return self.rows[0] if len(self.rows) == 1 else None
    def scalar_one_or_none(self): return self.rows[0]["team_identity_override_id"] if len(self.rows) == 1 else None


class Connection:
    def __init__(self, override=True): self.override = override
    def execute(self, statement, params=None):
        sql = " ".join(str(statement).split())
        if "FROM teams" in sql:
            name = "Philadelphia Union" if params["id"] == 1599 else "Philadelphia Ukrainian Nationals"
            return Result([{"team_id": params["id"], "team_name": name}])
        if "FROM team_identity_overrides" in sql:
            return Result([{"team_identity_override_id": params["override_id"]}]) if self.override else Result([])
        raise AssertionError(sql)


class ProviderIdentityGuardTests(unittest.TestCase):
    def test_compatible_receipt_accepted(self):
        row = relationship(); validate_provider_relationship_contract(row); verify_provider_relationship(Connection(), row)

    def test_reviewed_override_accepted(self):
        value = receipt("REVIEWED_SCOPED_OVERRIDE", -1, 257, 2025, 7)
        value.update(observed_name="Philadelphia Ukrainian Nationals")
        row = relationship(value); validate_provider_relationship_contract(row); verify_provider_relationship(Connection(), row)

    def test_unresolved_and_missing_receipts_rejected(self):
        with self.assertRaises(ValueError): validate_provider_relationship_contract({"provider_derived": True, "team_id": 1})
        value = receipt("NEEDS_IDENTITY_REVIEW")
        with self.assertRaises(ValueError): validate_provider_relationship_contract(relationship(value))

    def test_canonical_id_and_name_mismatch_rejected(self):
        row = relationship(); row["team_id"] = 2
        with self.assertRaises(ValueError): validate_provider_relationship_contract(row)
        row = relationship(); row["team_name"] = "Different Club"
        with self.assertRaises(ValueError): validate_provider_relationship_contract(row)

    def test_missing_or_unapproved_override_rejected(self):
        value = receipt("REVIEWED_SCOPED_OVERRIDE", -1, 257, 2025, 7)
        value.update(observed_name="Philadelphia Ukrainian Nationals")
        with self.assertRaises(ValueError): verify_provider_relationship(Connection(False), relationship(value))

    def test_wrong_override_league_is_rejected_by_database_lookup(self):
        value = receipt("REVIEWED_SCOPED_OVERRIDE", -1, 999, 2025, 7)
        value.update(observed_name="Philadelphia Ukrainian Nationals")
        with self.assertRaises(ValueError): verify_provider_relationship(Connection(False), relationship(value))

    def test_wrong_override_season_is_rejected_by_database_lookup(self):
        value = receipt("REVIEWED_SCOPED_OVERRIDE", -1, 257, 2024, 7)
        value.update(observed_name="Philadelphia Ukrainian Nationals")
        with self.assertRaises(ValueError): verify_provider_relationship(Connection(False), relationship(value))

    def test_legacy_canonical_relationship_remains_valid(self):
        validate_provider_relationship_contract({"team_id": 1, "team_name": "Legacy"})


if __name__ == "__main__": unittest.main()
