"""Global event identity, bounded scheduling and existing USA regression contracts."""
import copy
import io
import json
import tempfile
from contextlib import redirect_stdout
from pathlib import Path
from datetime import date,datetime,timedelta,timezone
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from sqlalchemy import text

from test_fixture_discovery import database,Client,payload
from ingestion.global_discovery import due_scopes,run_global_discovery,DiscoveryScope
from ingestion.pipeline import plan_fixture_discovery,run_fixture_discovery
from ingestion.pipeline import apply_fixture_discovery_plan

DAY=date(2026,11,4)
START=datetime(2026,10,28,tzinfo=timezone.utc)
END=datetime(2026,12,5,tzinfo=timezone.utc)
SCOPE=DiscoveryScope('England',45,'FA Cup',2026,'2026/27',('England','Wales'))


class ProvisionalKickoffLifecycleTests(unittest.TestCase):
    """Discovery inserts must join the existing nightly lifecycle, without a new ID."""

    def setUp(self):
        self.engine=database();self.addCleanup(self.engine.dispose)
        with self.engine.begin() as c:
            c.execute(text('DELETE FROM fixtures'))
            c.execute(text("INSERT INTO teams VALUES (505,'Inter'),(495,'Genoa')"))
            c.execute(text("INSERT INTO venues VALUES (23100,'Stadio Giuseppe Meazza','Milano','Italy',45.478097,9.123927,907,NULL)"))
            c.execute(text('CREATE TABLE fixture_supporter_links (supporter_id INTEGER, fixture_id INTEGER REFERENCES fixtures(fixture_id))'))
        self.scope=DiscoveryScope('Italy',137,'Coppa Italia',2026,'2026/27')
        self.item=dict(fixture=dict(id=1639884,date='2026-12-02T17:00:00+00:00',status=dict(short='NS'),venue=dict(id=None,name=None,city=None)),
            league=dict(id=137,season=2026,country='Italy',name='Coppa Italia',round='Round of 16'),
            teams=dict(home=dict(id=505,name='Inter'),away=dict(id=495,name='Genoa')),goals=dict(home=None,away=None))
        key=(1639884,137,2026,505,495,self.item['fixture']['date'])
        self.proofs={key:dict(venue_id=23100,source='https://www.inter.it/it/biglietti/intergenoacoppaitalia')}
        self.start=datetime(2026,11,4,tzinfo=timezone.utc);self.end=datetime(2027,1,1,tzinfo=timezone.utc)

    def plan(self,item=None,proofs=None):
        with self.engine.connect() as c:
            return plan_fixture_discovery(c,{(137,2026):[item or self.item]},self.start,self.end,
                approved_scopes=(self.scope,),event_proofs=self.proofs if proofs is None else proofs)

    def insert(self):
        p=self.plan();self.assertEqual(p['held'],[]);self.assertEqual(len(p['rows']),1)
        self.assertEqual(p['rows'][0]['fixture_date'].isoformat(),self.item['fixture']['date'])
        self.assertEqual(p['rows'][0]['status'],'NS')
        self.assertEqual(p['rows'][0]['venue_id'],23100)
        self.assertFalse({'provisional','confirmed','kickoff_confirmed'} & set(p['rows'][0]))
        self.assertEqual(apply_fixture_discovery_plan(self.engine,{(137,2026):[self.item]},self.start,self.end,
            expected_rows=p['rows'],approved_scopes=(self.scope,),event_proofs=self.proofs),1)

    def test_missing_venue_is_never_assigned_from_scheduling_policy(self):
        self.assertIsNone(self.plan(proofs={})['rows'][0]['venue_id'])

    def test_tbd_is_preserved_only_when_provider_supplies_it(self):
        self.item['fixture']['status']['short']='TBD'
        self.assertEqual(self.plan()['rows'][0]['status'],'TBD')

    def test_identity_conflict_is_not_a_provisional_kickoff(self):
        self.item['teams']['home']['name']='Different club'
        self.assertFalse(self.plan()['rows'])

    def test_insert_then_actual_nightly_reschedule_postpone_cancel_preserves_links(self):
        import refresh_fixture_states as refresh
        from unittest.mock import Mock
        self.insert()
        with self.engine.begin() as c:c.execute(text('INSERT INTO fixture_supporter_links VALUES (7,1639884)'))
        # Far-future inserts are selected when the existing window reaches them;
        # this as-of date puts the provisional kickoff inside the normal window.
        for status,kickoff in [('NS','2026-12-01T20:00:00+00:00'),('PST','2026-12-01T20:00:00+00:00'),('NS','2026-12-03T19:00:00+00:00'),('CANC','2026-12-03T19:00:00+00:00')]:
            item=copy.deepcopy(self.item);item['fixture'].update(date=kickoff,status=dict(short=status))
            client=Client();client.fixtures_by_ids=Mock(return_value=[item])
            env=dict(DATABASE_URL='synthetic',API_FOOTBALL_KEY='synthetic',ENABLE_EXPANDED_FIXTURE_REFRESH='true',
                ENABLE_NEW_FIXTURE_DISCOVERY='false',ENABLE_GLOBAL_FIXTURE_DISCOVERY='false')
            with self.subTest(status=status,kickoff=kickoff),tempfile.TemporaryDirectory() as folder:
                receipt=Path(folder)/'receipt.json'
                with patch.object(refresh,'create_engine',return_value=self.engine),patch.object(refresh,'ApiFootballClient',return_value=client),\
                     patch.dict('os.environ',env),patch('sys.argv',['refresh','--nightly','--as-of','2026-11-05','--write','--confirm-write','--report',str(receipt)]),redirect_stdout(io.StringIO()):
                    self.assertEqual(refresh.main(),0)
                client.fixtures_by_ids.assert_called_once_with([1639884])
                result=json.loads(receipt.read_text());self.assertTrue(result['commit_confirmed'])
                with self.engine.connect() as c:
                    row=c.execute(text('SELECT * FROM fixtures WHERE fixture_id=1639884')).mappings().one()
                    self.assertEqual((row['home_team_id'],row['away_team_id'],row['venue_id'],row['status']),(505,495,23100,status))
                    self.assertEqual(refresh.utc_datetime(row['fixture_date']),refresh.utc_datetime(kickoff))
                    self.assertEqual(c.execute(text('SELECT * FROM fixture_supporter_links')).all(),[(7,1639884)])
                    self.assertEqual(c.execute(text('SELECT count(*) FROM fixtures')).scalar_one(),1)
                # A new discovery observation after rescheduling cannot create another row.
                p=self.plan(item);self.assertFalse(p['rows']);self.assertFalse(p['held'])

    def test_reschedule_collision_fails_closed(self):
        from test_fixture_reconciliation import candidate,provider,KICKOFF
        from refresh_fixture_states import classify_candidate,validate_plan
        stored=candidate();moved=KICKOFF.replace(day=8)
        result,values=classify_candidate(stored,[provider(status='NS',home_goals=None,away_goals=None,fixture_date=moved)])
        checked=validate_plan([stored],[result],{stored.fixture_id:values},{(moved,1,2):{999}})
        self.assertFalse(checked['passed'])


