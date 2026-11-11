"""Existing nightly entry point: canonical venue reuse, retries and atomic recovery."""
import copy
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from datetime import datetime,timezone
from sqlalchemy import create_engine,text,MetaData,DateTime,Table
import refresh_fixture_states as refresh
from ingestion.discovery_venues import reviewed_home_proof
from test_fixture_discovery import database,Client

KICKOFF=datetime(2026,12,2,17,tzinfo=timezone.utc)

def item(venue=None,status='NS'):
    return dict(fixture=dict(id=1639884,date=KICKOFF.isoformat(),status=dict(short=status),venue=venue),
        league=dict(id=137,season=2026,country='Italy',round='Round of 16'),
        teams=dict(home=dict(id=505,name='Inter'),away=dict(id=495,name='Genoa')),goals=dict(home=None,away=None))

def row(vid=None):
    return SimpleNamespace(fixture_id=1639884,fixture_date=KICKOFF,status='NS',home_goals=None,away_goals=None,
        league_id=137,season=2026,home_team_id=505,away_team_id=495,home_team='Inter',away_team='Genoa',
        venue_id=vid,country='Italy',venue_name='San Siro',venue_city='Milano')

def context():
    return ([dict(venue_id=23100,name='Stadio Giuseppe Meazza',city='Milano',country='Italy',latitude=45.478097,longitude=9.123927,provider_venue_id=907),
             dict(venue_id=99,name='Alternative Ground',city='Milano',country='Italy',latitude=45.5,longitude=9.2,provider_venue_id=909)],
        [dict(venue_id=23100,provider='api_football',provider_venue_id=907,valid_to=None)],
        [dict(venue_id=23100,name='San Siro',valid_to=None)])

