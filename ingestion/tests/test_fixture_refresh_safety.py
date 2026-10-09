from pathlib import Path
import copy
import tempfile
import unittest
from datetime import date, timedelta
from unittest.mock import Mock
import requests
from test_fixture_reconciliation import candidate, provider, KICKOFF
from refresh_fixture_states import classify_candidate, resolve_venue, refresh_window, validate_plan, ALLOWED_FIELDS
from ingestion.api_football import ApiFootballClient

class RefreshSafetyTests(unittest.TestCase):
    def context(self):
        return ([dict(venue_id=7,provider_venue_id=70,name="Stadium Example",city="Town",country="England",latitude=1,longitude=2)], [dict(venue_id=7,provider="api_football",provider_venue_id=70,valid_to=None)], [])
    def row(self):
        r=candidate();r.venue_id=3;r.country="England";return r
    def item(self,venue=None):
        i=provider(status="NS",home_goals=None,away_goals=None);i["fixture"]["venue"]=venue;return i
    def test_rolling_window(self):
        a,b=refresh_window(date(2026,10,8));self.assertEqual(a.isoformat(),"2026-09-08T00:00:00+00:00");self.assertEqual(b.isoformat(),"2026-11-08T00:00:00+00:00")
    def test_unchanged(self):
        r=self.row();self.assertIsNone(classify_candidate(r,[self.item()],self.context())[1])
    def test_kickoff_and_date_changes(self):
        for delta in (timedelta(hours=1),timedelta(days=2)):
            i=self.item();i["fixture"]["date"]=(KICKOFF+delta).isoformat();self.assertIn("fixture_date",classify_candidate(self.row(),[i],self.context())[0]["proposed_changed_fields"])
    def test_known_venue_change_and_repeat(self):
        r=self.row();i=self.item(dict(id=70,name="Example",city="Town"));m,v=classify_candidate(r,[i],self.context());self.assertEqual(v["venue_id"],7);r.venue_id=7;self.assertIsNone(classify_candidate(r,[i],self.context())[1])
    def test_unknown(self):
        self.assertEqual(resolve_venue(self.row(),self.item(dict(id=99,name="Other")),*self.context()),(3,"UNKNOWN"))
    def test_missing(self):
        self.assertEqual(resolve_venue(self.row(),self.item(),*self.context()),(3,"MISSING"))
    def test_ambiguous(self):
        v,r,a=self.context();r.append(dict(venue_id=8,provider="api_football",provider_venue_id=70));self.assertEqual(resolve_venue(self.row(),self.item(dict(id=70,name="Example")),v,r,a),(3,"AMBIGUOUS"))
    def test_disputed(self):
        self.assertEqual(resolve_venue(self.row(),self.item(dict(id=70,name="Wrong")),*self.context()),(3,"DISPUTED"))
    def test_no_directions(self):
        v,r,a=self.context();v[0]["latitude"]=None;self.assertEqual(resolve_venue(self.row(),self.item(dict(id=70,name="Example")),v,r,a),(3,"UNRESOLVED_DIRECTIONS"))
    def test_lifecycle(self):
        for status in ("PST","CANC","ABD","FT"):
            v=classify_candidate(self.row(),[provider(status=status)],self.context())[1];self.assertEqual(v["status"],status)
    def test_missing_duplicate_identity(self):
        for rows,kind in (([],"PROVIDER_MISSING"),([provider(),provider()],"PROVIDER_DUPLICATE"),([provider(home_team_id=9)],"IDENTITY_MISMATCH")):
            m,v=classify_candidate(self.row(),rows,self.context());self.assertEqual(m["classification"],kind);self.assertIsNone(v)
    def test_malformed(self):
        self.assertEqual(classify_candidate(self.row(),[{}],self.context())[0]["classification"],"PROVIDER_MALFORMED")
    def test_malformed_venue_and_goals(self):
        for item in (self.item(["invalid"]), dict(provider(),goals={"home":"2","away":1})):
            self.assertEqual(classify_candidate(self.row(),[item],self.context())[0]["classification"],"PROVIDER_MALFORMED")
    def test_protected_input_and_scope(self):
        c=self.context();before=copy.deepcopy(c);r=self.row();old=copy.deepcopy(vars(r));m,v=classify_candidate(r,[provider()],c);self.assertEqual(c,before);self.assertEqual(vars(r),old);self.assertEqual(set(v),set(ALLOWED_FIELDS));self.assertNotIn("home_team_id",v);self.assertNotIn("venue_name",v)
    def test_timeout_429_and_malformed_response(self):
        for error in (requests.Timeout("timeout"),requests.HTTPError("429")):
            with tempfile.TemporaryDirectory() as d:
                client=ApiFootballClient("test-only",Path(d));client.session.get=Mock(side_effect=error)
                with self.assertRaises(RuntimeError):client.fixtures_by_ids([1])
                self.assertEqual(client.requests_made,1);self.assertTrue(client.failures)
        with tempfile.TemporaryDirectory() as d:
            client=ApiFootballClient("test-only",Path(d));response=Mock();response.json.return_value={"response":{}};client.session.get=Mock(return_value=response)
            with self.assertRaises(RuntimeError):client.fixtures_by_ids([1])

    def test_main_transaction_and_preservation(self):
        from sqlalchemy import create_engine, text
        from unittest.mock import patch
        import json
        import refresh_fixture_states as refresh
        engine=create_engine("sqlite://")
        with engine.begin() as c:
            c.execute(text("CREATE TABLE fixtures (fixture_id INTEGER PRIMARY KEY, fixture_date DATETIME, status TEXT, home_goals INTEGER, away_goals INTEGER, league_id INTEGER, season INTEGER, home_team_id INTEGER, away_team_id INTEGER, home_team TEXT, away_team TEXT, venue_id INTEGER, country TEXT)"))
            c.execute(text("CREATE TABLE venues (venue_id INTEGER, provider_venue_id INTEGER, name TEXT, city TEXT, country TEXT, latitude FLOAT, longitude FLOAT)"))
            c.execute(text("CREATE TABLE venue_provider_refs (venue_id INTEGER, provider TEXT, provider_venue_id INTEGER, valid_to TEXT)"))
            c.execute(text("CREATE TABLE venue_names (venue_id INTEGER, name TEXT, valid_to TEXT)"))
            c.execute(text("INSERT INTO fixtures VALUES (100, '2026-09-01 19:45:00.000000', 'NS', NULL, NULL,39,2026,1,2,'Home','Away',3,'England')"))
            for table in ('supporter_intents','meeting_preferences','match_board','attendance','ground_visits','fixture_editorial','ticket_sources','teams','home_content'):
                c.execute(text('CREATE TABLE '+table+' (id INTEGER, content TEXT)'))
                c.execute(text('INSERT INTO '+table+" VALUES (1,'preserve-exactly')"))
        fake=Mock();fake.failures=[];fake.requests_made=1;fake.fixtures_by_ids.return_value=[provider()]
        with tempfile.TemporaryDirectory() as d, patch.object(refresh,'create_engine',return_value=engine), patch.object(refresh,'ApiFootballClient',return_value=fake), patch.dict('os.environ',{'DATABASE_URL':'test','API_FOOTBALL_KEY':'test','ENABLE_EXPANDED_FIXTURE_REFRESH':'TRUE'}):
            args=['refresh','--nightly','--as-of','2026-09-02','--write','--confirm-write','--report',str(Path(d)/'receipt.json')]
            # Existing cron arguments need no changes: default-off excludes today/future.
            with engine.begin() as c:
                c.execute(text("INSERT INTO fixtures SELECT 101,'2026-09-03 19:45:00.000000',status,home_goals,away_goals,league_id,season,home_team_id,away_team_id,home_team,away_team,venue_id,country FROM fixtures WHERE fixture_id=100"))
            dry_args=[x for x in args if x not in ('--write','--confirm-write')]
            for flag in ('FALSE',None):
                with patch.dict('os.environ',{}):
                    import os
                    if flag is None:os.environ.pop('ENABLE_EXPANDED_FIXTURE_REFRESH',None)
                    else:os.environ['ENABLE_EXPANDED_FIXTURE_REFRESH']=flag
                    with patch('sys.argv',dry_args):self.assertEqual(refresh.main(),0)
                    receipt=json.loads((Path(d)/'receipt.json').read_text());self.assertEqual(receipt['candidates'],1);self.assertFalse(receipt['expanded_refresh_enabled']);self.assertEqual(receipt['field_change_counts']['venue_id'],0)
            with patch('sys.argv',dry_args):self.assertEqual(refresh.main(),1)
            self.assertEqual(json.loads((Path(d)/'receipt.json').read_text())['candidates'],2)
            with engine.begin() as c:c.execute(text('DELETE FROM fixtures WHERE fixture_id=101'))
            with patch.dict('os.environ',{'ENABLE_EXPANDED_FIXTURE_REFRESH':'FALSE'}):
                with patch('sys.argv',args):self.assertEqual(refresh.main(),0)
                with engine.connect() as c:
                    self.assertEqual(c.execute(text('SELECT venue_id FROM fixtures')).scalar(),3)
                    self.assertEqual(c.execute(text('SELECT status FROM fixtures')).scalar(),'FT')
            with engine.begin() as c:c.execute(text("UPDATE fixtures SET status='NS', home_goals=NULL, away_goals=NULL"))
            # Both dry-run and actual local write share the same held plan.
            with patch.dict(refresh.REVIEW_HOLDS,{100:dict(fixture_id=100,reason='test continuity hold',evidence='isolated test',review_status='PENDING_MANUAL_REVIEW')}):
                with engine.connect() as c:before_held=c.execute(text('SELECT * FROM fixtures')).all()
                for hold_args in (args, [x for x in args if x not in ('--write','--confirm-write')]):
                    with patch('sys.argv',hold_args):self.assertEqual(refresh.main(),0 if '--write' in hold_args else 1)
                    receipt=json.loads((Path(d)/'receipt.json').read_text())
                    self.assertEqual(receipt['classification_counts']['MANUAL_REVIEW_HOLD'],1)
                    self.assertEqual(receipt['proposed_fixture_rows_changed'],0)
                    with engine.connect() as c:self.assertEqual(c.execute(text('SELECT * FROM fixtures')).all(),before_held)
            with patch('sys.argv',args):self.assertEqual(refresh.main(),0)
            with engine.connect() as c:
                self.assertEqual(c.execute(text('SELECT status FROM fixtures')).scalar(),'FT')
                self.assertEqual(c.execute(text('SELECT count(*) FROM fixtures')).scalar(),1)
                for table in ('supporter_intents','meeting_preferences','match_board','attendance','ground_visits','fixture_editorial','ticket_sources','teams','home_content'):
                    self.assertEqual(c.execute(text('SELECT content FROM '+table)).scalar(),'preserve-exactly')
            # Completed row no longer selected on repeated run; no duplicate inserted.
            with patch('sys.argv',args):self.assertEqual(refresh.main(),0)
            with engine.begin() as c:
                c.execute(text("UPDATE fixtures SET status='NS', home_goals=NULL, away_goals=NULL"))
            fake.fixtures_by_ids.return_value=[]
            with patch('sys.argv',args):self.assertEqual(refresh.main(),0)
            receipt=json.loads((Path(d)/'receipt.json').read_text());self.assertFalse(receipt['complete']);self.assertEqual(receipt['classification_counts']['PROVIDER_MISSING'],1)
            fake.failures=['API timeout'];fake.fixtures_by_ids.side_effect=RuntimeError('API timeout')
            with patch('sys.argv',args):self.assertEqual(refresh.main(),1)
            with engine.connect() as c:self.assertEqual(c.execute(text('SELECT status FROM fixtures')).scalar(),'NS')
            fake.failures=[];fake.fixtures_by_ids.side_effect=None;fake.requests_made=0
            with engine.begin() as c:
                for fid in range(101,121):
                    c.execute(text("INSERT INTO fixtures SELECT :id,fixture_date,status,home_goals,away_goals,league_id,season,home_team_id,away_team_id,home_team,away_team,venue_id,country FROM fixtures WHERE fixture_id=100"),{'id':fid})
            fake.fixtures_by_ids.reset_mock()
            with patch('sys.argv',args+['--max-requests','1']):self.assertEqual(refresh.main(),1)
            fake.fixtures_by_ids.assert_not_called()
            self.assertEqual(json.loads((Path(d)/'receipt.json').read_text())['provider_requests'],0)
        engine.dispose()

    def test_proposed_collision(self):
        r1=self.row();r2=self.row();r2.fixture_id=101
        i1=provider();i2=provider(fixture_id=101)
        m1,v1=classify_candidate(r1,[i1],self.context());m2,v2=classify_candidate(r2,[i2],self.context())
        self.assertFalse(validate_plan([r1,r2],[m1,m2],{100:v1,101:v2},{})['passed'])
