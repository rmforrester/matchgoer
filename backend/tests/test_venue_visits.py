import unittest
from datetime import date, datetime, timezone, timedelta
from unittest.mock import MagicMock, patch
from venue_resolution import VenueResolution

from fastapi import HTTPException

from main import _ensure_venue_visit
from models import Fixture, VenueVisit


class VenueVisitContractTests(unittest.TestCase):
    def setUp(self):
        # These original tests isolate attendance reconciliation, not DB locks.
        locks = patch('main.lock_ground', side_effect=lambda db, key: key)
        identities = patch('main.resolution', return_value=VenueResolution({}))
        locks.start(); identities.start()
        self.addCleanup(locks.stop); self.addCleanup(identities.stop)

    fixture_date = datetime(2026, 8, 30, 15, 0, tzinfo=timezone.utc)

    def db_with(self, visits, *, fixture_venue_id=11, fixture_id=99):
        fixture = Fixture(fixture_id=fixture_id, venue_id=fixture_venue_id, fixture_date=self.fixture_date, status="FT")
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


    def test_unplayed_or_unknown_fixture_statuses_are_rejected(self):
        for status in ["NS", "TBD", "PST", "CANC", "ABD", "AWD", "WO", "1H", "HT", "SUSP", None]:
            with self.subTest(status=status):
                db = self.db_with([])
                db.fixture_query.first.return_value.status = status
                with self.assertRaises(HTTPException) as failure:
                    _ensure_venue_visit(db, user_id=7, venue_id=11, fixture_id=99, visit_date=self.fixture_date.date(), source="fixture_confirmation")
                self.assertEqual(failure.exception.status_code, 409)
                db.add.assert_not_called()

    def test_future_completed_fixture_and_future_manual_date_are_rejected(self):
        db = self.db_with([])
        db.fixture_query.first.return_value.fixture_date = datetime.now(timezone.utc) + timedelta(days=2)
        with self.assertRaises(HTTPException):
            _ensure_venue_visit(db, user_id=7, venue_id=11, fixture_id=99, visit_date=None, source="fixture_confirmation")
        for fixture_id in [None, 99]:
            with self.assertRaises(HTTPException) as failure:
                _ensure_venue_visit(db, user_id=7, venue_id=11, fixture_id=fixture_id, visit_date=date.today()+timedelta(days=2), source="manual")
            self.assertEqual(failure.exception.status_code, 422)
        db.add.assert_not_called()

    def test_missing_or_naive_fixture_date_fails_closed(self):
        for value in [None, datetime(2020, 1, 1)]:
            db = self.db_with([]); db.fixture_query.first.return_value.fixture_date=value
            with self.assertRaises(HTTPException):
                _ensure_venue_visit(db, user_id=7, venue_id=11, fixture_id=99, visit_date=None, source="fixture_confirmation")
            db.add.assert_not_called()

    def test_future_fixture_attachment_does_not_mutate_existing_visit(self):
        from types import SimpleNamespace
        from main import update_venue_visit_fixture
        from schemas import VenueVisitUpdate
        visit=VenueVisit(visit_id=1,user_id=7,venue_id=11,fixture_id=None,visit_date=date(2026,8,30),source="manual")
        for status, kickoff in [("NS",self.fixture_date),("FT",datetime.now(timezone.utc)+timedelta(days=2))]:
            db=self.db_with([]);db.visits_query.first.return_value=visit
            db.fixture_query.first.return_value.status=status;db.fixture_query.first.return_value.fixture_date=kickoff
            with patch('main.SessionLocal',return_value=db),self.assertRaises(HTTPException):
                update_venue_visit_fixture(11,1,VenueVisitUpdate(fixture_id=99),SimpleNamespace(user_id=7))
            self.assertIsNone(visit.fixture_id);self.assertEqual(visit.visit_date,date(2026,8,30))
            db.commit.assert_not_called();db.rollback.assert_called_once()

    def test_direct_fixture_and_manual_api_cannot_bypass_eligibility(self):
        from types import SimpleNamespace
        from main import record_fixture_attendance,record_manual_venue_visit
        from schemas import VenueVisitCreate
        db=self.db_with([]);db.fixture_query.first.return_value.status="NS"
        with patch('main.SessionLocal',return_value=db),self.assertRaises(HTTPException):
            record_fixture_attendance(99,SimpleNamespace(user_id=7))
        db.commit.assert_not_called()
        db=self.db_with([]);db.fixture_query.first.return_value.fixture_date=None
        with patch('main.SessionLocal',return_value=db),self.assertRaises(HTTPException) as failure:
            record_manual_venue_visit(11,VenueVisitCreate(fixture_id=99),SimpleNamespace(user_id=7))
        self.assertEqual(failure.exception.status_code,409)
        db.commit.assert_not_called()
        with patch('main.SessionLocal',return_value=db),self.assertRaises(HTTPException):
            record_fixture_attendance(99,SimpleNamespace(user_id=7))
        db.commit.assert_not_called()

        db=self.db_with([])
        with patch('main.SessionLocal',return_value=db),self.assertRaises(HTTPException):
            record_manual_venue_visit(11,VenueVisitCreate(visit_date=date.today()+timedelta(days=2)),SimpleNamespace(user_id=7))
        db.commit.assert_not_called()


    def test_all_played_completion_statuses_and_undated_manual_history_are_valid(self):
        from types import SimpleNamespace
        from main import _validate_attendance_fixture, _validate_attendance_date
        for status in ["FT", "AET", "PEN"]:
            _validate_attendance_fixture(SimpleNamespace(status=status,fixture_date=self.fixture_date))
        _validate_attendance_date(None)
        _validate_attendance_date(date(1990,1,1))


if __name__ == "__main__":
    unittest.main()
