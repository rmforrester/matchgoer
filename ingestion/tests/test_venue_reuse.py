import unittest

from ingestion.pipeline import TerraceTalkImporter


class VenueReuseTests(unittest.TestCase):
    def test_venue_name_normalization_treats_dash_variants_as_spacing(self):
        self.assertEqual(TerraceTalkImporter._normalize_venue_name("Heinz-von-Heiden-Arena"), "heinz von heiden arena")
        self.assertEqual(TerraceTalkImporter._normalize_venue_name("Heinz von Heiden-Arena"), "heinz von heiden arena")

    def test_venue_reuse_does_not_erase_provider_omissions(self):
        values = {
            "provider_venue_id": 18858,
            "name": "Heinz-von-Heiden-Arena",
            "address": None,
            "city": "Hannover",
            "capacity": None,
            "latitude": 52.360026,
            "longitude": 9.731016,
        }
        self.assertEqual(TerraceTalkImporter._venue_update_values(values), {
            "name": "Heinz-von-Heiden-Arena",
            "city": "Hannover",
            "latitude": 52.360026,
            "longitude": 9.731016,
        })

    def test_identity_change_with_retained_coordinates_requires_review(self):
        importer = TerraceTalkImporter.__new__(TerraceTalkImporter)
        canonical = {
            "venue_id": 566, "name": "Wembley Stadium", "city": "London",
            "country": "England", "latitude": 51.556070, "longitude": -0.279603,
        }
        incoming = [{
            "provider_venue_id": 566, "name": "The City Ground",
            "city": "Nottingham", "country": "England",
        }]
        conflict = importer._retained_coordinate_identity_conflict(canonical, incoming)
        self.assertIsNotNone(conflict)
        self.assertIn("conflicting_city", conflict["reasons"])
        self.assertIn("unresolved_name_change", conflict["reasons"])
        self.assertEqual(conflict["action"], "preserve canonical identity and coordinates; require reviewed reconciliation")

    def test_matching_identity_can_reuse_reviewed_coordinates(self):
        importer = TerraceTalkImporter.__new__(TerraceTalkImporter)
        canonical = {
            "venue_id": 566, "name": "The City Ground", "city": "Nottingham",
            "country": "England", "latitude": 52.9400, "longitude": -1.1328,
        }
        incoming = [{
            "provider_venue_id": 566, "name": "The City Ground",
            "city": "Nottingham", "country": "England",
        }]
        self.assertIsNone(importer._retained_coordinate_identity_conflict(canonical, incoming))
