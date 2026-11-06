"""Date-independent lifecycle membership, fair bounds, and stable supporter IDs."""
import copy,hashlib,io,json,os,tempfile,unittest
from contextlib import redirect_stdout
from datetime import date,datetime,timedelta,timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from sqlalchemy import text,Table,MetaData
import refresh_fixture_states as refresh
from test_automatic_venue_reconciliation import NightlyVenueIntegrationTests,NightlyVenuePostgresTests,item,KICKOFF
from test_fixture_discovery import Client

DAY=date(2026,12,3)
def candidate(fid,when,status='NS'):
    return SimpleNamespace(fixture_id=fid,fixture_date=when,status=status)
def due_day(fid,day=DAY):
    bucket=int(hashlib.sha256(str(fid).encode()).hexdigest(),16)%7
    return next(day+timedelta(days=i) for i in range(7) if (day+timedelta(days=i)).toordinal()%7==bucket)

class OutsideSelectionTests(unittest.TestCase):
    def test_status_membership_and_weekly_future_tracking(self):
        start,end=refresh.refresh_window(DAY)
        old=candidate(1,start-timedelta(days=180),'PST');future=candidate(2,end+timedelta(days=180))
        ignored=[candidate(3,start),candidate(4,end+timedelta(days=1),'CANC'),candidate(5,start-timedelta(days=300),'FT')]
        selected,receipt=refresh.select_outside_window([old,future]+ignored,due_day(2),start,end,50)
        self.assertEqual({r.fixture_id for r in selected},{1,2});self.assertEqual(receipt['eligible'],2)
        observed=set()
        for i in range(7):
            chosen,_=refresh.select_outside_window([future],DAY+timedelta(days=i),start,end,50)
            observed.update(r.fixture_id for r in chosen)
        self.assertEqual(observed,{2})
    def test_small_budget_rotates_both_classes_without_fixed_prefix(self):
        start,end=refresh.refresh_window(DAY)
        future=[candidate(fid,end+timedelta(days=100)) for fid in range(10,40)]
        older=[candidate(fid,start-timedelta(days=100)) for fid in range(1,6)]
        seen=set()
        for i in range(140):
            chosen,r=refresh.select_outside_window(older+future,DAY+timedelta(days=i),start,end,2)
            self.assertLessEqual(len(chosen),2);self.assertEqual(len({v.fixture_id for v in chosen}),len(chosen));seen.update(v.fixture_id for v in chosen)
        self.assertEqual(seen,{r.fixture_id for r in older+future})
    def test_zero_budget_has_explicit_deferrals_and_no_mutation(self):
        start,end=refresh.refresh_window(DAY);rows=[candidate(1,start-timedelta(days=1))];before=copy.deepcopy(vars(rows[0]))
        selected,r=refresh.select_outside_window(rows,DAY,start,end,0)
        self.assertEqual(selected,[]);self.assertEqual(r['due_deferred'],1);self.assertEqual(vars(rows[0]),before)
    def test_less_than_half_a_future_bucket_advances_by_whole_batches(self):
        start,end=refresh.refresh_window(DAY);rows=[candidate(fid,end+timedelta(days=900)) for fid in range(1000,1700)];seen=set()
        for i in range(56):
            selected,r=refresh.select_outside_window(rows,DAY+timedelta(days=i),start,end,17);self.assertLessEqual(len(selected),17);seen.update(v.fixture_id for v in selected)
        self.assertEqual(seen,{r.fixture_id for r in rows})

