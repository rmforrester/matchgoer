"""Build12 personal history: isolated PostgreSQL, synthetic owners, no hosted access."""
import os,unittest
from datetime import datetime,date,timezone,timedelta
from types import SimpleNamespace
from unittest.mock import patch
from sqlalchemy import create_engine,text
from sqlalchemy.orm import sessionmaker
from fastapi import HTTPException
import main
from models import Base,User,Venue,VenueVisit,Fixture,InterestedFixture,AwayDayReview
from schemas import VenueVisitCreate,VenueVisitUpdate
from identity import ResolvedIdentity
from personal_history import COLLECTION_SOURCE

@unittest.skipUnless(os.getenv('MATCHGOER_LOCAL_POSTGRES_TEST')=='TRUE','Explicit localhost PostgreSQL opt-in')
class Build12HistoryTests(unittest.TestCase):
 def setUp(self):
  self.engine=create_engine('postgresql+psycopg2://fixture_test@127.0.0.1:55439/postgres',connect_args={'options':'-c search_path=build12_history_test -c timezone=UTC'})
  with self.engine.begin() as c:c.exec_driver_sql('DROP SCHEMA IF EXISTS build12_history_test CASCADE');c.exec_driver_sql('CREATE SCHEMA build12_history_test')
  Base.metadata.create_all(self.engine)
  with self.engine.begin() as c:
   c.exec_driver_sql('CREATE UNIQUE INDEX b12_fixture ON venue_visits(user_id,fixture_id) WHERE fixture_id IS NOT NULL')
   c.exec_driver_sql('CREATE UNIQUE INDEX b12_dated ON venue_visits(user_id,venue_id,visit_date) WHERE fixture_id IS NULL AND visit_date IS NOT NULL')
   c.exec_driver_sql('CREATE UNIQUE INDEX b12_undated ON venue_visits(user_id,venue_id) WHERE fixture_id IS NULL AND visit_date IS NULL')
  self.sessions=sessionmaker(bind=self.engine);self.owner=ResolvedIdentity(1,'registered',True,'test');self.other=ResolvedIdentity(2,'anonymous',False,'test')
  with self.sessions.begin() as db:
   db.add_all([User(user_id=1,is_anonymous=False,account_status='registered'),User(user_id=2,is_anonymous=True,account_status='anonymous'),Venue(venue_id=1,name='Old Trafford',country='England'),Venue(venue_id=2,name='Another Stadium',country='England')]);db.flush();db.add(Venue(venue_id=3,name='Old Trafford alias',canonical_venue_id=1,equivalence_source='https://synthetic.test/verified'));db.flush()
   for fid,vid,when,status in [(10,1,datetime(2026,11,3,20,tzinfo=timezone.utc),'FT'),(11,1,datetime(2026,11,1,15,tzinfo=timezone.utc),'FT'),(20,2,datetime(2026,10,30,20,tzinfo=timezone.utc),'FT'),(30,2,datetime.now(timezone.utc)+timedelta(days=7),'NS'),(31,None,datetime(2026,10,30,20,tzinfo=timezone.utc),'FT')]:
    db.add(Fixture(fixture_id=fid,venue_id=vid,fixture_date=when,status=status,home_team='Manchester United' if fid==10 else 'Home',away_team='AS Roma' if fid==10 else 'Away',league_name='Synthetic',country='England'))
  self.mock=patch.object(main,'SessionLocal',self.sessions);self.mock.start();self.addCleanup(self.mock.stop);self.addCleanup(self.engine.dispose)
 def attend(self,fid,actor=None):return main.record_fixture_attendance(fid,actor or self.owner)
 def grounds(self,actor=None):return main.get_my_grounds(actor or self.owner)
 def remove(self,visit,actor=None):return main.delete_personal_matchday(visit.venue_id,visit.visit_id,identity=actor or self.owner)
 def snapshot(self):
  with self.engine.connect() as c:return {n:c.exec_driver_sql('SELECT row_to_json(t)::text FROM '+n+' t ORDER BY 1').scalars().all() for n in ['users','venues','fixtures','away_day_reviews']}
 def test_interest_does_not_add_ground_attendance_is_idempotent(self):
  main.mark_fixture_interested(10,self.owner);self.assertEqual(self.grounds(),[])
  a=self.attend(10);b=self.attend(10);self.assertEqual(a.visit_id,b.visit_id);self.assertEqual(self.grounds()[0]['visit_count'],1)
 def test_remove_one_then_final_derived_matchday_preserves_other_owner_and_interests(self):
  a=self.attend(10);b=self.attend(11);self.attend(10,self.other);main.mark_fixture_interested(10,self.owner);main.mark_fixture_interested(20,self.owner);before=self.snapshot()
  self.remove(a);g=self.grounds();self.assertEqual(g[0]['visit_count'],1);self.assertEqual(g[0]['visits'][0]['visit_id'],b.visit_id)
  self.remove(b);self.assertEqual(self.grounds(),[]);self.assertEqual(len(self.grounds(self.other)),1);self.assertFalse(self.remove(b)['removed'])
  with self.sessions() as db:self.assertEqual([v.fixture_id for v in db.query(InterestedFixture).filter_by(user_id=1)], [20])
  self.assertEqual(self.snapshot(),before)
 def test_independently_saved_ground_survives_final_matchday_removal(self):
  main.record_manual_venue_visit(1,VenueVisitCreate(),self.owner);a=self.attend(10);self.remove(a);self.assertTrue(self.grounds()[0]['independently_saved'])
 def test_promoted_manual_visit_keeps_ground_without_phantom_matchday(self):
  m=main.record_manual_venue_visit(1,VenueVisitCreate(visit_date=date(2026,11,3)),self.owner);a=self.attend(10);self.assertEqual(m.visit_id,a.visit_id);self.assertEqual(a.source,'manual')
  self.remove(a);g=self.grounds()[0];self.assertEqual(g['visits'],[]);self.assertEqual(g['attended_fixtures'],[]);self.assertEqual(g['visit_count'],0);self.assertTrue(g['independently_saved'])
  with self.sessions() as db:self.assertEqual(db.query(VenueVisit).filter_by(user_id=1).one().source,COLLECTION_SOURCE)
  again=main.record_manual_venue_visit(1,VenueVisitCreate(),self.owner);self.assertEqual(again.source,'manual');self.assertEqual(self.grounds()[0]['visit_count'],1)
 def test_remove_ground_counts_every_owned_matchday_including_equivalent_id(self):
  a=self.attend(10);self.attend(11);self.attend(10,self.other);main.record_manual_venue_visit(3,VenueVisitCreate(visit_date=date(2026,10,1)),self.owner)
  main.mark_fixture_interested(10,self.owner);main.mark_fixture_interested(20,self.owner)
  with self.sessions.begin() as db:db.add(AwayDayReview(user_id=1,venue_id=1,overall_score=8))
  before=self.snapshot();preview=main.preview_personal_ground_removal(1,self.owner);self.assertEqual(preview['matchday_count'],3)
  r=main.delete_personal_ground(1,preview['revision'],self.owner);self.assertEqual(r['removed_matchdays'],3);self.assertEqual(self.grounds(),[]);self.assertEqual(self.snapshot(),before);self.assertEqual(len(self.grounds(self.other)),1)
  self.assertFalse(main.delete_personal_ground(1,preview['revision'],self.owner)['removed'])
  with self.sessions() as db:self.assertEqual([v.fixture_id for v in db.query(InterestedFixture).filter_by(user_id=1)], [20])
 def test_changed_collection_requires_fresh_count_and_confirmation(self):
  self.attend(10);p=main.preview_personal_ground_removal(1,self.owner);self.attend(11)
  with self.assertRaises(HTTPException) as cm:main.delete_personal_ground(1,p['revision'],self.owner)
  self.assertEqual(cm.exception.status_code,409);self.assertEqual(self.grounds()[0]['visit_count'],2)
 def test_change_match_preserves_visit_id_moves_ground_and_uses_replacement_date(self):
  a=self.attend(10);main.mark_fixture_interested(10,self.owner);before=self.snapshot();r=main.update_venue_visit_fixture(1,a.visit_id,VenueVisitUpdate(fixture_id=20,allow_ground_change=True),self.owner)
  self.assertEqual((r.visit_id,r.venue_id,r.fixture_id,r.visit_date),(a.visit_id,2,20,date(2026,10,30)));self.assertEqual([g['venue_id'] for g in self.grounds()],[2]);self.assertEqual(self.snapshot(),before)
  repeat=main.update_venue_visit_fixture(2,a.visit_id,VenueVisitUpdate(fixture_id=20,allow_ground_change=True),self.owner);self.assertEqual(repeat.visit_id,a.visit_id)
  with self.sessions() as db:self.assertEqual(db.query(InterestedFixture).filter_by(user_id=1,fixture_id=10).count(),1)
 def test_cross_ground_change_preserves_independent_old_ground(self):
  m=main.record_manual_venue_visit(1,VenueVisitCreate(visit_date=date(2026,11,3)),self.owner);a=self.attend(10);main.update_venue_visit_fixture(1,a.visit_id,VenueVisitUpdate(fixture_id=20,allow_ground_change=True),self.owner)
  g={r['venue_id']:r for r in self.grounds()};self.assertEqual(g[1]['visits'],[]);self.assertTrue(g[1]['independently_saved']);self.assertEqual(g[2]['visits'][0]['visit_id'],m.visit_id)
 def test_duplicate_wrong_owner_missing_ground_future_and_legacy_guard(self):
  a=self.attend(10);self.attend(20)
  for actor,fid,allow,code in [(self.other,11,True,404),(self.owner,20,True,409),(self.owner,30,True,409),(self.owner,31,True,409),(self.owner,20,False,400)]:
   with self.subTest(fid=fid,actor=actor.user_id,allow=allow):
    with self.assertRaises(HTTPException) as cm:main.update_venue_visit_fixture(1,a.visit_id,VenueVisitUpdate(fixture_id=fid,allow_ground_change=allow),actor)
    self.assertEqual(cm.exception.status_code,code)
  self.assertFalse(self.remove(a,self.other)['removed']);self.assertEqual(self.grounds()[0]['visit_count'],1)
 def test_remove_is_atomic_when_membership_retention_fails(self):
  main.record_manual_venue_visit(1,VenueVisitCreate(visit_date=date(2026,11,3)),self.owner);a=self.attend(10);main.mark_fixture_interested(10,self.owner)
  with patch('personal_history.keep_ground',side_effect=RuntimeError('Injected failure')),self.assertRaises(RuntimeError):self.remove(a)
  self.assertEqual(self.grounds()[0]['visits'][0]['visit_id'],a.visit_id)
  with self.sessions() as db:self.assertEqual(db.query(InterestedFixture).filter_by(user_id=1,fixture_id=10).count(),1)
 def test_same_fixture_change_keeps_equivalent_raw_ground_reference(self):
  a=self.attend(10)
  with self.sessions.begin() as db:db.get(VenueVisit,a.visit_id).venue_id=3
  main.update_venue_visit_fixture(1,a.visit_id,VenueVisitUpdate(fixture_id=10,allow_ground_change=True),self.owner)
  with self.sessions() as db:self.assertEqual(db.get(VenueVisit,a.visit_id).venue_id,3)
 def test_collection_marker_cannot_authorise_photo_attendance(self):
  from terraces import reserve_photo,CONSENT_VERSION
  from uuid import uuid4
  m=main.record_manual_venue_visit(1,VenueVisitCreate(visit_date=date(2026,11,3)),self.owner);a=self.attend(10);self.remove(a)
  with self.sessions() as db:
   marker=db.query(VenueVisit).filter_by(user_id=1).one()
   with patch('terraces.require_photo_submitter',return_value=SimpleNamespace(user_id=1)),self.assertRaises(HTTPException) as cm:
    reserve_photo(db,'synthetic',visit_id=marker.visit_id,photo=None,submission_key=str(uuid4()),consent_version=CONSENT_VERSION,public_consent=True,rights_acknowledged=True)
   self.assertEqual(cm.exception.status_code,404)
 def test_stale_matchday_confirmation_cannot_remove_replacement_fixture(self):
  a=self.attend(10);main.update_venue_visit_fixture(1,a.visit_id,VenueVisitUpdate(fixture_id=11,allow_ground_change=True),self.owner)
  with self.assertRaises(HTTPException) as cm:main.delete_personal_matchday(1,a.visit_id,expected_fixture_id=10,check_fixture=True,identity=self.owner)
  self.assertEqual(cm.exception.status_code,409);self.assertEqual(self.grounds()[0]['visits'][0]['fixture_id'],11)
 def test_local_calendar_boundaries_and_canonical_alias_search(self):
  with self.sessions.begin() as db:
   db.add_all([Fixture(fixture_id=40,venue_id=3,fixture_date=datetime(2026,10,26,10,15,tzinfo=timezone.utc),status='FT',home_team='Boundary',away_team='One',league_name='Synthetic'),Fixture(fixture_id=41,venue_id=1,fixture_date=datetime(2026,10,27,9,30,tzinfo=timezone.utc),status='FT',home_team='Boundary',away_team='Two',league_name='Synthetic')])
  plus=main.get_venue_fixtures(1,around_date='2026-11-03',days=7,calendar_timezone='Pacific/Kiritimati');self.assertIn(40,{f['fixture_id'] for f in plus})
  minus=main.get_venue_fixtures(3,around_date='2026-10-19',days=7,calendar_timezone='Pacific/Honolulu');self.assertIn(41,{f['fixture_id'] for f in minus})
  match=main.get_venue_fixtures(1,around_date='2026-11-04',days=0,calendar_timezone='Pacific/Auckland',search='roma');self.assertEqual([f['fixture_id'] for f in match],[10]);self.assertEqual(match[0]['status'],'FT');self.assertEqual(match[0]['venue_id'],1)
  with self.assertRaises(HTTPException):main.get_venue_fixtures(1,around_date='2026-11-03',days=7,calendar_timezone='Invalid/Zone')

 def test_save_ground_without_date_is_idempotent_and_not_a_matchday(self):
  a=main.record_manual_venue_visit(1,VenueVisitCreate(collection_only=True),self.owner)
  b=main.record_manual_venue_visit(3,VenueVisitCreate(collection_only=True),self.owner)
  self.assertEqual(a.visit_id,b.visit_id);self.assertEqual(a.source,COLLECTION_SOURCE)
  g=self.grounds()[0];self.assertTrue(g['independently_saved']);self.assertEqual(g['visit_count'],0);self.assertEqual(g['visits'],[]);self.assertEqual(g['attended_fixtures'],[])
  attended=self.attend(10);self.remove(attended);self.assertEqual(self.grounds()[0]['visit_count'],0)
 def test_save_dated_visit_and_fixture_visit_preserve_separate_meaning(self):
  d=VenueVisitCreate(visit_date=date(2026,10,10));a=main.record_manual_venue_visit(1,d,self.owner);b=main.record_manual_venue_visit(1,d,self.owner)
  self.assertEqual(a.visit_id,b.visit_id);self.assertEqual(a.source,'manual');self.assertIsNone(a.fixture_id)
  f=VenueVisitCreate(fixture_id=10,visit_date=date(2026,11,3));x=main.record_manual_venue_visit(1,f,self.owner);y=main.record_manual_venue_visit(1,f,self.owner)
  self.assertEqual(x.visit_id,y.visit_id);self.assertEqual(x.source,'fixture_confirmation');g=self.grounds()[0];self.assertEqual(g['visit_count'],2);self.assertEqual([v['fixture_id'] for v in g['attended_fixtures']],[10])
 def test_ground_only_save_rejects_date_or_fixture_without_changes(self):
  for data in [VenueVisitCreate(collection_only=True,visit_date=date(2026,11,3)),VenueVisitCreate(collection_only=True,fixture_id=10)]:
   with self.assertRaises(HTTPException) as cm:main.record_manual_venue_visit(1,data,self.owner)
   self.assertEqual(cm.exception.status_code,422)
  self.assertEqual(self.grounds(),[])
 def test_ground_only_save_does_not_reclassify_existing_undated_attendance(self):
  a=main.record_manual_venue_visit(1,VenueVisitCreate(),self.owner);b=main.record_manual_venue_visit(1,VenueVisitCreate(collection_only=True),self.owner)
  self.assertEqual(a.visit_id,b.visit_id);self.assertEqual(b.source,'manual');self.assertEqual(self.grounds()[0]['visit_count'],1)
