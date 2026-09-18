import unittest

from ingestion.venue_identity import VenueIdentity, canonical_reuse_permitted


def venue(name, city="", region="", country="USA"):
    return VenueIdentity.from_values(name=name, city=city, region=region, country=country)


class VenueIdentityTests(unittest.TestCase):
    def test_same_identity_reuses(self):
        self.assertTrue(canonical_reuse_permitted(venue("City Stadium", "Richmond", "VA"), venue("City Stadium", "Richmond, Virginia")))

    def test_different_city_rejected(self):
        self.assertFalse(canonical_reuse_permitted(venue("City Stadium", "Lynchburg", "Virginia"), venue("City Stadium", "Richmond, Virginia")))

    def test_hill_city_rejected_from_richmond(self):
        proposed = venue("City Stadium", "Lynchburg", "Virginia")
        richmond = venue("City Stadium", "Richmond, Virginia")
        self.assertFalse(canonical_reuse_permitted(proposed, richmond))

    def test_spooky_nook_legitimate_reuse(self):
        proposed = venue("Spooky Nook Sports Lancaster", "Manheim", "Pennsylvania")
        existing = venue("Spooky Nook Sports Lancaster", "Manheim, PA")
        self.assertTrue(canonical_reuse_permitted(proposed, existing))

    def test_compatible_formatting_reuses(self):
        proposed = venue("St. Louis Soccer Park", "St. Louis", "MO")
        existing = venue("Saint Louis Soccer Park", "Saint Louis, Missouri")
        self.assertTrue(canonical_reuse_permitted(proposed, existing))

    def test_blank_proposed_city_preserves_nonconflicting_legacy_reuse(self):
        self.assertTrue(canonical_reuse_permitted(venue("Memorial Stadium"), venue("Memorial Stadium", "Seattle", "WA")))

    def test_known_proposed_city_does_not_reuse_blank_existing_city(self):
        self.assertFalse(canonical_reuse_permitted(venue("Memorial Stadium", "Seattle", "WA"), venue("Memorial Stadium")))

    def test_both_cities_blank_preserve_nonconflicting_reuse(self):
        self.assertTrue(canonical_reuse_permitted(venue("Memorial Stadium"), venue("Memorial Stadium")))

    def test_different_state_rejected(self):
        self.assertFalse(canonical_reuse_permitted(venue("Memorial Stadium", "Springfield", "MO"), venue("Memorial Stadium", "Springfield", "VA")))

    def test_different_country_rejected(self):
        self.assertFalse(canonical_reuse_permitted(venue("National Stadium", "Cardiff", country="Wales"), venue("National Stadium", "Cardiff", country="England")))

    def test_target_key_distinguishes_same_name_cross_city(self):
        self.assertNotEqual(venue("City Stadium", "Lynchburg", "VA").key, venue("City Stadium", "Richmond", "VA").key)

    def test_postwrite_identity_uses_same_semantics(self):
        target = venue("City Stadium", "Lynchburg", "Virginia")
        self.assertTrue(canonical_reuse_permitted(target, venue("City Stadium", "Lynchburg, VA")))
        self.assertFalse(canonical_reuse_permitted(target, venue("City Stadium", "Richmond, VA")))


if __name__ == "__main__":
    unittest.main()
