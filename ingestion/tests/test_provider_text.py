import html
import unittest

from ingestion.pipeline import TerraceTalkImporter
from ingestion.provider_text import normalize_provider_text


class ProviderTextTests(unittest.TestCase):
    def test_required_unicode_and_character_references(self):
        examples={
            'Villeneuve d&apos;Ascq':"Villeneuve d'Ascq",
            'Villeneuve d&#39;Ascq':"Villeneuve d'Ascq",
            'Villeneuve d&#x27;Ascq':"Villeneuve d'Ascq",
            'Dover Road &amp; Moneyfields Avenue':'Dover Road & Moneyfields Avenue',
            "Villeneuve d'Ascq":"Villeneuve d'Ascq",
            'Málaga, San Mamés, El Plantío, Saint-Étienne':'Málaga, San Mamés, El Plantío, Saint-Étienne',
            'Road &unknown; & nothing &notanentity':'Road &unknown; & nothing &notanentity',
            'Unknown &notanentity; stays literal':'Unknown &notanentity; stays literal',
            'Nested &amp;apos; name':'Nested &amp;apos; name',
            None:None,
        }
        for before,after in examples.items():
            with self.subTest(before=before):
                actual=normalize_provider_text(before)
                self.assertEqual(actual,after)
                self.assertEqual(normalize_provider_text(actual),actual)

    def test_boundary_only_normalizes_city_and_address(self):
        raw={'id':12,'name':'Opaque &amp; unchanged','city':'Villeneuve d&apos;Ascq','address':'Road &amp; Avenue'}
        record=TerraceTalkImporter._venue_record(raw,'France')
        self.assertEqual(record['name'],raw['name'])
        self.assertEqual(record['provider_venue_id'],12)
        self.assertEqual(record['city'],"Villeneuve d'Ascq")
        self.assertEqual(record['address'],'Road & Avenue')

    def test_decoded_text_still_requires_and_supports_escaped_rendering(self):
        decoded=normalize_provider_text('&lt;script&gt;alert(1)&lt;/script&gt;')
        self.assertEqual(decoded,'<script>alert(1)</script>')
        self.assertEqual(html.escape(decoded),'&lt;script&gt;alert(1)&lt;/script&gt;')


if __name__=='__main__':
    unittest.main()
