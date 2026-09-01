import unittest

from ingestion.coordinates import NominatimCoordinateEnricher


class Location:
    def __init__(self, latitude, longitude, raw):
        self.latitude, self.longitude, self.raw = latitude, longitude, raw


def stadium(name, *, name_en=None, alt_name=None, city="Athens", country_code="gr", latitude=38.0, longitude=23.7):
    names = {"name": name}
    if name_en:
        names["name:en"] = name_en
    if alt_name:
        names["alt_name"] = alt_name
    return Location(latitude, longitude, {
        "category": "leisure", "type": "stadium", "osm_type": "way",
        "osm_id": int(latitude * 100000 + longitude * 100),
        "namedetails": names,
        "display_name": f"{name}, {city}",
        "address": {"city": city, "country": "local", "country_code": country_code},
    })


class Geocoder:
    def __init__(self, responses):
        self.responses, self.calls = list(responses), []

    def geocode(self, query, **kwargs):
        self.calls.append((query, kwargs))
        return self.responses.pop(0) if self.responses else []


class StructuredNominatimTests(unittest.TestCase):
    def resolve(self, venue, responses):
        resolver = NominatimCoordinateEnricher(delay_seconds=0)
        resolver.geolocator = Geocoder(responses)
        result = resolver.enrich(venue, strict_uniqueness=True)
        return result, resolver.geolocator

    def venue(self, **changes):
        value = {"name": "Example Stadium", "address": "Main Road", "city": "Athens", "country": "Greece"}
        value.update(changes)
        return value

    def test_ambiguous_weak_query_continues_to_stronger_name_lookup(self):
        streets = [Location(38, 23, {"category": "highway", "type": "residential"})] * 2
        result, geocoder = self.resolve(self.venue(), [[], streets, [stadium("Example Stadium")]])
        self.assertEqual(result.source, "nominatim")
        self.assertGreaterEqual(len(geocoder.calls), 3)

    def test_name_en_reconciles_native_primary_name(self):
        result, _ = self.resolve(
            self.venue(name="Karaiskakis Stadium", city="Piraeus"),
            [[stadium("Γήπεδο Γεώργιος Καραϊσκάκης", name_en="Karaiskakis Stadium", city="Piraeus")]],
        )
        self.assertEqual(result.matched_label, "Karaiskakis Stadium")

    def test_alternate_name_and_conservative_transliteration_reconcile(self):
        result, _ = self.resolve(
            self.venue(name="Stadion Rajko Mitic", city="Beograd", country="Serbia"),
            [[stadium("Стадион Рајко Митић", alt_name="Rajko Mitić Stadium", city="Beograd", country_code="rs")]],
        )
        self.assertEqual(result.source, "nominatim")

    def test_language_suffix_and_unrelated_same_city_venue_do_not_block_match(self):
        football = stadium("Peristeri Stadium", city="Peristeri")
        unrelated = stadium("Andreas Papandreou Indoor Hall", city="Peristeri", latitude=38.002, longitude=23.688)
        result, _ = self.resolve(
            self.venue(name="Stadio Peristeriou", address=None, city="Athens"),
            [[football, unrelated]],
        )
        self.assertEqual(result.matched_label, "Peristeri Stadium")
        self.assertFalse(result.ambiguous)

    def test_exact_identity_and_shared_address_allow_adjacent_locality(self):
        candidate = stadium("GSP Stadium", city="Strovolos", country_code="cy")
        candidate.raw["address"]["road"] = "Pangkiprion Avenue"
        result, _ = self.resolve(
            self.venue(name="GSP Stadium", address="Pangkiprion Avenue", city="Nicosia", country="Cyprus"),
            [[candidate]],
        )
        self.assertEqual(result.source, "nominatim")

    def test_unique_non_physical_address_result_is_rejected(self):
        street = Location(35.3, 25.1, {
            "category": "highway", "type": "residential", "namedetails": {"name": "Parnassou"},
            "address": {"city": "Heraklion", "country_code": "gr"},
        })
        result, _ = self.resolve(self.venue(name="Stadio Thodoros Vardinoyannis", city="Heraklion"), [[street]])
        self.assertIsNone(result.source)

    def test_multiple_supported_physical_venues_remain_ambiguous(self):
        result, _ = self.resolve(self.venue(), [[
            stadium("Example Stadium", latitude=38.0, longitude=23.7),
            stadium("Example Stadium", latitude=38.1, longitude=23.8),
        ]])
        self.assertTrue(result.ambiguous)
        self.assertIsNone(result.source)

    def test_no_credible_physical_venue_remains_unresolved(self):
        result, _ = self.resolve(self.venue(), [[]])
        self.assertFalse(result.ambiguous)
        self.assertIsNone(result.source)

    def test_existing_exact_success_is_preserved(self):
        result, _ = self.resolve(self.venue(name="ETO Park", city="Győr", country="Hungary"), [[
            stadium("ETO Park", city="Győr", country_code="hu")
        ]])
        self.assertEqual((result.latitude, result.longitude), (38.0, 23.7))
        self.assertEqual(result.acceptance_reason, "structured_venue_identity_and_geography")

    def test_provider_774_style_wrong_city_address_result_is_rejected(self):
        wrong = Location(38.05, 23.77, {
            "category": "highway", "type": "residential", "namedetails": {"name": "Parnassou"},
            "address": {"suburb": "Irakleio, Athens", "country_code": "gr"},
        })
        result, _ = self.resolve(
            self.venue(name="Stadio Thódoros Vardinoyánnis", address="Parnassou", city="Heraklion"),
            [[wrong]],
        )
        self.assertIsNone(result.source)


if __name__ == "__main__":
    unittest.main()