def cray():
    f=payload(1646909)
    f['fixture'].update(date='2026-11-08T14:15:00+00:00',status={'short':'NS'})
    f['league'].update(id=45,country='England')
    f['teams']={'home':{'id':7711,'name':'Cray Wanderers'},'away':{'id':4686,'name':'Stockport County'}}
    f['goals']={'home':None,'away':None}
    return f


def scope_row(lid,cadence='daily'):
    return dict(country='England',league_id=lid,display_name='Cup',provider_season=2026,
        display_season='2026/27',cadence=cadence,review_status='REVIEWED',
        active_from='2026-01-01',active_until='2027-06-30')


class GlobalDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.engine=database();self.addCleanup(self.engine.dispose)
        with self.engine.begin() as c:
            c.execute(text("INSERT INTO teams VALUES (7711,'Cray Wanderers'),(4686,'Stockport County')"))
            c.execute(text("INSERT INTO venues VALUES (21325,'Flamingo Park','London','England',51.429584,.081368,21325,NULL)"))
    def plan(self,f=None,proofs=None,scopes=(SCOPE,)):
        with self.engine.connect() as c:
            return plan_fixture_discovery(c,{(45,2026):[cray() if f is None else f]},START,END,
                approved_scopes=scopes,event_proofs=proofs)
    def test_cray_exact_event_proof_reuses_existing_ground(self):
        key=(1646909,45,2026,7711,4686,'2026-11-08T14:15:00+00:00')
        proof={key:dict(venue_id=21325,source='https://www.cray-wanderers.com/official-fixture')}
        p=self.plan(proofs=proof)
        self.assertEqual(p['held'],[])
        self.assertEqual(p['rows'][0]['venue_id'],21325)
        self.assertEqual(p['location_outcomes'][1646909],'MAP_READY')
        f=cray();f['fixture']['date']='2026-11-08T15:00:00+00:00'
        self.assertIsNone(self.plan(f,proof)['rows'][0]['venue_id'])
    def test_missing_event_not_usual_home_inference(self):
        self.assertIsNone(self.plan()['rows'][0]['venue_id'])
    def test_stable_reference_handles_sponsor_label_and_region_suffix(self):
        f=cray();f['fixture']['venue']=dict(id=21325,name='Flamingo Park Sponsored Stadium',city='London, Greater London')
        self.assertEqual(self.plan(f)['rows'][0]['venue_id'],21325)
    def test_conflicting_city_remains_held(self):
        f=cray();f['fixture']['venue']=dict(id=21325,name='Flamingo Park',city='Manchester')
        self.assertEqual(self.plan(f)['held'][0]['reason'],'VENUE_LOCALITY_CONFLICT')
    def test_name_only_requires_compatible_location(self):
        f=cray();f['fixture']['venue']=dict(id=None,name='Flamingo Park',city='London')
        self.assertEqual(self.plan(f)['rows'][0]['venue_id'],21325)
        f['fixture']['venue']['city']='Manchester'
        self.assertFalse(self.plan(f)['rows'])
    def test_existing_physical_equivalence_deduplicates_refs(self):
        with self.engine.begin() as c:
            c.execute(text("INSERT INTO venues VALUES (999,'Old Flamingo Park','London','England',51.42,.08,21325,21325)"))
        f=cray();f['fixture']['venue']=dict(id=21325,name='Old Flamingo Park',city='London')
        self.assertEqual(self.plan(f)['rows'][0]['venue_id'],21325)
    def test_known_other_ground_label_conflicts_with_direct_reference(self):
        f=cray();f['fixture']['venue']=dict(id=21325,name='Athletic Club Boise Soccer Stadium',city='London')
        self.assertEqual(self.plan(f)['held'][0]['reason'],'VENUE_NAME_CONFLICT')
    def test_unknown_venue_null_and_missing_point_distinguished(self):
        f=cray();f['fixture']['venue']=dict(id=123456,name='Not yet mapped',city='London')
        self.assertIsNone(self.plan(f)['rows'][0]['venue_id'])
        with self.engine.begin() as c:c.execute(text('UPDATE venues SET latitude=NULL WHERE venue_id=21325'))
        f['fixture']['venue']=dict(id=21325,name='Flamingo Park',city='London')
        p=self.plan(f)
        self.assertEqual(p['rows'][0]['venue_id'],21325)
        self.assertEqual(p['location_outcomes'][1646909],'KNOWN_VENUE_MISSING_COORDINATES')
    def test_scope_country_season_and_canonical_team_protected(self):
        for change in ('country','season','team'):
            f=cray()
            if change=='country':f['league']['country']='USA'
            elif change=='season':f['league']['season']=2027
            else:f['teams']['home']['name']='Different club'
            self.assertFalse(self.plan(f)['rows'])
        self.assertEqual(self.plan(scopes=())['errors'],['UNAPPROVED_SCOPE'])
    def test_reviewed_same_id_abbreviation_is_scope_and_preimage_pinned(self):
        review=dict(provider_team_id=7711,canonical_team_id=7711,canonical_name='Cray Wanderers',
            observed_name='Cray',league_id=45,season=2026,source='https://www.cray-wanderers.com/')
        from dataclasses import replace
        scope=replace(SCOPE,team_reviews=(review,))
        f=cray();f['teams']['home']['name']='Cray'
        self.assertEqual(self.plan(f,scopes=(scope,))['rows'][0]['home_team'],'Cray Wanderers')
        with self.engine.begin() as c:c.execute(text("UPDATE teams SET team_name='Different entity' WHERE team_id=7711"))
        self.assertEqual(self.plan(f,scopes=(scope,))['held'][0]['reason'],'REVIEWED_TEAM_ALIAS_CONFLICT')
    def test_reviewed_venue_locality_does_not_merge_a_same_name_ground(self):
        from dataclasses import replace
        scope=replace(SCOPE,venue_reviews=(dict(venue_id=21325,localities=['Chislehurst'],source='https://www.cray-wanderers.com/contact/'),))
        f=cray();f['fixture']['venue']=dict(id=21325,name='Flamingo Park',city='Chislehurst')
        self.assertEqual(self.plan(f,scopes=(scope,))['rows'][0]['venue_id'],21325)
        f['fixture']['venue']['city']='Manchester'
        self.assertFalse(self.plan(f,scopes=(scope,))['rows'])
    def test_representative_european_scope_country_rules(self):
        for lid,country in [(81,'Germany'),(143,'Spain'),(66,'France')]:
            scope=DiscoveryScope(country,lid,'Reviewed cup',2026,'2026/27',(country,))
            f=cray();f['league'].update(id=lid,country=country)
            with self.engine.connect() as c:
                p=plan_fixture_discovery(c,{(lid,2026):[f]},START,END,approved_scopes=(scope,))
            self.assertEqual(p['held'],[])
            self.assertEqual(p['rows'][0]['country'],country)
    def test_payload_natural_duplicates_both_held(self):
        a,b=cray(),cray();b['fixture']['id']=9999
        with self.engine.connect() as c:
            p=plan_fixture_discovery(c,{(45,2026):[a,b]},START,END,approved_scopes=(SCOPE,))
        self.assertEqual(p['rows'],[]);self.assertEqual(len(p['held']),2)
    def test_usa_original_defaults_still_reuse_boise_proof(self):
        result=run_fixture_discovery(self.engine,Client(),DAY,write=True)
        self.assertTrue(result['passed'],result)
        again=run_fixture_discovery(self.engine,Client(),DAY,write=True)
        self.assertEqual((result['inserted'],again['inserted']),(1,0))
    def test_fifty_one_candidates_no_truncation(self):
        rows=[]
        for i in range(51):
            f=cray();f['fixture']['id']=1000+i;rows.append(f)
        with self.engine.connect() as c:
            p=plan_fixture_discovery(c,{(45,2026):rows},START,END,approved_scopes=(SCOPE,))
        self.assertTrue(p['overflow']);self.assertEqual(p['rows'],[])


