import unittest

from fixture_type import classify_fixture_type


class FixtureTypeTests(unittest.TestCase):
    def test_normal_domestic_league_is_standard(self):
        self.assertEqual(classify_fixture_type("Premier League", "England"), "standard")

    def test_domestic_cups_are_cup_markers(self):
        for name, country in (("FA Cup", "England"), ("Copa del Rey", "Spain"), ("DFB-Pokal", "Germany"), ("Super Cup", "Italy")):
            with self.subTest(name=name):
                self.assertEqual(classify_fixture_type(name, country), "cup")

    def test_continental_club_competitions_share_the_cup_marker(self):
        for name in ("UEFA Champions League", "UEFA Europa League", "UEFA Europa Conference League", "FIFA Club World Cup"):
            with self.subTest(name=name):
                self.assertEqual(classify_fixture_type(name, "World"), "cup")

    def test_domestic_playoffs_remain_standard(self):
        for name in ("Championship - Play Offs", "Promotion Playoff", "Relegation Play-Offs"):
            with self.subTest(name=name):
                self.assertEqual(classify_fixture_type(name, "England"), "standard")

    def test_national_team_competitions_are_international(self):
        for name in ("World Cup", "World Cup - Qualification Europe", "UEFA Nations League", "European Championship", "CONMEBOL - UEFA Finalissima", "Friendlies"):
            with self.subTest(name=name):
                self.assertEqual(classify_fixture_type(name, "World"), "international")

    def test_missing_or_unknown_metadata_fails_safe_to_standard(self):
        for name, country in ((None, None), ("", None), ("New Competition", None), ("Friendlies Clubs", "World")):
            with self.subTest(name=name):
                self.assertEqual(classify_fixture_type(name, country), "standard")


if __name__ == "__main__":
    unittest.main()
