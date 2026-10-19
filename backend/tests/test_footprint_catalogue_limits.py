import copy
import json
from pathlib import Path
import tempfile
import unittest

from football_footprint import load_membership_catalogue, MAX_CATALOGUE_BYTES


class CatalogueLimitTests(unittest.TestCase):
    def fixture(self, count):
        scope = dict(competition_id=1, season=2026, name='League', country='Country',
                     start='2026-01-01', end='2026-12-31', total=1, complete=True,
                     source='https://official.test', members=[dict(team_id=1, venue_id=10,
                     evidence='https://official.test/home')])
        scopes = []
        for i in range(count):
            item = copy.deepcopy(scope);item['competition_id'] = i+1;scopes.append(item)
        return dict(version=1, scopes=scopes)

    def load(self, raw):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'catalogue.json';path.write_bytes(raw)
            return load_membership_catalogue(path)

    def test_scope_boundaries(self):
        for count in (400, 401, 1000):
            with self.subTest(count=count):
                self.assertEqual(len(self.load(json.dumps(self.fixture(count)).encode())['scopes']), count)
        with self.assertRaisesRegex(ValueError, 'oversized'):
            self.load(json.dumps(self.fixture(1001)).encode())

    def test_exact_byte_boundary_and_one_byte_over(self):
        raw = json.dumps(self.fixture(1)).encode()
        self.assertEqual(len(self.load(raw+b' '*(MAX_CATALOGUE_BYTES-len(raw)))['scopes']), 1)
        with self.assertRaisesRegex(ValueError, 'byte limit'):
            self.load(raw+b' '*(MAX_CATALOGUE_BYTES-len(raw)+1))

    def test_oversized_rejected_before_json_parse(self):
        with self.assertRaisesRegex(ValueError, 'byte limit'):
            self.load(b'x'*(MAX_CATALOGUE_BYTES+1))

    def test_duplicate_keys_and_bad_members_remain_rejected(self):
        data = self.fixture(2);data['scopes'][1] = copy.deepcopy(data['scopes'][0])
        with self.assertRaises(AssertionError):self.load(json.dumps(data).encode())
        data = self.fixture(1);data['scopes'][0]['total'] = 101
        with self.assertRaises(AssertionError):self.load(json.dumps(data).encode())

    def test_malformed_json_rejected(self):
        with self.assertRaises(json.JSONDecodeError):self.load(b'{')
