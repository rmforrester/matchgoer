import unittest

from location_safety import has_usable_coordinates
from models import Fixture


class LocationSafetyTests(unittest.TestCase):
    def test_null_coordinates_fail_closed_for_location_dependent_serving(self):
        self.assertFalse(has_usable_coordinates(None, None))
        self.assertFalse(has_usable_coordinates(51.5, None))
        self.assertFalse(has_usable_coordinates(None, -0.1))
        self.assertTrue(has_usable_coordinates(51.5, -0.1))

    def test_fixture_without_a_resolved_venue_remains_a_valid_non_location_record(self):
        fixture = Fixture(fixture_id=99, venue_id=None, home_team="Home", away_team="Away")
        self.assertIsNone(fixture.venue_id)


if __name__ == "__main__":
    unittest.main()
