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
            # Empty outcomes persist privately but remain null in the existing API contract.
            with Session(engine) as db:
                current=db.get(Fixture,1);current.home_goals=0;db.commit()
                empty=payload([goal(type='Card',detail='Yellow Card')])
                empty['goals']['home']=empty['score']['fulltime']['home']=0
                self.assertTrue(save_snapshot(db,1,empty,now+timedelta(days=1)));db.commit()
            with patch.object(main,'SessionLocal',lambda:Session(engine)):
                self.assertIsNone(main.get_fixture_social(1,None)['matchday_highlights'])
            with Session(engine) as db:
                self.assertEqual(db.query(FixtureEventSnapshot).count(),1)
                self.assertEqual(db.query(VenueVisit).count(),1)
            rollback=migration.with_name('20261022_fixture_event_snapshots_rollback.sql')
            with engine.connect() as c:c.exec_driver_sql(rollback.read_text());c.commit()
            with Session(engine) as db:self.assertEqual(db.get(Fixture,1).status,'FT')
        finally:
            with engine.begin() as c:c.exec_driver_sql('DROP SCHEMA IF EXISTS highlights_snapshot_test CASCADE')
            engine.dispose()


if __name__=='__main__':unittest.main()

class DemandEnrichmentTests(unittest.TestCase):
    def setUp(self):
        from models import User, VenueVisit, InterestedFixture
        self.User,self.Visit,self.Saved=User,VenueVisit,InterestedFixture
        self.engine=create_engine('sqlite://')
        for table in [User.__table__,Venue.__table__,Fixture.__table__,VenueVisit.__table__,InterestedFixture.__table__,FixtureEventSnapshot.__table__]:table.create(self.engine)
        self.now=datetime(2026,10,24,12,tzinfo=timezone.utc)
        self.db=Session(self.engine)
        self.db.add_all([User(user_id=1,is_anonymous=False,account_status='registered'),User(user_id=2,is_anonymous=True,account_status='anonymous'),User(user_id=3,is_anonymous=False,account_status='deleted')])
        self.db.add(Venue(venue_id=1,name='Synthetic ground'));self.db.commit()
        self.client=Mock();self.client.requests_made=0;self.client.quota_is_fresh.return_value=True;self.client.highlights_quota_available.return_value=True
        def fetch(ids):self.client.requests_made+=1;return [self.row(i) for i in ids]
        self.client.fixtures_by_ids.side_effect=fetch

    def tearDown(self):self.db.close();self.engine.dispose()

    def add(self,fid=1,*,went=True,owner=1,age=1,demand_age=None,**changes):
        f=Fixture(**vars(fixture(**(dict(fixture_id=fid,fixture_date=self.now-timedelta(days=age),venue_id=1)|changes))))
        self.db.add(f);self.db.flush()
        self.demand(fid,went=went,owner=owner,age=age if demand_age is None else demand_age)
        return f

    def demand(self,fid,*,went=True,owner=1,age=1):
        if went:self.db.add(self.Visit(visit_id=fid*10+owner,user_id=owner,fixture_id=fid,venue_id=1,source='manual',created_at=self.now-timedelta(days=age)))
        else:self.db.add(self.Saved(interested_id=fid*10+owner,user_id=owner,fixture_id=fid,going=False,created_at=self.now-timedelta(days=age)))
        self.db.commit()

    def row(self,fid=1,**changes):
        p=payload();p['fixture']['id']=fid;return p|changes

    def select(self,**kw):
        from ingestion.matchday_highlights import select_demand
        return [r['fixture_id'] for r in select_demand(self.db,now=self.now,**kw)]

    def run_stage(self,**kw):
        from ingestion.matchday_highlights import run_demand_enrichment
        return run_demand_enrichment(self.engine,self.client,enabled=True,now=self.now,**kw)

    def test_went_priority_and_cross_supporter_dedup(self):
        self.add(2,went=False);self.add(1);self.demand(1,owner=2);self.demand(1,went=False,owner=2)
        self.assertEqual(self.select(),[1,2])
        r=self.run_stage();self.assertEqual(r['inserted_or_updated'],[1,2]);self.assertEqual(self.client.requests_made,1)
        self.assertEqual(self.db.query(self.Visit).count(),2);self.assertEqual(self.db.query(self.Saved).count(),2)

    def test_ineligible_status_date_score_identity_and_holds(self):
        self.add(1,status='NS');self.add(2,status='AET');self.add(3,status='PEN');self.add(4,age=-1);self.add(5,home_goals=None);self.add(6,away_team_id=10);self.add(7);self.add(8,owner=3)
        self.assertEqual(self.select(held_ids=[7]),[])

    def test_did_you_go_requires_venue(self):
        self.add(1,went=False,venue_id=None);self.assertEqual(self.select(),[])

    def test_retrospective_new_demand_and_historical_manifest(self):
        self.add(1,age=150,demand_age=0);self.add(2,age=150)
        self.assertEqual(self.select(),[1]);self.assertEqual(self.select(historical=True),[1,2])
        self.assertEqual(self.select(retained_ids=[2]),[1,2])

    def test_retry_day7_weekday_and_day30(self):
        self.add(1,age=7);self.add(2,age=30)
        self.assertEqual(self.select(),[1] if self.now.weekday()==1 else [])
        from ingestion.matchday_highlights import select_demand
        monday=self.now+timedelta(days=(1-self.now.weekday())%7)
        self.assertEqual([r['fixture_id'] for r in select_demand(self.db,now=monday)],[1])

    def test_old_valid_snapshot_is_preserved_and_repeat_fetch_is_zero(self):
        f=self.add();save_snapshot(self.db,1,payload(),self.now-timedelta(days=60));self.db.commit()
        self.assertEqual(self.select(),[]);self.assertEqual(self.run_stage()['extra_requests'],0)
        self.assertEqual(enrich_batch(self.db,self.client,[1],enabled=True),{1:False});self.client.fixtures_by_ids.assert_not_called()

    def test_repeated_run_skips_new_snapshot(self):
        self.add();self.assertEqual(self.run_stage()['extra_requests'],1);self.assertEqual(self.run_stage()['extra_requests'],0)

    def test_retained_payload_uses_no_provider_even_without_quota(self):
        self.add(age=90);self.client.highlights_quota_available.return_value=False
        self.assertEqual(self.run_stage(provider_rows=[payload()])['inserted_or_updated'],[1]);self.client.fixtures_by_ids.assert_not_called();self.client.get.assert_not_called()

    def test_disabled_has_no_connections_or_requests(self):
        from ingestion.matchday_highlights import run_demand_enrichment
        r=run_demand_enrichment(None,self.client);self.assertFalse(r['enabled']);self.client.fixtures_by_ids.assert_not_called()

    def test_provider_error_missing_coverage_and_invalid_rows(self):
        self.add()
        for mode in ['error','missing','score','identity']:
            def fetch(ids):
                self.client.requests_made+=1
                if mode=='error':raise RuntimeError('synthetic')
                if mode=='missing':return []
                p=payload()
                if mode=='score':p['goals']['home']=2
                if mode=='identity':p['teams']['home']['id']=999
                return [p]
            self.client.fixtures_by_ids.side_effect=fetch;r=self.run_stage();self.assertEqual(self.db.query(FixtureEventSnapshot).count(),0)
            self.assertEqual(self.db.get(Fixture,1).home_goals,1)
            self.assertTrue(r['errors'] if mode=='error' else r['unavailable'])

    def test_invalid_previous_snapshot_is_not_overwritten_on_bad_coverage(self):
        f=self.add();save_snapshot(self.db,1,payload(),self.now-timedelta(days=1));self.db.commit();old=self.db.get(FixtureEventSnapshot,1).source_sha256
        f.home_goals=2;self.db.commit();self.client.fixtures_by_ids.side_effect=lambda ids:[]
        self.run_stage();self.db.expire_all();self.assertEqual(self.db.get(FixtureEventSnapshot,1).source_sha256,old)

    def test_two_requests_and_global_budget(self):
        for i in range(1,54):self.add(i)
        self.assertEqual(self.run_stage()['extra_requests'],2);self.assertEqual(self.db.query(FixtureEventSnapshot).count(),40)
        self.client.requests_made=749;self.assertEqual(self.run_stage(max_requests=750)['extra_requests'],1)

    def test_probe_counts_within_two_calls(self):
        for i in range(1,22):self.add(i)
        self.client.quota_is_fresh.return_value=False
        def probe(*a,**k):self.client.requests_made+=1
        self.client.get.side_effect=probe
        r=self.run_stage();self.assertEqual(r['extra_requests'],2);self.assertEqual(len(r['inserted_or_updated']),20)

    def test_quota_denied_or_exhausted_budget_never_fetch(self):
        self.add();self.client.highlights_quota_available.return_value=False;self.assertEqual(self.run_stage()['extra_requests'],0)
        self.client.highlights_quota_available.return_value=True;self.assertEqual(self.run_stage(max_requests=0)['extra_requests'],0)

    def test_duplicate_retained_rows_roll_back_batch(self):
        self.add();r=self.run_stage(provider_rows=[payload(),payload()]);self.assertTrue(r['errors']);self.assertEqual(self.db.query(FixtureEventSnapshot).count(),0)

    def test_preserves_five_existing_acceptance_snapshots(self):
        old={}
        for i in range(1,6):
            self.add(i);save_snapshot(self.db,i,self.row(i),self.now-timedelta(days=60));self.db.commit();old[i]=self.db.get(FixtureEventSnapshot,i).source_sha256
        self.add(6);self.assertEqual(self.run_stage()['inserted_or_updated'],[6]);self.client.fixtures_by_ids.assert_called_once_with([6])
        self.db.expire_all();self.assertEqual({i:self.db.get(FixtureEventSnapshot,i).source_sha256 for i in old},old)

    def test_quota_exhausted_by_first_batch_stops_second(self):
        for i in range(1,22):self.add(i)
        def fetch(ids):
            self.client.requests_made+=1;self.client.highlights_quota_available.return_value=False
            return [self.row(i) for i in ids]
        self.client.fixtures_by_ids.side_effect=fetch
        r=self.run_stage();self.assertEqual(r['extra_requests'],1);self.assertEqual(len(r['inserted_or_updated']),20);self.assertEqual(r['deferred'],1)

    def empty_row(self,fid=1):
        p=self.row(fid);p['goals']={'home':0,'away':0};p['score']['fulltime']={'home':0,'away':0}
        p['events']=[goal(type='Card',detail='Yellow Card'),goal(type='subst',detail='Substitution 1')]
        return p

    def test_empty_persists_hidden_and_later_runs_make_no_requests(self):
        from matchday_highlights import snapshot_is_valid
        from ingestion.matchday_highlights import run_demand_enrichment
        f=self.add(home_goals=0);p=self.empty_row();self.client.fixtures_by_ids.side_effect=None;self.client.fixtures_by_ids.return_value=[p]
        self.assertEqual(self.run_stage()['inserted_or_updated'],[1]);self.db.expire_all();s=self.db.get(FixtureEventSnapshot,1)
        self.assertEqual(s.payload['events'],p['events']);old=(s.source_sha256,s.fetched_at)
        self.assertTrue(snapshot_is_valid(f,s.payload));self.assertIsNone(project_highlights(f,s.payload));self.assertIsNone(fixture_highlights(self.db,f))
        r=run_demand_enrichment(self.engine,self.client,enabled=True,now=self.now+timedelta(days=9));self.assertEqual(r['extra_requests'],0);self.assertEqual(r['selected'],0)
        self.assertEqual(enrich_batch(self.db,self.client,[1],enabled=True),{1:False});self.client.fixtures_by_ids.assert_called_once_with([1]);self.client.get.assert_not_called()
        self.db.expire_all();s=self.db.get(FixtureEventSnapshot,1);self.assertEqual((s.source_sha256,s.fetched_at),old)

    def test_missing_empty_arrays_are_not_settled(self):
        from matchday_highlights import snapshot_is_valid
        self.add(home_goals=0)
        for missing in [[],None,'missing']:
            p=self.empty_row()
            if missing=='missing':p.pop('events')
            else:p['events']=missing
            self.assertFalse(snapshot_is_valid(self.db.get(Fixture,1),p));self.assertFalse(save_snapshot(self.db,1,p,self.now));self.db.commit()
        self.assertEqual(self.db.query(FixtureEventSnapshot).count(),0);self.assertEqual(self.select(),[1])

    def test_excluded_routine_types_can_settle_individually(self):
        from matchday_highlights import snapshot_is_valid
        f=self.add(home_goals=0)
        for event in self.empty_row()['events']:
            p=self.empty_row();p['events']=[event];self.assertTrue(snapshot_is_valid(f,p));self.assertIsNone(project_highlights(f,p))

    def test_unknown_var_and_ambiguous_dismissal_are_not_empty_evidence(self):
        from matchday_highlights import snapshot_is_valid
        f=self.add(home_goals=0)
        cases=[[goal(type='Var',detail='Goal cancelled')],[goal(type='Card',detail='Unknown card')],[goal(type='unknown',detail='unknown')],
               [goal(type='Card',detail='Second Yellow card'),goal(type='Card',detail='Red Card')],
               [goal(type='Card',detail='Yellow Card'),goal(type='Card',detail='Yellow Card')]]
        for events in cases:
            p=self.empty_row();p['events']=events;self.assertFalse(snapshot_is_valid(f,p));self.assertFalse(save_snapshot(self.db,1,p,self.now))
        self.assertEqual(self.db.query(FixtureEventSnapshot).count(),0)

    def test_malformed_empty_evidence_fails_closed(self):
        from matchday_highlights import snapshot_is_valid
        f=self.add(home_goals=0)
        cases=[goal(type='Card',detail='Yellow Card',time=dict(elapsed=None,extra=None)),goal(type='Card',detail='Yellow Card',team=dict(id=999)),
               goal(type='Card',detail='Yellow Card',time=dict(elapsed=45,extra=-1)),goal(type='subst',detail='Substitution unknown'),
               goal(type='Card',detail='Yellow Card',time=dict(elapsed=151,extra=None))]
        for event in cases:
            p=self.empty_row();p['events']=[event];self.assertFalse(snapshot_is_valid(f,p))

    def test_empty_identity_score_status_and_unknown_goal_rejected(self):
        from copy import deepcopy
        from matchday_highlights import snapshot_is_valid
        f=self.add(home_goals=0)
        for change in ['identity','score','fulltime','status','goal']:
            p=self.empty_row()
            if change=='identity':p['teams']['home']['id']=999
            if change=='score':p['goals']['home']=1
            if change=='fulltime':p['score']['fulltime']['away']=1
            if change=='status':p['fixture']['status']['short']='AET'
            if change=='goal':p['events'].append(goal())
            self.assertFalse(snapshot_is_valid(f,p));self.assertFalse(save_snapshot(self.db,1,p,self.now))

    def test_existing_red_snapshot_cannot_be_erased_by_empty(self):
        f=self.add(home_goals=0);p=self.empty_row();p['events']=[goal(type='Card',detail='Red Card')]
        self.assertTrue(save_snapshot(self.db,1,p,self.now));self.db.commit();s=self.db.get(FixtureEventSnapshot,1);old=(s.source_sha256,s.fetched_at,s.payload)
        self.assertFalse(save_snapshot(self.db,1,self.empty_row(),self.now+timedelta(days=1)));self.db.commit();s=self.db.get(FixtureEventSnapshot,1);self.assertEqual((s.source_sha256,s.fetched_at,s.payload),old)
        self.assertEqual(len(fixture_highlights(self.db,f)['events']),1)

    def test_empty_cache_revalidates_when_canonical_score_changes(self):
        f=self.add(home_goals=0);self.assertTrue(save_snapshot(self.db,1,self.empty_row(),self.now));self.db.commit();f.home_goals=1;self.db.commit()
        self.assertEqual(self.select(),[1]);self.assertIsNone(fixture_highlights(self.db,f));self.assertEqual(self.run_stage()['inserted_or_updated'],[1])
        self.db.expire_all();self.assertEqual(len(fixture_highlights(self.db,self.db.get(Fixture,1))['events']),1)

    def test_empty_cache_fails_closed_after_identity_or_status_drift(self):
        from matchday_highlights import snapshot_is_valid
        f=self.add(home_goals=0);p=self.empty_row();self.assertTrue(save_snapshot(self.db,1,p,self.now));self.db.commit()
        f.league_id=999;self.db.commit();self.assertFalse(snapshot_is_valid(f,p));self.assertEqual(self.select(),[1]);f.status='NS';self.db.commit();self.assertEqual(self.select(),[])

    def test_empty_provider_failure_retains_bounded_retry(self):
        from ingestion.matchday_highlights import run_demand_enrichment
        self.add(home_goals=0);self.client.fixtures_by_ids.side_effect=RuntimeError('synthetic failure')
        self.assertTrue(self.run_stage()['errors']);self.assertEqual(self.db.query(FixtureEventSnapshot).count(),0);self.assertEqual(self.select(),[1])
        self.assertEqual(run_demand_enrichment(self.engine,self.client,enabled=True,now=self.now+timedelta(days=31))['extra_requests'],0)

    def test_empty_payload_from_retained_real_0_0(self):
        from matchday_highlights import snapshot_is_valid
        root=Path(__file__).resolve().parents[4]
        source=root/'reports/highlights-historical-backfill-20261024/retrieved-rows.json'
        if not source.exists():self.skipTest('Optional retained public provider corpus')
        p=next(r for r in json.loads(source.read_text(encoding='utf-8')) if r['fixture']['id']==1555521)
        f=fixture(fixture_id=p['fixture']['id'],league_id=p['league']['id'],season=p['league']['season'],home_team_id=p['teams']['home']['id'],away_team_id=p['teams']['away']['id'],home_goals=0,away_goals=0)
        self.assertTrue(snapshot_is_valid(f,p));self.assertIsNone(project_highlights(f,p))
