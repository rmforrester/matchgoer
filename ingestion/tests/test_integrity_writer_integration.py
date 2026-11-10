"""Exercise existing nightly and discovery writers with synthetic transport and saved public fixtures."""
import contextlib,copy,io,json,os,tempfile,unittest
from datetime import date,datetime,timezone
from pathlib import Path
from unittest.mock import Mock,patch
import requests
from sqlalchemy import select,text,Table,MetaData
import refresh_fixture_states as refresh
from ingestion.api_football import ApiFootballClient
from ingestion.pipeline import run_fixture_discovery
from ingestion.global_discovery import DiscoveryScope
from backend.fixture_integrity import RUNS,SCHEDULE,set_verified_venue
from test_automatic_venue_reconciliation import NightlyVenueIntegrationTests,item
from test_fixture_discovery import Client,database


class NightlyReceiptTests(NightlyVenueIntegrationTests):
    def run_real_client(self, failure=False):
        with tempfile.TemporaryDirectory() as d:
            client=ApiFootballClient('synthetic',Path(d),min_request_interval=0)
            def reply(url,params=None,**kwargs):
                if failure and url.endswith('/fixtures'):raise requests.Timeout('synthetic failure')
                r=Mock();r.status_code=200;r.headers={'x-ratelimit-requests-remaining':'1000','x-ratelimit-remaining':'100'}
                response={} if url.endswith('/status') else [item(dict(id=907,name='San Siro',city='Milano'),'FT')]
                r.json.return_value=dict(response=response,errors=[],results=len(response),paging=dict(current=1,total=1))
                return r
            env=dict(DATABASE_URL='synthetic-engine-injected',API_FOOTBALL_KEY='synthetic',ENABLE_EXPANDED_FIXTURE_REFRESH='TRUE',ENABLE_NEW_FIXTURE_DISCOVERY='FALSE',ENABLE_GLOBAL_FIXTURE_DISCOVERY='FALSE')
            argv=['refresh','--nightly','--as-of','2026-12-02','--write','--confirm-write','--report',str(Path(d)/'report.json')]
            with patch.object(refresh,'create_engine',return_value=self.engine),patch.object(refresh,'ApiFootballClient',return_value=client),patch.object(client.session,'get',side_effect=reply),patch.dict(os.environ,env),patch('sys.argv',argv),contextlib.redirect_stdout(io.StringIO()):
                code=refresh.main()
            report=json.loads((Path(d)/'report.json').read_text(encoding='utf-8'))
        return code,report

    def test_atomic_nightly_receipt_and_idempotent_second_execution(self):
        code,r=self.run_real_client();self.assertEqual(code,0,r)
        with self.engine.connect() as c:
            run=c.execute(select(RUNS)).mappings().one()
            self.assertEqual(run['requests_attempted'],1);self.assertEqual(run['requests_completed'],1)
            self.assertEqual(len(run['receipt']['integrity']['groups']),1)
            self.assertEqual(c.execute(select(SCHEDULE.c.fixture_id)).scalars().all(),[1639884])
            self.assertEqual(run['receipt']['accounting']['updated'],1)
        code,r=self.run_real_client();self.assertEqual(code,0,r)
        with self.engine.connect() as c:
            rows=c.execute(select(RUNS).order_by(RUNS.c.started_at)).mappings().all()
            self.assertEqual(rows[-1]['receipt']['accounting']['updated'],0)
            self.assertEqual(c.execute(select(SCHEDULE.c.history)).scalar_one().__len__(),1)

    def test_provider_failure_has_durable_failed_receipt(self):
        code,r=self.run_real_client(failure=True);self.assertEqual(code,1)
        with self.engine.connect() as c:
            run=c.execute(select(RUNS)).mappings().one()
            self.assertEqual(run['state'],'FAILED');self.assertEqual(run['requests_attempted'],1);self.assertEqual(run['requests_completed'],0)
            self.assertFalse(run['receipt']['report']['commit_confirmed'])
            self.assertEqual(c.exec_driver_sql('SELECT status FROM fixtures').scalar_one(),'NS')

    def test_verified_venue_survives_actual_nightly_writer(self):
        with self.engine.begin() as c:set_verified_venue(c,1639884,99,source_url='https://official.example/event',evidence_sha256='a'*64,actor='reviewer',provider_venue={'name':'San Siro'})
        code,r=self.run_real_client();self.assertEqual(code,0,r)
        with self.engine.connect() as c:self.assertEqual(c.exec_driver_sql('SELECT venue_id FROM fixtures').scalar_one(),99)


