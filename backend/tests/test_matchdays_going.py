"""Explicit opt-in, isolated PostgreSQL contract tests; never hosted."""
import os
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

import main
from account_claim import _merge_into_existing_account
from identity import ResolvedIdentity
from models import Base, User, UserProfile, Venue, Fixture, InterestedFixture, FixtureMeetingIntent, VenueVisit, AnonymousSession
from schemas import GoingUpdate


@unittest.skipUnless(os.getenv("MATCHGOER_LOCAL_POSTGRES_TEST") == "TRUE", "Isolated loopback PostgreSQL opt-in required")
class MatchdaysGoingTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("postgresql+psycopg2://fixture_test@127.0.0.1:55439/postgres",
                                    connect_args={"options": "-c search_path=matchdays_going_test"})
        with self.engine.begin() as c:
            c.exec_driver_sql("DROP SCHEMA IF EXISTS matchdays_going_test CASCADE")
            c.exec_driver_sql("CREATE SCHEMA matchdays_going_test")
        Base.metadata.create_all(self.engine)
        # Use the established uniqueness contract for confirmed visits.
        with self.engine.begin() as c:
            c.exec_driver_sql("CREATE UNIQUE INDEX test_visit_fixture ON venue_visits(user_id,fixture_id) WHERE fixture_id IS NOT NULL")
            c.exec_driver_sql("CREATE UNIQUE INDEX test_visit_manual ON venue_visits(user_id,venue_id,visit_date) WHERE fixture_id IS NULL AND visit_date IS NOT NULL")
        self.sessions = sessionmaker(bind=self.engine)
        self.identity = ResolvedIdentity(1, "registered", True, "test")
        with self.sessions.begin() as db:
            db.add_all([User(user_id=1,is_anonymous=False,account_status="registered"), User(user_id=2), Venue(venue_id=1,name="Synthetic Ground")])
            db.flush()
            db.add(UserProfile(user_id=1,display_name="Supporter"))
            db.add_all([Fixture(fixture_id=i,venue_id=1,fixture_date=datetime(2026,10,8,14,tzinfo=timezone.utc),home_team="Home",away_team="Away",status="NS",league_name="Synthetic") for i in (1,2,3)])
            db.flush()
            db.add_all([InterestedFixture(user_id=1,fixture_id=1),InterestedFixture(user_id=1,fixture_id=2),InterestedFixture(user_id=2,fixture_id=1)])
            db.flush()
            db.add_all([FixtureMeetingIntent(user_id=1,fixture_id=1),FixtureMeetingIntent(user_id=1,fixture_id=2)])
        self.replace = patch.object(main, "SessionLocal", self.sessions)
        self.replace.start()

    def tearDown(self):
        self.replace.stop()
        self.engine.dispose()

    def counts(self):
        with self.sessions() as db:
            return tuple(db.query(model).count() for model in (InterestedFixture,FixtureMeetingIntent,VenueVisit))

    def test_existing_save_and_repeated_save_do_not_downgrade_going(self):
        self.assertFalse(main.get_interested_fixtures(self.identity)[0]["going"])
        main.update_going(1,GoingUpdate(going=True),self.identity)
        main.mark_fixture_interested(1,self.identity)
        self.assertTrue(next(x for x in main.get_interested_fixtures(self.identity) if x["fixture_id"]==1)["going"])

    def test_reversible_intention_preserves_social_and_has_no_visits(self):
        before=self.counts()
        for value in (True,False,True,True):
            result=main.update_going(1,GoingUpdate(going=value),self.identity)
            self.assertEqual(result["going"],value)
            self.assertEqual(self.counts(),before)

    def test_decline_only_own_fixture_and_preference(self):
        with self.sessions.begin() as db:db.add(VenueVisit(user_id=1,venue_id=1,fixture_id=2,visit_date=datetime(2026,10,8).date(),source="fixture_confirmation"))
        main.update_going(1,GoingUpdate(going=True),self.identity)
        main.remove_fixture_interested(1,self.identity)
        with self.sessions() as db:
            self.assertEqual({(x.user_id,x.fixture_id) for x in db.query(InterestedFixture)}, {(1,2),(2,1)})
            self.assertEqual({x.fixture_id for x in db.query(FixtureMeetingIntent)}, {2})
            self.assertEqual(db.query(VenueVisit).count(),1)

    def test_interested_and_going_to_went_keep_saves_and_preferences(self):
        main.update_going(1,GoingUpdate(going=True),self.identity)
        for fixture in (1,2):
            main.record_fixture_attendance(fixture,self.identity)
            main.record_fixture_attendance(fixture,self.identity)
        self.assertEqual(self.counts(),(3,2,2))
        # Old frontend's follow-up DELETE does not remove saved/social data.
        self.assertTrue(main.remove_fixture_interested(1,self.identity)["attendance_preserved"])
        self.assertEqual(self.counts(),(3,2,2))
        with self.assertRaises(HTTPException) as error:main.update_going(1,GoingUpdate(going=False),self.identity)
        self.assertEqual(error.exception.status_code,409)

    def test_cross_user_scope_and_unsaved_rejection(self):
        other=ResolvedIdentity(2,"anonymous",False,"test")
        main.update_going(1,GoingUpdate(going=True),other)
        with self.sessions() as db:
            self.assertFalse(db.query(InterestedFixture).filter_by(user_id=1,fixture_id=1).one().going)
        with self.assertRaises(HTTPException):main.update_going(2,GoingUpdate(going=True),other)
        with self.assertRaises(HTTPException):main.remove_fixture_interested(2,other)
        self.assertEqual(self.counts(),(3,2,0))

    def test_manual_visit_reused_and_history_preserved(self):
        with self.sessions.begin() as db:
            db.add(VenueVisit(user_id=1,venue_id=1,visit_date=datetime(2026,10,8).date(),source="manual"))
            db.add(VenueVisit(user_id=1,venue_id=1,visit_date=datetime(2025,1,1).date(),source="manual"))
        main.record_fixture_attendance(1,self.identity)
        self.assertEqual(self.counts(),(3,2,2))

    def test_account_merge_strongest_intention_keeps_target_meetings(self):
        with self.sessions.begin() as db:
            db.add(AnonymousSession(session_id="synthetic",user_id=2))
            db.query(InterestedFixture).filter_by(user_id=2,fixture_id=1).one().going=True
        with self.sessions.begin() as db:
            _merge_into_existing_account(db,source_user=db.get(User,2),source_session=db.get(AnonymousSession,"synthetic"),target_user_id=1,provider_identity=SimpleNamespace(),claimed_at=datetime.now(timezone.utc),failure_hook=None)
        with self.sessions() as db:
            self.assertTrue(db.query(InterestedFixture).filter_by(user_id=1,fixture_id=1).one().going)
            self.assertEqual(db.query(InterestedFixture).count(),2)
            self.assertEqual(db.query(FixtureMeetingIntent).count(),2)

    def test_migration_exact_old_rows_preserved(self):
        with self.engine.begin() as c:
            before=c.exec_driver_sql("SELECT interested_id,user_id,fixture_id,created_at FROM interested_fixtures ORDER BY interested_id").all()
            c.exec_driver_sql("ALTER TABLE interested_fixtures DROP COLUMN going")
        sql=(Path(__file__).resolve().parents[1]/"migrations/20261009_matchdays_going.sql").read_text()
        with self.engine.connect() as c:
            c.exec_driver_sql(sql)
        with self.engine.connect() as c:
            self.assertEqual(c.exec_driver_sql("SELECT interested_id,user_id,fixture_id,created_at FROM interested_fixtures ORDER BY interested_id").all(),before)
            self.assertEqual(c.exec_driver_sql("SELECT count(*) FROM interested_fixtures WHERE going").scalar(),0)
        self.assertEqual(self.counts(),(3,2,0))