class AutomaticVenueTests(unittest.TestCase):
    def test_null_to_known_and_idempotence(self):
        r=row();p=item(dict(id=907,name='San Siro',city='Milano'))
        m,v=refresh.classify_candidate(r,[p],context());self.assertEqual(v['venue_id'],23100)
        r.venue_id=23100;self.assertIsNone(refresh.classify_candidate(r,[p],context())[1])
    def test_provider_id_sponsorship_rename_is_not_a_new_ground(self):
        r=row(23100);m,v=refresh.classify_candidate(r,[item(dict(id=907,name='Sponsored Meazza',city='Milano'))],context())
        self.assertEqual(m['venue_mapping'],'MATCHED');self.assertIsNone(v);self.assertIn('name',m['venue_label_changes'])
    def test_exact_alias_without_provider_id(self):
        self.assertEqual(refresh.resolve_venue(row(),item(dict(id=None,name='San Siro',city='Milano')),*context()),(23100,'MATCHED'))
    def test_unambiguous_reassignment(self):
        self.assertEqual(refresh.resolve_venue(row(23100),item(dict(id=909,name='Alternative Ground',city='Milano')),*context()),(99,'MATCHED'))
    def test_omission_never_erases_old_ground(self):
        self.assertEqual(refresh.resolve_venue(row(23100),item(),*context()),(23100,'MISSING'))
    def test_other_known_ground_name_conflicts_with_provider_id(self):
        self.assertEqual(refresh.resolve_venue(row(23100),item(dict(id=909,name='San Siro',city='Milano')),*context()),(23100,'DISPUTED'))
    def test_conflicting_city_and_unknown_provider_are_held(self):
        for venue in [dict(id=907,name='San Siro',city='Rome'),dict(id=99999,name='Unknown',city='Rome')]:
            vid,status=refresh.resolve_venue(row(23100),item(venue),*context());self.assertEqual(vid,23100);self.assertIn(status,{'DISPUTED','UNKNOWN'})
    def test_physical_equivalence_is_reused(self):
        v,r,a=context();v.append(dict(v[0],venue_id=23101,provider_venue_id=None,canonical_venue_id=23100));r.append(dict(venue_id=23101,provider='api_football',provider_venue_id=907,valid_to=None))
        self.assertEqual(refresh.resolve_venue(row(),item(dict(id=907,name='San Siro',city='Milano')),v,r,a),(23100,'MATCHED'))
    def test_missing_coordinates_do_not_destroy_known_identity(self):
        v,r,a=context();v[0]['latitude']=None
        self.assertEqual(refresh.resolve_venue(row(),item(dict(id=907,name='San Siro',city='Milano')),v,r,a),(23100,'UNRESOLVED_DIRECTIONS'))
    def test_invalid_coordinates_are_not_automatically_linked(self):
        v,r,a=context();v[0]['latitude']=200
        self.assertEqual(refresh.resolve_venue(row(),item(dict(id=907,name='San Siro',city='Milano')),v,r,a),(None,'DISPUTED'))
    def test_date_update_survives_venue_conflict(self):
        p=item(dict(id=909,name='San Siro',city='Milano'));p['fixture']['date']='2026-12-01T20:00:00+00:00'
        m,v=refresh.classify_candidate(row(23100),[p],context());self.assertEqual(m['classification'],'WOULD_UPDATE_RESCHEDULED');self.assertEqual(v['venue_id'],23100)
    def test_recent_completed_null_venue_can_be_filled_without_rewriting_lifecycle(self):
        r=row();r.status='FT';r.home_goals=2;r.away_goals=1
        p=item(dict(id=907,name='San Siro',city='Milano'),'FT');p['goals']=dict(home=2,away=1)
        m,v=refresh.classify_candidate(r,[p],context());self.assertEqual(m['proposed_changed_fields'],['venue_id']);self.assertEqual(v['venue_id'],23100)
        p['goals']['home']=3;self.assertIsNone(refresh.classify_candidate(r,[p],context())[1])
    def test_reviewed_regular_league_home_and_exception_exclusions(self):
        p=item();p['league'].update(id=135,round='Regular Season - 9')
        proof=dict(home_team_id=505,league_id=135,season=2026,venue_id=23100,competition_type='league',no_venue_exceptions=True,
            valid_from='2026-08-01',valid_until='2027-05-31',review_status='VERIFIED_CURRENT_HOME',source='https://www.inter.it/verified-home')
        self.assertEqual(reviewed_home_proof(p,[proof]),proof)
        rc=dict(home_ground_reviews=[proof]);self.assertEqual(refresh.resolve_venue(row(),p,*context(),rc),(23100,'MATCHED_HOME_REVIEW'))
        # Existing verified event venue is never replaced by a home fallback.
        self.assertEqual(refresh.resolve_venue(row(99),p,*context(),rc),(99,'MISSING'))
        for key,value in [('round','Play-offs'),('round','Final'),('round','Round of 16')]:
            bad=copy.deepcopy(p);bad['league'][key]=value;self.assertIsNone(reviewed_home_proof(bad,[proof]))
        for change in [dict(no_venue_exceptions=False),dict(valid_until='2026-11-01'),dict(source=''),dict(competition_type='cup')]:
            self.assertIsNone(reviewed_home_proof(p,[dict(proof,**change)]))
    def test_home_fallback_rejects_venue_policy_conflict_and_locality(self):
        p=item();p['league'].update(id=135,round='Regular Season - 9')
        proof=dict(home_team_id=505,league_id=135,season=2026,venue_id=23100,competition_type='league',no_venue_exceptions=True,
            valid_from='2026-08-01',valid_until='2027-05-31',review_status='VERIFIED_CURRENT_HOME',source='https://www.inter.it/verified-home')
        rc=dict(home_ground_reviews=[proof],fixture_verifications={1639884:dict(state='DISPUTED',identity=dict(fixture_id=1639884,league_id=137,season=2026,home_team_id=505,away_team_id=495))})
        self.assertEqual(refresh.resolve_venue(row(),p,*context(),rc),(None,'MISSING'))
        rc.pop('fixture_verifications');p['fixture']['venue']=dict(id=None,name=None,city='Rome')
        self.assertEqual(refresh.resolve_venue(row(),p,*context(),rc),(None,'DISPUTED'))
        p['fixture']['venue']=dict(id=909,name='Alternative Ground',city='Milano')
        self.assertEqual(refresh.resolve_venue(row(),p,*context(),rc),(99,'MATCHED'))
        p['fixture']['venue']=None
        for change in [dict(no_venue_exceptions=False),dict(valid_until='2026-11-01'),dict(source=''),dict(competition_type='cup')]:
            self.assertEqual(refresh.resolve_venue(row(),p,*context(),dict(home_ground_reviews=[dict(proof,**change)])),(None,'MISSING'))

    def test_official_event_proof_is_an_exact_preimage_not_generic_home_fallback(self):
        p=item();key=(1639884,137,2026,505,495,KICKOFF.isoformat());rc=dict(event_proofs={key:dict(venue_id=23100,source='https://www.inter.it/official-event')})
        self.assertEqual(refresh.resolve_venue(row(),p,*context(),rc),(23100,'MATCHED'))
        p['fixture']['date']='2026-12-01T20:00:00+00:00'
        self.assertEqual(refresh.resolve_venue(row(),p,*context(),rc),(None,'MISSING'))
    def test_conflicting_home_reviews_hold_venue_without_blocking_date(self):
        p=item();p['league'].update(id=135,round='Regular Season - 9');p['fixture']['date']='2026-12-01T20:00:00+00:00'
        r=row();r.league_id=135
        proof=dict(home_team_id=505,league_id=135,season=2026,venue_id=23100,competition_type='league',no_venue_exceptions=True,
            valid_from='2026-08-01',valid_until='2027-05-31',review_status='VERIFIED_CURRENT_HOME',source='https://www.inter.it/verified-home')
        m,v=refresh.classify_candidate(r,[p],(*context(),dict(home_ground_reviews=[proof,dict(proof,venue_id=99)])))
        self.assertEqual(m['venue_mapping'],'AMBIGUOUS');self.assertEqual(m['classification'],'WOULD_UPDATE_RESCHEDULED');self.assertIsNone(v['venue_id'])

class NightlyVenueIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.engine=database();self.addCleanup(self.engine.dispose);self.populate()
    def populate(self):
        with self.engine.begin() as c:
            c.execute(text('DELETE FROM fixtures'))
            c.execute(text("INSERT INTO teams VALUES (505,'Inter'),(495,'Genoa')"))
            c.execute(text("INSERT INTO venues VALUES (23100,'Stadio Giuseppe Meazza','Milano','Italy',45.478097,9.123927,907,NULL),(99,'Alternative Ground','Milano','Italy',45.5,9.2,909,NULL)"))
            c.execute(text("INSERT INTO venue_names VALUES (23100,'San Siro',NULL)"))
            fixtures=Table('fixtures',MetaData(),autoload_with=c)
            c.execute(fixtures.insert().values(fixture_id=1639884,fixture_date=KICKOFF,venue_id=None,league_id=137,season=2026,country='Italy',status='NS',home_team_id=505,home_team='Inter',away_team_id=495,away_team='Genoa'))
            c.execute(text('CREATE TABLE supporter_fixture_links (supporter_id INTEGER, fixture_id INTEGER REFERENCES fixtures(fixture_id))'))
            c.execute(text('INSERT INTO supporter_fixture_links VALUES (7,1639884)'))
    def run_nightly(self,p,inject=None,mapping_change=False):
        client=Client()
        def by_ids(ids):
            client.requests_made+=1
            if mapping_change:
                with self.engine.begin() as c:c.execute(text("UPDATE venues SET city='Changed by another writer' WHERE venue_id=23100"))
            return [p]
        client.fixtures_by_ids=by_ids
        env=dict(DATABASE_URL='synthetic',API_FOOTBALL_KEY='synthetic',ENABLE_EXPANDED_FIXTURE_REFRESH='true',ENABLE_NEW_FIXTURE_DISCOVERY='false',ENABLE_GLOBAL_FIXTURE_DISCOVERY='false')
        with tempfile.TemporaryDirectory() as folder:
            receipt=Path(folder)/'receipt.json'
            with patch.object(refresh,'create_engine',return_value=self.engine),patch.object(refresh,'ApiFootballClient',return_value=client),patch.dict(os.environ,env),patch('sys.argv',['refresh','--nightly','--as-of','2026-12-03','--write','--confirm-write','--report',str(receipt)]),patch.object(refresh,'reconcile_final_state',side_effect=inject,wraps=refresh.reconcile_final_state),redirect_stdout(io.StringIO()):
                code=refresh.main()
            return code,json.loads(receipt.read_text())
    def state(self):
        with self.engine.connect() as c:return dict(c.execute(text('SELECT * FROM fixtures WHERE fixture_id=1639884')).mappings().one())
    def test_null_alias_reassignment_and_omission_preserve_supporters(self):
        for venue,expected in [(dict(id=None,name='San Siro',city='Milano'),23100),(dict(id=909,name='Alternative Ground',city='Milano'),99),(None,99)]:
            code,result=self.run_nightly(item(venue));self.assertEqual(code,0,result);self.assertTrue(result['commit_confirmed']);self.assertEqual(self.state()['venue_id'],expected)
            with self.engine.connect() as c:
                self.assertEqual(c.execute(text('SELECT * FROM supporter_fixture_links')).all(),[(7,1639884)])
                self.assertEqual(c.execute(text('SELECT count(*) FROM fixtures')).scalar_one(),1)
                self.assertEqual(c.execute(text("SELECT content FROM editorial")).scalar_one(),'must remain unchanged')
        code,result=self.run_nightly(item());self.assertEqual(result['proposed_fixture_rows_changed'],0)
    def test_failure_after_update_rolls_back(self):
        before=self.state();code,result=self.run_nightly(item(dict(id=907,name='San Siro',city='Milano')),RuntimeError('Synthetic precommit failure'))
        self.assertEqual(code,1);self.assertFalse(result['commit_confirmed']);self.assertEqual(self.state(),before)
    def test_completed_null_is_selected_by_real_candidate_query(self):
        with self.engine.begin() as c:c.execute(text("UPDATE fixtures SET status='FT',home_goals=2,away_goals=1"))
        p=item(dict(id=907,name='San Siro',city='Milano'),'FT');p['goals']=dict(home=2,away=1)
        code,result=self.run_nightly(p);self.assertEqual(code,0,result);self.assertEqual(result['candidates'],1);self.assertEqual(self.state()['venue_id'],23100)
    def test_mapping_preimage_drift_refuses_fixture_update(self):
        before=self.state();code,result=self.run_nightly(item(dict(id=907,name='San Siro',city='Milano')),mapping_change=True)
        self.assertEqual(code,1);self.assertFalse(result['commit_confirmed']);self.assertEqual(self.state(),before)
    def test_scoped_home_fallback_through_nightly_writer(self):
        from ingestion.global_discovery import load_registry
        reg=load_registry()
        proof=dict(home_team_id=505,league_id=135,season=2026,venue_id=23100,competition_type='league',no_venue_exceptions=True,
            valid_from='2026-08-01',valid_until='2027-05-31',review_status='VERIFIED_CURRENT_HOME',source='https://www.inter.it/verified-home')
        reg['home_ground_reviews']=[proof]
        with self.engine.begin() as c:c.execute(text('UPDATE fixtures SET league_id=135'))
        p=item();p['league'].update(id=135,round='Regular Season - 9')
        with patch('ingestion.global_discovery.load_registry',return_value=reg):
            code,result=self.run_nightly(p)
            self.assertEqual(code,0,result);self.assertEqual(self.state()['venue_id'],23100)
            self.assertEqual(result['venue_reconciliation']['mapping_counts'].get('MATCHED_HOME_REVIEW'),1)
            code,second=self.run_nightly(p)
            self.assertEqual(code,0,second);self.assertEqual(second['proposed_fixture_rows_changed'],0)
        with self.engine.connect() as c:self.assertEqual(c.execute(text('SELECT * FROM supporter_fixture_links')).all(),[(7,1639884)])

    def test_discovery_uses_same_scoped_home_proof_and_excludes_cup_round(self):
        from ingestion.global_discovery import DiscoveryScope
        from ingestion.pipeline import plan_fixture_discovery
        proof=dict(home_team_id=505,league_id=135,season=2026,venue_id=23100,competition_type='league',no_venue_exceptions=True,
            valid_from='2026-08-01',valid_until='2027-05-31',review_status='VERIFIED_CURRENT_HOME',source='https://www.inter.it/verified-home')
        scope=DiscoveryScope('Italy',135,'Serie A',2026,'2026/27',home_ground_reviews=(proof,))
        p=item();p['fixture'].update(id=1639885,date='2026-12-04T17:00:00+00:00');p['league'].update(id=135,round='Regular Season - 9')
        with self.engine.connect() as c:
            plan=plan_fixture_discovery(c,{(135,2026):[p]},datetime(2026,12,1,tzinfo=timezone.utc),datetime(2026,12,5,tzinfo=timezone.utc),approved_scopes=(scope,))
            self.assertEqual(plan['rows'][0]['venue_id'],23100)
            p['league']['round']='Play-offs'
            plan=plan_fixture_discovery(c,{(135,2026):[p]},datetime(2026,12,1,tzinfo=timezone.utc),datetime(2026,12,5,tzinfo=timezone.utc),approved_scopes=(scope,))
            self.assertIsNone(plan['rows'][0]['venue_id'])
            p['league']['round']='Regular Season - 9'
            from dataclasses import replace
            for reviews in [(dict(proof,no_venue_exceptions=False),),(dict(proof,valid_until='2026-11-01'),),(proof,dict(proof,venue_id=99))]:
                blocked=replace(scope,home_ground_reviews=reviews)
                plan=plan_fixture_discovery(c,{(135,2026):[p]},datetime(2026,12,1,tzinfo=timezone.utc),datetime(2026,12,5,tzinfo=timezone.utc),approved_scopes=(blocked,))
                self.assertEqual(len(plan['rows']),1,plan);self.assertIsNone(plan['rows'][0]['venue_id'])
        from ingestion.pipeline import run_fixture_discovery
        p['league']['round']='Regular Season - 9'
        client=Client();client.fixtures_between=lambda *args: [p]
        result=run_fixture_discovery(self.engine,client,datetime(2026,12,3).date(),write=True,approved_scopes=(scope,))
        self.assertTrue(result['passed'],result);self.assertEqual(result['inserted'],1)
        with self.engine.connect() as c:self.assertEqual(c.execute(text('SELECT venue_id FROM fixtures WHERE fixture_id=1639885')).scalar_one(),23100)
        second=run_fixture_discovery(self.engine,client,datetime(2026,12,3).date(),write=True,approved_scopes=(scope,))
        self.assertTrue(second['passed'],second);self.assertEqual(second['inserted'],0)