class NewDrawTests(unittest.TestCase):
    def setUp(self):
        self.engine=database();self.addCleanup(self.engine.dispose)

    def test_twenty_saved_FA_Cup_ties_insert_once_with_atomic_sidecars(self):
        evidence=json.loads((Path(__file__).parent/'fixtures/fa_cup_second_round_20261110.json').read_text(encoding='utf-8'))
        payloads=evidence['payloads'];self.assertEqual(len(payloads),20)
        canonical=evidence['canonical']
        with self.engine.begin() as c:
            teams=Table('teams',MetaData(),autoload_with=c);grounds=Table('venues',MetaData(),autoload_with=c);names=Table('venue_names',MetaData(),autoload_with=c)
            tids={x for x in c.execute(select(teams.c.team_id)).scalars()}
            rows={t['id']:dict(team_id=t['id'],team_name=t['name']) for p in payloads for t in p['teams'].values() if t['id'] not in tids}
            c.execute(teams.insert(),list(rows.values()))
            known=set(c.execute(select(grounds.c.venue_id)).scalars());new=[{k:v for k,v in r.items() if k in grounds.c} for r in canonical['venues'] if r['venue_id'] not in known]
            if new:c.execute(grounds.insert(),new)
            aliases=[{k:v for k,v in r.items() if k in names.c} for r in canonical['aliases']]
            if aliases:c.execute(names.insert(),aliases)
        reg=json.loads((Path(__file__).resolve().parents[2]/'config/global_fixture_discovery.json').read_text(encoding='utf-8'))
        with self.engine.connect() as c:known=set(c.execute(select(grounds.c.venue_id)).scalars())
        scope=DiscoveryScope('England',45,'FA Cup',2026,'2026/27',venue_countries=('England','Wales'),venue_reviews=tuple(r for r in reg.get('venue_reviews',[]) if r['venue_id'] in known))
        client=Client(items=payloads)
        def inventory(league,season,start,end):client.requests_made+=1;return copy.deepcopy(payloads)
        client.fixtures_between=inventory
        r=run_fixture_discovery(self.engine,client,date(2026,11,10),write=True,approved_scopes=(scope,))
        self.assertTrue(r['passed'],r);self.assertEqual(r['inserted'],20)
        with self.engine.connect() as c:
            self.assertEqual(len(c.execute(select(SCHEDULE.c.fixture_id)).all()),20)
            self.assertEqual(c.exec_driver_sql('SELECT count(*) FROM fixtures WHERE league_id=45').scalar_one(),20)
            self.assertEqual(c.exec_driver_sql('SELECT count(*) FROM fixtures WHERE league_id=45 AND venue_id IS NOT NULL').scalar_one(),12)
        r=run_fixture_discovery(self.engine,client,date(2026,11,10),write=True,approved_scopes=(scope,));self.assertTrue(r['passed'],r);self.assertEqual(r['inserted'],0)

    def test_replacement_provider_ID_is_held_before_insertion(self):
        from test_fixture_discovery import payload,START,END
        from ingestion.pipeline import plan_fixture_discovery
        a=payload(123);a['fixture']['status']['short']='PST';a['goals']={'home':None,'away':None}
        r=run_fixture_discovery(self.engine,Client(items=[a]),date(2026,11,3),write=True)
        self.assertTrue(r['passed'],r)
        b=copy.deepcopy(a);b['fixture']['id']=456;b['fixture']['date']='2026-11-20T01:00:00+00:00';b['fixture']['status']['short']='NS'
        with self.engine.connect() as c:r=plan_fixture_discovery(c,{(489,2026):[b]},START,END)
        self.assertEqual(r['rows'],[]);self.assertEqual(r['held'][0]['reason'],'POSSIBLE_REPLACEMENT_IDENTITY_REVIEW')


if __name__=='__main__':unittest.main()
