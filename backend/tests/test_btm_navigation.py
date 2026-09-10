import unittest

from btm_navigation import validate_btm_navigation


class BtmNavigationValidationTests(unittest.TestCase):
    def test_exact_address_and_coordinates_are_allowed_when_supported(self):
        validate_btm_navigation(maps_destination="57 Fulham High Street, London SW6 3JJ", unique_target_supported=True)
        validate_btm_navigation(maps_destination="51.4749,-0.2217", unique_target_supported=True)

    def test_common_name_fails_closed_without_unique_support(self):
        with self.assertRaises(ValueError):
            validate_btm_navigation(maps_destination="Golden Lion, London", unique_target_supported=False)

    def test_contained_or_unknown_destination_can_publish_without_directions(self):
        validate_btm_navigation(maps_destination=None, unique_target_supported=False)

    def test_starkies_requires_explicit_containing_venue_support(self):
        with self.assertRaises(ValueError):
            validate_btm_navigation(maps_destination="Starkies, Bury", unique_target_supported=False)
        validate_btm_navigation(maps_destination="Gigg Lane, Bury, BL9 9HR", unique_target_supported=True)

