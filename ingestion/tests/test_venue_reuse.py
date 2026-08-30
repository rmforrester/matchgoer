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
