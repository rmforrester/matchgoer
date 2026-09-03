import unittest
from datetime import date
from unittest.mock import MagicMock

from main import _ensure_venue_visit
from models import VenueVisit


class VenueVisitContractTests(unittest.TestCase):
    def test_matching_manual_visit_is_promoted_to_fixture_attendance(self):
        visit = VenueVisit(user_id=7, venue_id=11, visit_date=date(2026, 8, 30), source="manual")
        query = MagicMock()
        query.filter.return_value = query
        query.with_for_update.return_value = query
        query.first.side_effect = [None, visit]
        db = MagicMock()
        db.query.return_value = query

        result = _ensure_venue_visit(
            db,
            user_id=7,
            venue_id=11,
            fixture_id=99,
            visit_date=date(2026, 8, 30),
            source="fixture_confirmation",
        )

        self.assertIs(result, visit)
        self.assertEqual((visit.fixture_id, visit.source), (99, "fixture_confirmation"))
        db.flush.assert_called_once_with()
        db.execute.assert_not_called()

    def test_existing_fixture_attendance_remains_idempotent(self):
        visit = VenueVisit(user_id=7, venue_id=11, fixture_id=99, visit_date=date(2026, 8, 30), source="fixture_confirmation")
        query = MagicMock()
        query.filter.return_value = query
        query.first.return_value = visit
        db = MagicMock()
        db.query.return_value = query

        result = _ensure_venue_visit(
            db,
            user_id=7,
            venue_id=11,
            fixture_id=99,
            visit_date=date(2026, 8, 30),
            source="fixture_confirmation",
        )

        self.assertIs(result, visit)
        db.flush.assert_not_called()
        db.execute.assert_not_called()


if __name__ == "__main__":
    unittest.main()