class RotationTests(unittest.TestCase):
    def test_global_cannot_raise_shared_ceiling_above_750(self):
        client=Client([]);client.requests_made=748
        r=run_global_discovery(None,client,DAY,registry={'scopes':[scope_row(45)]},
            discovery_started_at=748,max_requests=1000)
        self.assertEqual(client.requests_made,748)
        self.assertEqual(r['shared_request_budget'],750)
        self.assertEqual(r['deferred_scopes'][0]['reason'],'REQUEST_BUDGET_DEFERRED')
    def test_expired_registry_is_reported_not_silently_complete(self):
        expired=scope_row(45);expired['active_until']='2026-01-01'
        report=run_global_discovery(None,Client([]),DAY,registry={'scopes':[expired]})
        self.assertFalse(report['coverage_complete'])
        self.assertEqual(report['ineligible_scopes'][0]['reason'],'EXPIRED_REGISTRY_READINESS_REQUIRED')
        self.assertEqual(report['provider_requests'],0)
    def test_realistic_weekly_overflow_reappears_without_starving_daily_cups(self):
        data={'scopes':[scope_row(i) for i in range(10000,10065)]+
            [scope_row(i,'weekly') for i in range(20000,20236)]}
        seen=set()
        def stage(engine,client,day,**kwargs):
            client.requests_made+=1
            return dict(passed=True,inserted=0,held_count=0,coverage_complete=True)
        with patch('ingestion.global_discovery.run_fixture_discovery',side_effect=stage):
            for offset in range(14):
                client=Client([]);client.requests_made=5
                r=run_global_discovery(None,client,DAY+timedelta(days=offset),registry=data,discovery_started_at=0)
                checked={g['league_id'] for g in r['groups']}
                self.assertTrue(set(range(10000,10065))<=checked)
                seen.update(checked)
                self.assertLessEqual(client.requests_made,100)
        self.assertEqual(seen,set(range(10000,10065))|set(range(20000,20236)))
    def test_daily_rotation_and_weekly_coverage_no_fixed_prefix(self):
        data={'scopes':[scope_row(i) for i in range(100,110)]+[scope_row(i,'weekly') for i in range(200,220)]}
        daily=set();weekly=set()
        for offset in range(140):
            due=due_scopes(data,DAY+timedelta(days=offset))
            # Extreme one-request global budget still gives both classes progress.
            if due:
                (daily if due[0]['cadence']=='daily' else weekly).add(due[0]['league_id'])
        self.assertEqual(daily,set(range(100,110)))
        self.assertEqual(weekly,set(range(200,220)))
    def test_expiry_country_and_unreviewed_scopes_excluded(self):
        a=scope_row(45);b=scope_row(81);b['review_status']='PENDING_SCOPE_OR_SEASON_REVIEW'
        c=scope_row(253);c['country']='USA'
        d=scope_row(48);d['active_until']='2026-01-01'
        data={'scopes':[a,b,c,d]}
        self.assertEqual([x['league_id'] for x in due_scopes(data,DAY)],[45])
        self.assertEqual(due_scopes(data,DAY,'France'),[])
    def test_shared_100_includes_existing_usa_and_reserves_highlights(self):
        client=Client([]);client.requests_made=353+5
        registry={'scopes':[scope_row(i) for i in range(100,220)]}
        def stage(engine,client,day,**kwargs):
            client.requests_made+=1
            return dict(passed=True,inserted=0,held_count=0,coverage_complete=True)
        with patch('ingestion.global_discovery.run_fixture_discovery',side_effect=stage):
            r=run_global_discovery(None,client,DAY,registry=registry,discovery_started_at=353)
        self.assertEqual(client.requests_made-353,100)
        self.assertEqual(len(r['deferred_scopes']),25)
        self.assertFalse(r['coverage_complete'])
    def test_quota_exhaustion_cannot_write_or_suppress_other_reports(self):
        client=Client([]);client.quota=None
        r=run_global_discovery(None,client,DAY,registry={'scopes':[scope_row(45)]})
        self.assertFalse(r['passed']);self.assertEqual(r['inserted'],0)
    def test_overflow_group_does_not_block_other_competitions(self):
        client=Client([])
        def stage(engine,client,day,**kwargs):
            client.requests_made+=1
            lid=kwargs['approved_scopes'][0].league_id
            return dict(passed=lid!=45,inserted=0,held_count=0,coverage_complete=lid!=45)
        with patch('ingestion.global_discovery.run_fixture_discovery',side_effect=stage):
            r=run_global_discovery(None,client,DAY,registry={'scopes':[scope_row(45),scope_row(48)]})
        self.assertEqual(len(r['groups']),2);self.assertFalse(r['passed'])


