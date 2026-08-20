import unittest
from datetime import datetime, timezone

from fixture_time import fixture_datetime_utc, fixture_status_group
from main import _board_closed
from models import Fixture


class FixtureContractTests(unittest.TestCase):
    def test_datetime_contract_normalizes_aware_values_to_utc(self):
        value = datetime.fromisoformat("2026-08-20T15:00:00-04:00")
        self.assertEqual(fixture_datetime_utc(value).isoformat(), "2026-08-20T19:00:00+00:00")

    def test_datetime_contract_rejects_naive_values(self):
        with self.assertRaises(ValueError):
            fixture_datetime_utc(datetime(2026, 8, 20, 19, 0))

    def test_supported_status_groups(self):
        expected = {
            "NS": "upcoming", "1H": "live", "FT": "finished",
            "AET": "finished", "PEN": "finished", "PST": "postponed", "CANC": "cancelled",
        }
        self.assertEqual({status: fixture_status_group(status) for status in expected}, expected)

    def test_cancelled_board_is_closed_without_inferred_attendance(self):
        fixture = Fixture(fixture_id=1, fixture_date=datetime.now(timezone.utc), status="CANC")
        self.assertTrue(_board_closed(fixture))
        self.assertEqual(fixture_status_group(fixture.status), "cancelled")


if __name__ == "__main__":
    unittest.main()