class ReviewedReusVenueTests(unittest.TestCase):
    def setup_context(self):
        from ingestion.global_discovery import load_registry,event_proofs
        reg=load_registry();proof=next(p for p in reg['event_proofs'] if p['fixture_id']==1644373)
        p=dict(fixture=dict(id=1644373,date=proof['kickoff'],status=dict(short='NS'),venue=dict(id=None,name='Estadi Municipal de Reus',city='Reus')),league=dict(id=143,season=2026,country='Spain'),teams=dict(home=dict(id=22136,name='Reddis'),away=dict(id=5251,name='Barakaldo')),goals=dict(home=None,away=None))
        r=SimpleNamespace(fixture_id=1644373,fixture_date=datetime.fromisoformat(proof['kickoff']),league_id=143,season=2026,home_team_id=22136,away_team_id=5251,home_team='Reddis',away_team='Barakaldo',country='Spain',status='NS',home_goals=None,away_goals=None,venue_id=24196)
        venues=[dict(venue_id=24196,name='Estadio Camp Nou Municipal',city='Reus',country='Spain',latitude=41.156361,longitude=1.085796,provider_venue_id=1468),dict(venue_id=27736,name='Estadi Municipal de Reus',city='Reus',country='Spain',latitude=41.155108,longitude=1.086687,provider_venue_id=None)]
        context=dict(venue_countries=['Spain'],venue_reviews=[v for v in reg['venue_reviews'] if v['venue_id']==24196],event_proofs=event_proofs(reg));return r,p,venues,context
    def test_exact_cup_proof_reuses_original_main_stadium_not_conflicting_pin(self):
        r,p,venues,context=self.setup_context();self.assertEqual(refresh.resolve_venue(r,p,venues,[],[],context),(24196,'MATCHED'))
    def test_new_date_keeps_verified_ground_when_exact_proof_no_longer_matches(self):
        r,p,venues,context=self.setup_context();p['fixture']['date']=(r.fixture_date+timedelta(days=70)).isoformat()
        decision,values=refresh.classify_candidate(r,[p],(venues,[],[],context));self.assertEqual(decision['classification'],'WOULD_UPDATE_RESCHEDULED');self.assertEqual(values['venue_id'],24196)
    def test_other_cup_fixture_cannot_borrow_reviewed_main_ground_assignment(self):
        r,p,venues,context=self.setup_context();p['fixture']['id']+=1
        self.assertEqual(refresh.resolve_venue(SimpleNamespace(**dict(vars(r),venue_id=None)),p,venues,[],[],context),(None,'AMBIGUOUS'))

