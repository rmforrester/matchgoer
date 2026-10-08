import contextlib,io,json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from sqlalchemy import create_engine,text,event
import refresh_fixture_states as r
from test_fixture_reconciliation import provider
@unittest.skipUnless(os.getenv('MATCHGOER_LOCAL_POSTGRES_TEST') == 'TRUE', 'Explicit isolated loopback PostgreSQL test opt-in required')
class PrecommitPostgresTests(unittest.TestCase):
 def setUp(self):
  self.e=create_engine('postgresql+psycopg2://fixture_test@127.0.0.1:55439/postgres')
  with self.e.begin() as c:
   c.exec_driver_sql('DROP SCHEMA IF EXISTS fixture_precommit_test CASCADE');c.exec_driver_sql('CREATE SCHEMA fixture_precommit_test')
  @event.listens_for(self.e,'connect')
  def search(db,record):
   with db.cursor() as q:q.execute('SET search_path TO fixture_precommit_test')
   db.commit()
  self.e.dispose()
  with self.e.begin() as c:
   c.exec_driver_sql('CREATE TABLE fixtures (fixture_id INTEGER PRIMARY KEY, fixture_date TIMESTAMPTZ, status TEXT, home_goals INTEGER, away_goals INTEGER, league_id INTEGER, season INTEGER, home_team_id INTEGER, away_team_id INTEGER, home_team TEXT, away_team TEXT, venue_id INTEGER, country TEXT, editorial TEXT)')
   c.exec_driver_sql('CREATE TABLE venues (venue_id INTEGER, provider_venue_id INTEGER, name TEXT, city TEXT, country TEXT, latitude FLOAT, longitude FLOAT)')
   c.exec_driver_sql('CREATE TABLE venue_provider_refs (venue_id INTEGER, provider TEXT, provider_venue_id INTEGER, valid_to TEXT)');c.exec_driver_sql('CREATE TABLE venue_names (venue_id INTEGER, name TEXT, valid_to TEXT)')
   for i in [100,101,102,*r.REVIEW_HOLDS]:c.execute(text("INSERT INTO fixtures VALUES (:id,'2026-09-01 19:45:00+00','NS',NULL,NULL,39,2026,:home,2,'Home','Away',3,'England','preserve')"),dict(id=i,home=i))
  self.fake=Mock();self.fake.failures=[];self.fake.requests_made=1;self.fake.fixtures_by_ids.return_value=[provider(home_team_id=100),provider(fixture_id=101,home_team_id=999),*[provider(fixture_id=i,home_team_id=i) for i in r.REVIEW_HOLDS]]
  self.before=self.state();self.commits=0;self.database_errors=[]
  @event.listens_for(self.e,'handle_error')
  def failed(context):self.database_errors.append(getattr(context.original_exception,'pgcode',None))
  @event.listens_for(self.e,'commit')
  def committed(c):self.commits+=1
 def tearDown(self):self.e.dispose()
 def state(self):
  with self.e.connect() as c:return c.exec_driver_sql('SELECT * FROM fixtures ORDER BY fixture_id').all()
 def run_writer(self,sql=None):
  original=r.reconcile_final_state
  def reconcile(c,t,b,u):
   if sql:c.exec_driver_sql(sql)
   original(c,t,b,u)
  with tempfile.TemporaryDirectory() as d,patch.object(r,'create_engine',return_value=self.e),patch.object(r,'ApiFootballClient',return_value=self.fake),patch.dict(os.environ,{'DATABASE_URL':'local-only','API_FOOTBALL_KEY':'mock','ENABLE_EXPANDED_FIXTURE_REFRESH':'TRUE'}),patch.object(r,'reconcile_final_state',side_effect=reconcile),patch('sys.argv',['refresh','--nightly','--as-of','2026-09-02','--write','--confirm-write','--report',str(Path(d)/'receipt.json')]),contextlib.redirect_stdout(io.StringIO()):
   r.main();return json.loads((Path(d)/'receipt.json').read_text())
 def rollback_case(self,sql):
  self.assertIsNotNone(self.run_writer(sql)['write_error']);self.assertEqual(self.commits,0);self.assertEqual(self.state(),self.before)
 def test_A_success_one_commit(self):
  self.assertIsNone(self.run_writer()['write_error']);self.assertEqual(self.commits,1);after=self.state();self.assertEqual([b[0] for b,a in zip(self.before,after) if b!=a],[100]);self.assertEqual(next(x for x in after if x[0]==100)[2:5],('FT',2,1))
 def test_B_intended_differs(self):self.rollback_case("UPDATE fixtures SET status='NS' WHERE fixture_id=100")
 def test_C_french_hold(self):self.rollback_case('UPDATE fixtures SET home_goals=8 WHERE fixture_id=1599987')
 def test_D_identity_hold(self):self.rollback_case('UPDATE fixtures SET home_team_id=8 WHERE fixture_id=101')
 def test_E_venue(self):self.rollback_case('UPDATE fixtures SET venue_id=99 WHERE fixture_id=100')
 def test_F_rowcount(self):
  with self.e.begin() as c:
   c.exec_driver_sql('CREATE FUNCTION refuse() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RETURN NULL; END $$');c.exec_driver_sql('CREATE TRIGGER refuse BEFORE UPDATE ON fixtures FOR EACH ROW EXECUTE FUNCTION refuse()')
  self.commits=0;self.assertIsNotNone(self.run_writer()['write_error']);self.assertEqual(self.commits,0);self.assertEqual(self.state(),self.before)
 def test_G_database_error(self):self.rollback_case('SELECT 1/0')
 def test_H_idempotence(self):
  self.run_writer();after=self.state();receipt=self.run_writer();self.assertEqual(receipt['proposed_fixture_rows_changed'],0);self.assertEqual(after,self.state())
 def test_editorial(self):self.rollback_case("UPDATE fixtures SET editorial='wrong' WHERE fixture_id=102")
 def test_delete(self):self.rollback_case('DELETE FROM fixtures WHERE fixture_id=102')
 def test_insert(self):self.rollback_case('INSERT INTO fixtures (fixture_id) VALUES (999)')
 def test_table_lock_allows_reads_blocks_other_fixture_writes(self):
  from sqlalchemy.exc import OperationalError
  with self.e.begin() as owner:
   owner.exec_driver_sql('LOCK TABLE fixtures IN SHARE ROW EXCLUSIVE MODE')
   with self.e.begin() as reader:
    self.assertEqual(reader.exec_driver_sql('SELECT count(*) FROM fixtures').scalar(),17)
    reader.exec_driver_sql('SELECT fixture_id FROM fixtures WHERE fixture_id=102 FOR UPDATE')
   for sql in ('UPDATE fixtures SET status=\'PST\' WHERE fixture_id=102',
               'DELETE FROM fixtures WHERE fixture_id=102',
               'INSERT INTO fixtures (fixture_id) VALUES (999)'):
    with self.assertRaises(OperationalError) as error:
     with self.e.begin() as other:
      other.exec_driver_sql("SET LOCAL lock_timeout='150ms'")
      other.exec_driver_sql(sql)
    self.assertEqual(error.exception.orig.pgcode,'55P03')
 def test_intended_row_lock_does_not_protect_unrelated_rows(self):
  with self.e.begin() as owner:
   owner.exec_driver_sql('SELECT fixture_id FROM fixtures WHERE fixture_id=100 FOR UPDATE')
   with self.e.begin() as other:
    other.exec_driver_sql("SET LOCAL lock_timeout='150ms'")
    other.exec_driver_sql('INSERT INTO fixtures (fixture_id) VALUES (999)')
    other.exec_driver_sql('DELETE FROM fixtures WHERE fixture_id=102')
    other.exec_driver_sql("UPDATE fixtures SET status='PST' WHERE fixture_id=1599987")
   self.assertEqual(owner.exec_driver_sql('SELECT count(*) FROM fixtures WHERE fixture_id=999').scalar(),1)
   self.assertEqual(owner.exec_driver_sql('SELECT count(*) FROM fixtures WHERE fixture_id=102').scalar(),0)
   self.assertEqual(owner.exec_driver_sql('SELECT status FROM fixtures WHERE fixture_id=1599987').scalar(),'PST')
 def assert_timeouts_reset(self):
  with self.e.connect() as c:
   for setting in ('lock_timeout','statement_timeout','idle_in_transaction_session_timeout'):
    self.assertEqual(c.exec_driver_sql('SHOW '+setting).scalar(),'0')
 def test_timeout_success_exact_settings_and_reset(self):
  original=r.reconcile_final_state
  def verify(c,t,b,u):
   for setting,expected in (('lock_timeout','10s'),('statement_timeout','2min'),('idle_in_transaction_session_timeout','2min')):
    self.assertEqual(c.exec_driver_sql('SHOW '+setting).scalar(),expected)
   original(c,t,b,u)
  with patch.object(r,'reconcile_final_state',side_effect=verify):
   self.assertIsNone(self.run_writer()['write_error'])
  self.assertEqual(self.commits,1);self.assert_timeouts_reset()
 def test_timeout_lock_acquisition_rolls_back(self):
  import time
  with self.e.connect() as blocker:
   transaction=blocker.begin()
   try:
    blocker.exec_driver_sql('LOCK TABLE fixtures IN ROW EXCLUSIVE MODE')
    started=time.monotonic();self.assertIsNotNone(self.run_writer()['write_error'])
    self.assertGreaterEqual(time.monotonic()-started,9)
   finally:transaction.rollback()
  self.assertIn('55P03',self.database_errors)
  self.assertEqual(self.commits,0);self.assertEqual(self.state(),self.before);self.assert_timeouts_reset()
 def test_timeout_statement_rolls_back(self):
  import time
  started=time.monotonic();self.rollback_case('SELECT pg_sleep(121)')
  self.assertGreaterEqual(time.monotonic()-started,119);self.assertIn('57014',self.database_errors);self.assert_timeouts_reset()
 def test_timeout_idle_termination_rolls_back(self):
  import time
  original=r.reconcile_final_state
  def idle(c,t,b,u):
   time.sleep(121)
   original(c,t,b,u)
  with patch.object(r,'reconcile_final_state',side_effect=idle):
   self.assertIsNotNone(self.run_writer()['write_error'])
  self.assertEqual(self.commits,0);self.assertEqual(self.state(),self.before);self.assert_timeouts_reset()
 def test_timeout_failed_reconciliation_settings_reset(self):
  self.rollback_case("UPDATE fixtures SET status='NS' WHERE fixture_id=100")
  self.assert_timeouts_reset()
