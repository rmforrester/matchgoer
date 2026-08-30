from dataclasses import replace
import unittest
from unittest.mock import patch

from config.leagues import LeagueScope
from config.venue_overrides import MANUAL_VENUE_OVERRIDES, ManualVenueOverride, manual_override_for
from ingestion.pipeline import TerraceTalkImporter


def scope(league_id: int, season: int = 2026) -> LeagueScope:
    return LeagueScope(
        country="Test",
        league_id=league_id,
        display_name="Test",
        provider_season=season,
        display_season="2026/27",
    )


def fixture(fixture_id: int, venue_id: int | None) -> dict:
    return {"id": fixture_id, "venue": {"id": venue_id}}


class VenueOverridePrecedenceTests(unittest.TestCase):
    def test_ce_europa_override_supersedes_provider_and_home_venue(self):
        result = TerraceTalkImporter._fixture_venue_link(fixture(1, 1466), 593, {593: 1466}, scope(436))
        self.assertIsNone(result[0])
        self.assertEqual(result[1], "manual_verified")
        self.assertEqual(result[2], 1466)
        self.assertEqual(result[3].venue_name, "Can Dragó")

    def test_ce_europa_override_does_not_leak_to_other_season(self):
        result = TerraceTalkImporter._fixture_venue_link(fixture(1, 1466), 593, {593: 1466}, scope(436, 2027))
        self.assertEqual(result, (1466, "fixture_provider", 1466, None))

    def test_gibraltar_override_supersedes_victoria_and_missing_links(self):
        team_ids = [667, 698, 10125, 16130, 16131, 16132, 16133, 16134, 16135, 16137, 16790]
        for team_id in team_ids:
            with self.subTest(team_id=team_id):
                direct = 760 if team_id != 16790 else None
                result = TerraceTalkImporter._fixture_venue_link(fixture(2, direct), team_id, {team_id: 760}, scope(758))
                self.assertIsNone(result[0])
                self.assertEqual(result[1], "manual_verified")
                self.assertEqual(result[3].venue_name, "Europa Sports Park")

    def test_gibraltar_override_does_not_leak_to_other_season(self):
        result = TerraceTalkImporter._fixture_venue_link(fixture(2, 760), 667, {667: 760}, scope(758, 2027))
        self.assertEqual(result, (760, "fixture_provider", 760, None))

    def test_non_overridden_provider_and_home_fallback_are_unchanged(self):
        self.assertEqual(
            TerraceTalkImporter._fixture_venue_link(fixture(3, 900), 1, {1: 901}, scope(999)),
            (900, "fixture_provider", 901, None),
        )
        self.assertEqual(
            TerraceTalkImporter._fixture_venue_link(fixture(3, None), 1, {1: 901}, scope(999)),
            (901, "home_team_fallback", None, None),
        )

    def test_fixture_specific_reviewed_override_outranks_season_override(self):
        season_override = manual_override_for(436, 2026, 593, 99)
        fixture_override = replace(
            season_override,
            venue_name="Authoritative one-off venue",
            fixture_provider_id=99,
        )
        with patch(
            "config.venue_overrides.MANUAL_VENUE_OVERRIDES",
            MANUAL_VENUE_OVERRIDES + (fixture_override,),
        ):
            selected = manual_override_for(436, 2026, 593, 99)
        self.assertEqual(selected.fixture_provider_id, 99)
        self.assertEqual(selected.venue_name, "Authoritative one-off venue")

    def test_austria_lustenau_provider_assignment_is_unchanged(self):
        self.assertEqual(
            TerraceTalkImporter._fixture_venue_link(fixture(4, 135), 2164, {2164: 135}, scope(218)),
            (135, "fixture_provider", 135, None),
        )

    def test_rennes_bad_provider_venue_is_overridden_for_exact_fixture_only(self):
        result = TerraceTalkImporter._fixture_venue_link(
            fixture(1552735, 671), 94, {94: 680}, scope(61)
        )
        self.assertIsNone(result[0])
        self.assertEqual(result[1], "manual_verified")
        self.assertEqual(result[3].venue_name, "Roazhon Park")
        self.assertEqual(
            TerraceTalkImporter._fixture_venue_link(
                fixture(1552736, 680), 94, {94: 680}, scope(61)
            ),
            (680, "fixture_provider", 680, None),
        )

    def test_paris_fc_current_season_home_is_jean_bouin(self):
        result = TerraceTalkImporter._fixture_venue_link(
            fixture(10, 12585), 114, {114: 12585}, scope(61)
        )
        self.assertEqual(result[1], "manual_verified")
        self.assertEqual(result[3].venue_name, "Stade Jean-Bouin")
        self.assertEqual(
            TerraceTalkImporter._fixture_venue_link(
                fixture(10, 12585), 114, {114: 12585}, scope(61, 2027)
            ),
            (12585, "fixture_provider", 12585, None),
        )

    def test_slavia_current_season_home_uses_verified_fortuna_arena(self):
        result = TerraceTalkImporter._fixture_venue_link(
            fixture(11, 435), 560, {560: 18856}, scope(345)
        )
        self.assertEqual(result[1], "manual_verified")
        self.assertEqual(result[3].venue_name, "Fortuna Arena")
        self.assertEqual(
            TerraceTalkImporter._fixture_venue_link(
                fixture(11, 435), 560, {560: 18856}, scope(345, 2027)
            ),
            (435, "fixture_provider", 18856, None),
        )

    def test_derry_provider_id_contradiction_is_fixture_scoped_to_brandywell(self):
        result = TerraceTalkImporter._fixture_venue_link(
            fixture(1492622, 864), 670, {670: 1172}, scope(357)
        )
        self.assertEqual(result[1], "manual_verified")
        self.assertEqual(result[3].venue_name, "The Ryan McBride Brandywell Stadium")
        self.assertEqual(
            TerraceTalkImporter._fixture_venue_link(
                fixture(1492623, 1172), 670, {670: 1172}, scope(357)
            ),
            (1172, "fixture_provider", 1172, None),
        )

    def test_override_lookup_does_not_mutate_home_team_mapping(self):
        home_venues = {593: 1466}
        TerraceTalkImporter._fixture_venue_link(fixture(1, 1466), 593, home_venues, scope(436))
        self.assertEqual(home_venues, {593: 1466})


if __name__ == "__main__":
    unittest.main()