@unittest.skipUnless(os.getenv('MATCHGOER_LOCAL_POSTGRES_TEST')=='TRUE','Explicit fixed loopback PostgreSQL opt-in required')
class NightlyVenuePostgresTests(NightlyVenueIntegrationTests):
    def setUp(self):
        self.admin=create_engine('postgresql+psycopg2://fixture_test@127.0.0.1:55439/postgres',connect_args={'options':'-c statement_timeout=15000'})
        with self.admin.begin() as c:c.exec_driver_sql('CREATE SCHEMA automated_venue_test')
        self.engine=create_engine('postgresql+psycopg2://fixture_test@127.0.0.1:55439/postgres',connect_args={'options':'-c search_path=automated_venue_test -c statement_timeout=15000'})
        local=database()
        try:
            old=MetaData();old.reflect(local);new=MetaData()
            for t in old.sorted_tables:
                clone=t.to_metadata(new)
                for col in clone.c:
                    if isinstance(col.type,DateTime):col.type=DateTime(timezone=True)
            new.create_all(self.engine)
            with local.connect() as src,self.engine.begin() as dst:
                for n,t in old.tables.items():
                    rows=[dict(r) for r in src.execute(t.select()).mappings()]
                    if rows:dst.execute(new.tables[n].insert(),rows)
        finally:local.dispose()
        self.populate()
    def tearDown(self):
        self.engine.dispose()
        with self.admin.begin() as c:c.exec_driver_sql('DROP SCHEMA automated_venue_test CASCADE')
        self.admin.dispose()