class NightlyIndependenceTests(unittest.TestCase):
    def test_global_failure_preserves_lifecycle_commit_and_highlights(self):
        import refresh_fixture_states as refresh
        engine=database();self.addCleanup(engine.dispose)
        client=Client([]);client.fixtures_by_ids=lambda ids:[]
        with tempfile.TemporaryDirectory() as folder:
            report=Path(folder)/'report.json'
            with patch.object(refresh,'create_engine',return_value=engine),\
                 patch.object(refresh,'ApiFootballClient',return_value=client),\
                 patch.object(refresh,'run_fixture_discovery',return_value=dict(passed=True,inserted=0)),\
                 patch('ingestion.global_discovery.run_global_discovery',side_effect=RuntimeError('synthetic stage failure')),\
                 patch('ingestion.matchday_highlights.run_demand_enrichment',return_value={}) as highlights,\
                 patch.dict('os.environ',{'DATABASE_URL':'synthetic','API_FOOTBALL_KEY':'synthetic',
                     'ENABLE_EXPANDED_FIXTURE_REFRESH':'false','ENABLE_GLOBAL_FIXTURE_DISCOVERY':'true'}),\
                 patch('sys.argv',['refresh','--nightly','--as-of','2026-11-04','--write','--confirm-write',
                     '--enrich-highlights','--report',str(report)]),redirect_stdout(io.StringIO()):
                self.assertEqual(refresh.main(),1)
            receipt=json.loads(report.read_text(encoding='utf-8'))
            self.assertTrue(receipt['commit_confirmed'])
            self.assertFalse(receipt['global_fixture_discovery']['passed'])
            highlights.assert_called_once()


class GlobalReadinessTests(unittest.TestCase):
    def test_existing_readiness_command_bounds_global_profile_to_explicit_ids(self):
        import ingestion.season_readiness as readiness
        with tempfile.TemporaryDirectory() as folder,\
             patch.object(readiness,'api_football_key',return_value='synthetic'),\
             patch.object(readiness,'database_url',return_value='sqlite://'),\
             patch.object(readiness,'ApiFootballClient'),patch.object(readiness,'create_engine'),\
             patch.object(readiness,'report',return_value=dict(competitions=[],requests=0,errors=[],quota=None)) as report,\
             redirect_stdout(io.StringIO()):
            self.assertEqual(readiness.main(['--profile','global-discovery','--league-id','45',
                '--league-id','81','--max-requests','6','--output',str(Path(folder)/'readiness.json')]),0)
        self.assertEqual({w.league_id for w in report.call_args.args[2]},{45,81})
        self.assertEqual(report.call_args.kwargs['max_requests'],6)
