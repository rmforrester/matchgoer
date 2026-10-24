import json
import os
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from matchday_highlights import project_highlights, save_snapshot, fixture_highlights, MAX_BYTES
from models import Fixture, FixtureEventSnapshot, Venue
from ingestion.matchday_highlights import enrich_batch


def fixture(**changes):
    values = dict(fixture_id=1, league_id=39, season=2026, home_team_id=10, away_team_id=20,
                  home_team="Home", away_team="Away", status="FT", home_goals=1, away_goals=0)
    return SimpleNamespace(**(values | changes))


def goal(**changes):
    return dict(time=dict(elapsed=45, extra=2), team=dict(id=10), player=dict(id=100, name="Scorer"),
                assist=dict(id=101, name="Creator"), type="Goal", detail="Normal Goal", comments=None) | changes


def payload(events=None):
    return dict(fixture=dict(id=1, status=dict(short="FT")), league=dict(id=39, season=2026),
                teams=dict(home=dict(id=10), away=dict(id=20)), goals=dict(home=1, away=0),
                score=dict(fulltime=dict(home=1, away=0)), events=[goal()] if events is None else events)


class HighlightsTests(unittest.TestCase):
    def test_goal_assist_stoppage_and_no_public_ids(self):
        result = project_highlights(fixture(), payload())
        self.assertEqual(result['events'][0], dict(kind='goal', minute=45, extra=2, player='Scorer', team='Home', assist='Creator'))
        self.assertNotIn('_id', json.dumps(result))
        self.assertFalse(result['partial'])

    def test_penalties_misses_and_own_goal_scoring_side(self):
        for detail, kind in [('Penalty','penalty'),('Own Goal','own_goal')]:
            result = project_highlights(fixture(), payload([goal(detail=detail), goal(detail='Missed Penalty')]))
            self.assertEqual([e['kind'] for e in result['events']], [kind,'missed_penalty'])
            self.assertEqual(result['events'][0]['team'], 'Home')

    def test_red_only_scoreless_match_is_usable(self):
        p=payload([goal(type='Card', detail='Red Card')]);p['goals']['home']=p['score']['fulltime']['home']=0
        self.assertEqual(project_highlights(fixture(home_goals=0),p)['events'][0]['kind'],'red_card')

    def test_excludes_yellow_substitution_var_and_second_yellow_pair(self):
        p=payload([goal(),goal(type='Card',detail='Yellow Card'),goal(type='subst',detail='Substitution 1'),
                   goal(type='Var',detail='Goal cancelled'),goal(type='Card',detail='Second Yellow card'),goal(type='Card',detail='Red Card')])
        self.assertEqual(len(project_highlights(fixture(),p)['events']),1)

    def test_nulls_preserved_and_partial(self):
        p=payload([goal(player=dict(id=None,name=None),time=dict(elapsed=None,extra=None))])
        result=project_highlights(fixture(),p)
        self.assertTrue(result['partial']);self.assertIsNone(result['events'][0]['player']);self.assertIsNone(result['events'][0]['minute'])

    def test_ambiguous_second_booking_is_not_presented_as_straight_red(self):
        p=payload([goal(),goal(type='Card',detail='Yellow Card'),
                   goal(type='Card',detail='Yellow Card',time=dict(elapsed=75,extra=None)),goal(type='Card',detail='Red Card')])
        self.assertEqual([e['kind'] for e in project_highlights(fixture(),p)['events']],['goal'])

    def test_exact_duplicate_not_double_counted(self):
        result=project_highlights(fixture(),payload([goal(),goal()]))
        self.assertEqual(len(result['events']),1);self.assertTrue(result['partial'])

    def test_incomplete_mismatch_unknown_side_and_unknown_goal_fail_closed(self):
        for p in [payload([]),payload([goal(team=dict(id=30))]),payload([goal(detail='Unknown Goal')])]:
            self.assertIsNone(project_highlights(fixture(),p))
        self.assertIsNone(project_highlights(fixture(home_goals=2),payload()))

    def test_identity_and_unverified_completion_fail_closed(self):
        for field in ['fixture_id','league_id','season','home_team_id','away_team_id']:
            self.assertIsNone(project_highlights(fixture(**{field:999}),payload()))
        for status in ['NS','PST','CANC','ABD','AET','PEN',None]:
            self.assertIsNone(project_highlights(fixture(status=status),payload()))

    def test_invalid_minutes_malformed_and_bounds(self):
        for events in [[None],[goal(time=dict(elapsed=-1,extra=None))],[goal(time=dict(elapsed=45,extra=-2))],[goal()]*301]:
            self.assertIsNone(project_highlights(fixture(),payload(events)))
        p=payload();p['fixture']['irrelevant']='x'*MAX_BYTES
        self.assertIsNone(project_highlights(fixture(),p))

    def test_chronological_stable_ties(self):
        p=payload([goal(),goal(type='Card',detail='Red Card',time=dict(elapsed=20,extra=None)),
                   goal(type='Card',detail='Red Card',player=dict(id=102,name='Other'),time=dict(elapsed=45,extra=2))])
        self.assertEqual([e['kind'] for e in project_highlights(fixture(),p)['events']],['red_card','goal','red_card'])

    def test_all_saved_provider_fixtures(self):
        # Public sporting-data fixtures retained from the authorised five-call sample.
        root=Path(__file__).resolve().parents[4]/'reports/matchday-highlights-feasibility-20261022/provider-sample'
        if not root.exists():
            self.skipTest('Optional full research corpus not bundled in application source')
        total=0
        for name in ['response-01.json','response-02.json']:
            for row in json.loads((root/name).read_text(encoding='utf-8'))['response']:
                f=fixture(fixture_id=row['fixture']['id'],league_id=row['league']['id'],season=row['league']['season'],
                          home_team_id=row['teams']['home']['id'],away_team_id=row['teams']['away']['id'],
                          home_team=row['teams']['home']['name'],away_team=row['teams']['away']['name'],
                          home_goals=row['goals']['home'],away_goals=row['goals']['away'])
                self.assertIsNotNone(project_highlights(f,row),row['fixture']['id']);total+=1
        self.assertEqual(total,40)


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.engine=create_engine('sqlite://')
        for table in [Venue.__table__,Fixture.__table__,FixtureEventSnapshot.__table__]:table.create(self.engine)
        self.db=Session(self.engine)
        self.db.add(Fixture(**vars(fixture())));self.db.commit()
        self.now=datetime.now(timezone.utc)

    def tearDown(self):
        self.db.close();self.engine.dispose()

    def test_replay_stale_fetch_and_fixture_preservation(self):
        self.assertTrue(save_snapshot(self.db,1,payload(),self.now));self.db.commit()
        self.assertFalse(save_snapshot(self.db,1,payload(),self.now))
        self.assertFalse(save_snapshot(self.db,1,payload(),self.now-timedelta(seconds=1)))
        self.assertEqual(len(self.db.scalars(select(FixtureEventSnapshot)).all()),1)
        self.assertEqual(self.db.get(Fixture,1).home_goals,1)
        self.assertEqual(self.db.get(Fixture,1).status,'FT')

    def test_bad_refresh_preserves_valid_snapshot_and_changed_scores_hide_it(self):
        save_snapshot(self.db,1,payload(),self.now);self.db.commit()
        self.assertFalse(save_snapshot(self.db,1,payload([]),self.now+timedelta(days=1)))
        self.assertIsNotNone(fixture_highlights(self.db,self.db.get(Fixture,1)))
        self.db.get(Fixture,1).home_goals=2
        self.assertIsNone(fixture_highlights(self.db,self.db.get(Fixture,1)))

    def test_no_missing_fixture_creation_or_private_data_tables(self):
        self.assertFalse(save_snapshot(self.db,2,payload(),self.now))
        self.assertIsNone(fixture_highlights(self.db,self.db.get(Fixture,1)))
        self.assertEqual(set(FixtureEventSnapshot.__table__.columns.keys()),{'fixture_id','payload','source_sha256','fetched_at'})

    def test_ingestion_disabled_and_one_bounded_batch(self):
        client=Mock();client.fixtures_by_ids.return_value=[payload()]
        with self.assertRaises(RuntimeError):enrich_batch(self.db,client,[1])
        client.fixtures_by_ids.assert_not_called()
        with self.assertRaises(ValueError):enrich_batch(self.db,client,list(range(1,22)),enabled=True)
        result=enrich_batch(self.db,client,[1,1],enabled=True)
        self.assertEqual(result,{1:True});client.fixtures_by_ids.assert_called_once_with([1])
        client.reset_mock()
        self.assertEqual(enrich_batch(self.db,client,[1],enabled=True),{1:False})
        client.fixtures_by_ids.assert_not_called()
        self.db.rollback();self.assertIsNone(self.db.get(FixtureEventSnapshot,1))

    def test_duplicate_provider_fixture_rejected_before_snapshot_write(self):
        client=Mock();client.fixtures_by_ids.return_value=[payload(),payload()]
        with self.assertRaises(ValueError):enrich_batch(self.db,client,[1],enabled=True)
        self.assertIsNone(self.db.get(FixtureEventSnapshot,1))

    def test_future_or_missing_fixture_never_calls_provider(self):
        client=Mock()
        for ids in [[2],[1]]:
            self.db.get(Fixture,1).status='NS'
            with self.assertRaises(ValueError):enrich_batch(self.db,client,ids,enabled=True)
        client.fixtures_by_ids.assert_not_called()


