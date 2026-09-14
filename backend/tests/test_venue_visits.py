import unittest
from datetime import date, datetime, timezone
from unittest.mock import MagicMock

from fastapi import HTTPException

from main import _ensure_venue_visit
from models import Fixture, VenueVisit


class VenueVisitContractTests(unittest.TestCase):
    fixture_date = datetime(2026, 8, 30, 15, 0, tzinfo=timezone.utc)

    def db_with(self, visits, *, fixture_venue_id=11, fixture_id=99):
        fixture = Fixture(fixture_id=fixture_id, venue_id=fixture_venue_id, fixture_date=self.fixture_date)
        fixture_query = MagicMock()
        fixture_query.filter.return_value = fixture_query
        fixture_query.first.return_value = fixture
        visits_query = MagicMock()
        visits_query.filter.return_value = visits_query
        visits_query.order_by.return_value = visits_query
        visits_query.with_for_update.return_value = visits_query
        visits_query.all.return_value = visits
        db = MagicMock()
        db.query.side_effect = lambda model: fixture_query if model is Fixture else visits_query
        db.fixture_query = fixture_query
        db.visits_query = visits_query
        return db

    def test_matching_manual_visit_is_promoted_to_fixture_attendance(self):
        visit = VenueVisit(user_id=7, venue_id=11, visit_date=date(2026, 8, 30), source="manual")
        db = self.db_with([visit])

        result = _ensure_venue_visit(
            db,
            user_id=7,
            venue_id=11,
            fixture_id=99,
            visit_date=date(2026, 8, 30),
            source="fixture_confirmation",
        )

        self.assertIs(result, visit)
        self.assertEqual((visit.fixture_id, visit.source), (99, "manual"))
        db.flush.assert_called_once_with()
        db.execute.assert_not_called()

    def test_existing_fixture_attendance_remains_idempotent(self):
        visit = VenueVisit(user_id=7, venue_id=11, fixture_id=99, visit_date=date(2026, 8, 30), source="fixture_confirmation")
        db = self.db_with([visit])

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

    def test_no_manual_visit_creates_normal_fixture_visit(self):
        db = self.db_with([])
        created = VenueVisit(user_id=7, venue_id=11, fixture_id=99, visit_date=date(2026, 8, 30), source="fixture_confirmation")
        resolved_query = MagicMock()
        resolved_query.filter.return_value = resolved_query
        resolved_query.first.return_value = created
        db.query.side_effect = [db.fixture_query, db.visits_query, resolved_query]
        result = _ensure_venue_visit(
            db, user_id=7, venue_id=11, fixture_id=99,
            visit_date=date(2026, 8, 30), source="fixture_confirmation",
        )
        self.assertIs(result, created)
        insert = db.execute.call_args.args[0]
        self.assertEqual(insert.compile().params["visit_date"], date(2026, 8, 30))

    def test_multiple_matching_manual_visits_fail_closed(self):
        visits = [
            VenueVisit(visit_id=1, user_id=7, venue_id=11, visit_date=date(2026, 8, 30), source="manual"),
            VenueVisit(visit_id=2, user_id=7, venue_id=11, visit_date=date(2026, 8, 30), source="manual"),
        ]
        db = self.db_with(visits)
        with self.assertRaises(HTTPException) as raised:
            _ensure_venue_visit(db, user_id=7, venue_id=11, fixture_id=99, visit_date=date(2026, 8, 30), source="fixture_confirmation")
        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(raised.exception.detail["code"], "VENUE_VISIT_RECONCILIATION_CONFLICT")
        db.flush.assert_not_called()
        db.execute.assert_not_called()

    def test_fixture_venue_mismatch_fails_closed(self):
        db = self.db_with([], fixture_venue_id=12)
        with self.assertRaises(HTTPException) as raised:
            _ensure_venue_visit(db, user_id=7, venue_id=11, fixture_id=99, visit_date=date(2026, 8, 30), source="fixture_confirmation")
        self.assertEqual(raised.exception.status_code, 409)
        db.execute.assert_not_called()

    def test_different_date_manual_visit_is_not_reused(self):
        other_visit = VenueVisit(user_id=7, venue_id=11, visit_date=date(2026, 8, 29), source="manual")
        db = self.db_with([other_visit])
        created = VenueVisit(user_id=7, venue_id=11, fixture_id=99, visit_date=date(2026, 8, 30), source="fixture_confirmation")
        resolved_query = MagicMock()
        resolved_query.filter.return_value = resolved_query
        resolved_query.first.return_value = created
        db.query.side_effect = [db.fixture_query, db.visits_query, resolved_query]
        result = _ensure_venue_visit(
            db, user_id=7, venue_id=11, fixture_id=99,
            visit_date=date(2026, 8, 29), source="fixture_confirmation",
        )
        self.assertIs(result, created)
        self.assertIsNone(other_visit.fixture_id)
        db.execute.assert_called_once()

    def test_same_date_different_venue_manual_visit_is_not_reused(self):
        other_visit = VenueVisit(user_id=7, venue_id=12, visit_date=date(2026, 8, 30), source="manual")
        db = self.db_with([other_visit])
        created = VenueVisit(user_id=7, venue_id=11, fixture_id=99, visit_date=date(2026, 8, 30), source="fixture_confirmation")
        resolved_query = MagicMock()
        resolved_query.filter.return_value = resolved_query
        resolved_query.first.return_value = created
        db.query.side_effect = [db.fixture_query, db.visits_query, resolved_query]
        result = _ensure_venue_visit(db, user_id=7, venue_id=11, fixture_id=99, visit_date=date(2026, 8, 30), source="fixture_confirmation")
        self.assertIs(result, created)
        self.assertIsNone(other_visit.fixture_id)
        db.execute.assert_called_once()

    def test_add_ground_manual_visit_behavior_is_unchanged(self):
        visit = VenueVisit(user_id=7, venue_id=11, visit_date=date(2026, 8, 30), source="manual")
        query = MagicMock()
        query.filter.return_value = query
        query.first.return_value = visit
        db = MagicMock()
        db.query.return_value = query
        result = _ensure_venue_visit(
            db, user_id=7, venue_id=11, fixture_id=None,
            visit_date=date(2026, 8, 30), source="manual",
        )
        self.assertIs(result, visit)
        self.assertEqual((visit.fixture_id, visit.source), (None, "manual"))
        db.execute.assert_called_once()


if __name__ == "__main__":
    unittest.main()
