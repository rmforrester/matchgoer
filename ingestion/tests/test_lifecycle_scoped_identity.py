"""Scoped lifecycle canonical reuse without a duplicate club or global remap."""
import copy,unittest
from datetime import datetime,timezone,timedelta
from types import SimpleNamespace
from sqlalchemy import text
from test_fixture_discovery import database
import refresh_fixture_states as refresh

class ScopedLifecycleIdentityTests(unittest.TestCase):
 def setUp(self):
  self.engine=database();self.addCleanup(self.engine.dispose)
  with self.engine.begin() as c:c.execute(text("INSERT INTO teams VALUES(1310,'Sedan'),(3028,'Bourges Foot'),(25358,'Grau-du-Roi'),(9934,'Villefranche SJB')"))
 def case(self,fid=1647987):
  h,a,pid,name=(1310,3028,17360,'Bourges Foot 18') if fid==1647987 else (25358,9934,28647,'Riviera')
  r=SimpleNamespace(fixture_id=fid,league_id=66,season=2026,home_team_id=h,away_team_id=a,home_team='Home',away_team='Canonical',fixture_date=datetime(2026,11,14,15,tzinfo=timezone.utc),status='NS',home_goals=None,away_goals=None,venue_id=None)
  p=dict(fixture=dict(id=fid,date='2026-12-01T19:00:00+00:00',status=dict(short='PST'),venue={}),league=dict(id=66,season=2026),teams=dict(home=dict(id=h,name='Home'),away=dict(id=pid,name=name)),goals=dict(home=None,away=None))
  return r,p
 def mapping(self,fid=1647987,**changes):
  r,p=self.case(fid);values=dict(id=1 if fid==1647987 else 2,provider='api_football',pid=p['teams']['away']['id'],league=66,season=2026,cid=r.away_team_id,name=p['teams']['away']['name'],review='APPROVED');values.update(changes)
  with self.engine.begin() as c:c.execute(text('INSERT INTO team_identity_overrides VALUES(:id,:provider,:pid,:league,:season,:cid,:name,:review)'),values)
 def classify(self,r,p):
  with self.engine.connect() as c:ctx=refresh.lifecycle_team_context(c,[r],{r.fixture_id:[p]})
  return refresh.classify_candidate(r,[p],expanded=False,identity_context=ctx.get(r.fixture_id)),ctx
 def test_both_exact_canonical_reuses_allow_lifecycle_and_preserve_raw_receipt(self):
  for fid in [1647987,1647955]:
   self.mapping(fid);r,p=self.case(fid);(m,v),ctx=self.classify(r,p)
   self.assertEqual(m['classification'],'WOULD_UPDATE_RESCHEDULED');self.assertEqual(v['status'],'PST');self.assertNotIn('home_team_id',v);self.assertNotIn('away_team_id',v)
   self.assertEqual(m['raw_provider_identity']['away_team_id'],p['teams']['away']['id']);self.assertEqual(m['resolved_provider_identity']['away_team_id'],r.away_team_id)
   r.fixture_date=v['fixture_date'];r.status='PST';self.assertIsNone(self.classify(r,p)[0][1])
  with self.engine.connect() as c:self.assertEqual(c.execute(text('SELECT count(*) FROM teams WHERE team_id IN(17360,28647)')).scalar(),0)
 def test_missing_pending_wrong_scope_name_and_missing_target_hold(self):
  for changes in [None,dict(review='PENDING'),dict(league=69),dict(season=2025),dict(name='Different successor'),dict(cid=999999)]:
   with self.subTest(changes=changes):
    with self.engine.begin() as c:c.execute(text('DELETE FROM team_identity_overrides'))
    if changes is not None:self.mapping(**changes)
    r,p=self.case();(m,v),_=self.classify(r,p);self.assertEqual(m['classification'],'IDENTITY_MISMATCH');self.assertIsNone(v)
 def test_fixture_league_and_stored_canonical_conflicts_still_hold(self):
  self.mapping();r,p=self.case();r.away_team_id=9934;self.assertIsNone(self.classify(r,p)[0][1]);r,p=self.case();r.league_id=69;self.assertIsNone(self.classify(r,p)[0][1])
 def test_no_implicit_alias_or_raw_id_override_bypass(self):
  self.mapping();r,p=self.case();r.away_team_id=17360
  self.assertEqual(self.classify(r,p)[0][0]['classification'],'IDENTITY_MISMATCH')
  p['teams']['away']['name']='Unverified merger';self.assertIsNone(self.classify(r,p)[0][1])
 def test_scope_isolation_and_mapping_preimage_drift(self):
  r,p=self.case();self.mapping();_,before=self.classify(r,p)
  with self.engine.begin() as c:c.execute(text("UPDATE team_identity_overrides SET review_status='REVOKED'"))
  _,after=self.classify(r,p);self.assertNotEqual(before,after)
  r,p=self.case();r.season=2025;p['league']['season']=2025;self.assertIsNone(self.classify(r,p)[0][1])
 def test_ordinary_same_id_alias_remains_existing_behaviour(self):
  r,p=self.case();p['teams']['away']['id']=r.away_team_id;p['teams']['away']['name']='Other abbreviation';(m,v),ctx=self.classify(r,p);self.assertEqual(ctx,{});self.assertIsNotNone(v)