class OutsideWindowScenarios:
    def run_at(self,p,day=DAY,budget=750,quota=None,inject=None,discovery=False):
        client=Client();client.quota=quota if quota is not None else client.quota;requested=[]
        def fetch(ids):
            client.requests_made+=1;requested.extend(ids)
            return [copy.deepcopy(p)] if p['fixture']['id'] in ids else []
        client.fixtures_by_ids=fetch
        env=dict(DATABASE_URL='synthetic',API_FOOTBALL_KEY='synthetic',ENABLE_EXPANDED_FIXTURE_REFRESH='true',ENABLE_NEW_FIXTURE_DISCOVERY=str(discovery).lower(),ENABLE_GLOBAL_FIXTURE_DISCOVERY='false')
        with tempfile.TemporaryDirectory() as folder:
            receipt=Path(folder)/'receipt.json';args=['refresh','--nightly','--as-of',day.isoformat(),'--max-requests',str(budget),'--write','--confirm-write','--report',str(receipt)]
            with patch.object(refresh,'create_engine',return_value=self.engine),patch.object(refresh,'ApiFootballClient',return_value=client),patch.dict(os.environ,env),patch('sys.argv',args),patch.object(refresh,'reconcile_final_state',side_effect=inject,wraps=refresh.reconcile_final_state),patch.object(refresh,'run_fixture_discovery',return_value=dict(passed=True,inserted=0)) as discover,redirect_stdout(io.StringIO()):
                code=refresh.main()
            return code,json.loads(receipt.read_text()),requested,client.requests_made,discover.call_count
    def set_stored(self,when,status='NS'):
        with self.engine.begin() as c:
            table=Table('fixtures',MetaData(),autoload_with=c)
            c.execute(table.update().values(fixture_date=when,status=status,venue_id=23100))
            c.execute(text('CREATE TABLE IF NOT EXISTS interested_fixture_links (user_id INTEGER, fixture_id INTEGER REFERENCES fixtures(fixture_id))'))
            c.execute(text('CREATE TABLE IF NOT EXISTS attended_matchdays (user_id INTEGER, fixture_id INTEGER REFERENCES fixtures(fixture_id))'))
            for name in ['interested_fixture_links','attended_matchdays']:
                c.execute(text('DELETE FROM '+name));c.execute(text('INSERT INTO '+name+' VALUES (17,1639884)'))
    def assert_links(self):
        with self.engine.connect() as c:
            for name in ['interested_fixture_links','attended_matchdays']:self.assertEqual(c.execute(text('SELECT * FROM '+name)).all(),[(17,1639884)])
            self.assertEqual(c.execute(text('SELECT count(*) FROM fixtures')).scalar_one(),1)
            self.assertEqual(c.execute(text('SELECT content FROM editorial')).scalar_one(),'must remain unchanged')
    def test_months_old_postponement_repeated_future_moves_venue_and_cancellation(self):
        self.set_stored(datetime(2026,4,1,tzinfo=timezone.utc),'PST');p=item(dict(id=907,name='San Siro',city='Milano'))
        p['fixture']['date']='2027-03-01T17:00:00+00:00'
        code,r,ids,calls,_=self.run_at(p);self.assertEqual(code,0,r);self.assertEqual(ids,[1639884]);self.assertTrue(r['commit_confirmed']);self.assertEqual(self.state()['status'],'NS');self.assert_links()
        day=due_day(1639884)
        for i in range(3):
            p['fixture']['date']=f'2027-0{6+i}-01T17:00:00+00:00';p['fixture']['venue']=dict(id=909,name='Alternative Ground',city='Milano')
            code,r,ids,calls,_=self.run_at(p,day+timedelta(days=7*i));self.assertEqual(code,0,r);self.assertEqual(self.state()['venue_id'],99);self.assertEqual(refresh.utc_datetime(self.state()['fixture_date']).isoformat(),p['fixture']['date']);self.assert_links()
        p['fixture']['venue']=None;p['fixture']['status']['short']='PST'
        self.assertEqual(self.run_at(p,day)[0],0);self.assertEqual(self.state()['venue_id'],99);self.assert_links()
        p['fixture']['status']['short']='CANC'
        self.assertEqual(self.run_at(p,day)[0],0);self.assertEqual(self.state()['status'],'CANC');self.assert_links()
        p['fixture']['status']['short']='NS';code,r,ids,calls,_=self.run_at(p,day)
        self.assertEqual(ids,[]);self.assertEqual(calls,0);self.assertEqual(self.state()['status'],'CANC');self.assert_links()
    def test_repeated_execution_is_idempotent_and_precommit_failure_rolls_back(self):
        self.set_stored(datetime(2026,1,1,tzinfo=timezone.utc),'PST');before=self.state();p=item(dict(id=909,name='Alternative Ground',city='Milano'))
        p['fixture']['date']='2027-06-01T17:00:00+00:00'
        code,r,_,_,_=self.run_at(p,inject=RuntimeError('outside-window readback failure'));self.assertEqual(code,1);self.assertFalse(r['commit_confirmed']);self.assertEqual(self.state(),before);self.assert_links()
        self.assertEqual(self.run_at(p)[0],0);after=self.state();code,r,_,_,_=self.run_at(p,due_day(1639884));self.assertEqual(code,0,r);self.assertEqual(r['proposed_fixture_rows_changed'],0);self.assertEqual(self.state(),after);self.assert_links()
    def test_in_window_fixture_moved_months_forward_stays_in_future_tracking(self):
        self.set_stored(KICKOFF);p=item(dict(id=907,name='San Siro',city='Milano'));p['fixture']['date']='2027-06-01T17:00:00+00:00'
        code,r,ids,calls,_=self.run_at(p);self.assertEqual(code,0,r);self.assertEqual(ids,[1639884]);self.assertEqual(r['outside_window_tracking']['requested_ids'],[])
        p['fixture']['date']='2027-09-01T18:00:00+00:00'
        code,r,ids,calls,_=self.run_at(p,due_day(1639884));self.assertEqual(code,0,r);self.assertEqual(r['outside_window_tracking']['requested_ids'],[1639884]);self.assertEqual(refresh.utc_datetime(self.state()['fixture_date']).isoformat(),p['fixture']['date']);self.assert_links()
    def test_tiny_request_limit_is_honored_for_old_tracking(self):
        self.set_stored(datetime(2026,1,1,tzinfo=timezone.utc),'PST');p=item()
        code,r,ids,calls,_=self.run_at(p,budget=2);self.assertEqual(code,0,r);self.assertEqual(ids,[1639884]);self.assertLessEqual(calls,2);self.assert_links()
    def test_quota_deferral_never_claims_provider_missing_or_erases_ground(self):
        self.set_stored(datetime(2026,1,1,tzinfo=timezone.utc));before=self.state();p=item()
        code,r,ids,calls,_=self.run_at(p,quota=dict(daily_remaining=100,minute_remaining=10))
        self.assertEqual(ids,[]);self.assertEqual(calls,0);self.assertEqual(r['outside_window_tracking']['quota_deferred_ids'],[1639884]);self.assertEqual(r['classification_counts']['PROVIDER_MISSING'],0);self.assertEqual(self.state(),before)
    def test_downstream_discovery_budget_reserved_even_with_outside_backlog(self):
        self.set_stored(datetime(2026,1,1,tzinfo=timezone.utc));p=item();code,r,ids,calls,discovery=self.run_at(p,budget=6,discovery=True)
        self.assertEqual(ids,[]);self.assertEqual(calls,0);self.assertEqual(discovery,1);self.assertLessEqual(calls,6);self.assertEqual(r['outside_window_tracking']['reserved_downstream_requests'],6)

class OutsideWindowSQLiteTests(OutsideWindowScenarios,NightlyVenueIntegrationTests):
    pass

@unittest.skipUnless(os.getenv('MATCHGOER_LOCAL_POSTGRES_TEST')=='TRUE','Explicit fixed loopback PostgreSQL opt-in required')
class OutsideWindowPostgresTests(OutsideWindowScenarios,NightlyVenuePostgresTests):
    pass