@unittest.skipUnless(os.getenv('MATCHGOER_LOCAL_POSTGRES_TEST') == 'TRUE', 'Explicit isolated loopback PostgreSQL opt-in required')
class PostgresSnapshotTests(unittest.TestCase):
    def test_migration_concurrent_writers_and_rollback(self):
        engine=create_engine('postgresql+psycopg2://fixture_test@127.0.0.1:55439/postgres',
                             connect_args={'options':'-c search_path=highlights_snapshot_test'})
        try:
            with engine.begin() as c:
                self.assertEqual(str(c.exec_driver_sql('select inet_server_addr()').scalar()),'127.0.0.1')
                c.exec_driver_sql('DROP SCHEMA IF EXISTS highlights_snapshot_test CASCADE')
                c.exec_driver_sql('CREATE SCHEMA highlights_snapshot_test')
            for table in [Venue.__table__,Fixture.__table__]:table.create(engine)
            migration=Path(__file__).parents[1]/'migrations/20261022_fixture_event_snapshots.sql'
            with engine.connect() as c:c.exec_driver_sql(migration.read_text());c.commit()
            with Session(engine) as db:
                db.add(Fixture(**vars(fixture())));db.commit()
            first_locked=threading.Event();release=threading.Event();results=[];errors=[]
            now=datetime.now(timezone.utc)
            def writer(when,first=False):
                try:
                    with Session(engine) as db:
                        if first:
                            db.query(Fixture).filter(Fixture.fixture_id==1).with_for_update().first()
                            first_locked.set();release.wait(5)
                        results.append(save_snapshot(db,1,payload(),when));db.commit()
                except Exception as error:errors.append(error)
            newest=threading.Thread(target=writer,args=(now,True));newest.start();self.assertTrue(first_locked.wait(5))
            stale=threading.Thread(target=writer,args=(now-timedelta(hours=1),));stale.start();release.set()
            newest.join(10);stale.join(10)
            self.assertFalse(newest.is_alive() or stale.is_alive());self.assertFalse(errors)
            self.assertEqual(sorted(results),[False,True])
            with Session(engine) as db:
                self.assertEqual(db.get(FixtureEventSnapshot,1).fetched_at,now)
                self.assertEqual(db.get(Fixture,1).home_goals,1)
            # Exercise the existing response: public events must not change private attendance.
            from models import Base, User, UserProfile, VenueVisit
            from identity import ResolvedIdentity
            import main
            Base.metadata.create_all(engine)
            with Session(engine) as db:
                db.add(Venue(venue_id=111,name='Synthetic Ground'))
                db.add_all([User(user_id=i,is_anonymous=False,account_status='registered') for i in [1,2]])
                db.flush()
                db.add_all([UserProfile(user_id=i,display_name='Synthetic Supporter') for i in [1,2]])
                db.get(Fixture,1).fixture_date=datetime(2026,10,1,tzinfo=timezone.utc)
                db.get(Fixture,1).venue_id=111
                db.add(VenueVisit(user_id=1,venue_id=111,fixture_id=1,visit_date=datetime(2026,10,1).date()))
                db.commit()
            responses=[]
            with patch.object(main,'SessionLocal',lambda:Session(engine)):
                for identity in [None,ResolvedIdentity(1,'registered',True,'test'),ResolvedIdentity(2,'registered',True,'test')]:
                    responses.append(main.get_fixture_social(1,identity))
            self.assertEqual([r['own_attendance']['attended'] for r in responses],[False,True,False])
            self.assertEqual(responses[0]['matchday_highlights'],responses[1]['matchday_highlights'])
            self.assertEqual(responses[1]['matchday_highlights'],responses[2]['matchday_highlights'])
            with Session(engine) as db:self.assertEqual(db.query(VenueVisit).count(),1)
            rollback=migration.with_name('20261022_fixture_event_snapshots_rollback.sql')
            with engine.connect() as c:c.exec_driver_sql(rollback.read_text());c.commit()
            with Session(engine) as db:self.assertEqual(db.get(Fixture,1).status,'FT')
        finally:
            with engine.begin() as c:c.exec_driver_sql('DROP SCHEMA IF EXISTS highlights_snapshot_test CASCADE')
            engine.dispose()


if __name__=='__main__':unittest.main()
