"""Synthetic owner/ground data, local PostgreSQL and existing authentication policy."""
import os,unittest
from datetime import date,datetime,timezone
from unittest.mock import patch
from fastapi import HTTPException,Response
from fastapi.testclient import TestClient
import main,community_tips
from backend.tests import test_build12_history as history
from backend.tests import test_terraces_b1 as photos
from models import Fixture,Venue,VenueVisit,MatchdayTip
from schemas import VenueVisitCreate,VenueVisitUpdate,MatchdayTipCreate
from identity import optional_current_identity

@unittest.skipUnless(os.getenv('MATCHGOER_LOCAL_POSTGRES_TEST')=='TRUE','Explicit local PostgreSQL opt-in')
class GroupingTests(unittest.TestCase):
 setUp=history.Build12HistoryTests.setUp
 attend=history.Build12HistoryTests.attend
 remove=history.Build12HistoryTests.remove
 def projection(self):return main.get_my_grounds(self.owner,footprint=True)
 def seed_competitions(self):
  with self.sessions.begin() as db:
   v=db.get(Venue,1);v.name='Hinchliffe Stadium';v.city='Paterson';v.country='USA'
   for fid,league,name in [(10,7001,'USL League One'),(11,7002,'Synthetic Cup'),(20,7003,'International Cup')]:
    f=db.get(Fixture,fid);f.league_id=league;f.league_name=name;f.season=2026;f.country='USA';f.fixture_date=datetime(2026,10,24,20,tzinfo=timezone.utc)
   db.get(Fixture,10).home_team='NY Cosmos';db.get(Fixture,10).away_team='Chattanooga Red Wolves'
 def test_hinchliffe_uses_actual_competition_without_current_home_catalogue(self):
  self.seed_competitions();self.attend(10);r=self.projection();groups=r['footprint']['attendance_competitions']
  self.assertEqual([(x['competition_id'],x['name']) for x in groups],[(7001,'USL League One')]);self.assertEqual(groups[0]['grounds'][0]['venue_id'],1);self.assertEqual(groups[0]['coverage'],'attendance');self.assertIsNone(groups[0]['lifetime_clubs'])
  self.assertEqual(r['grounds'][0]['venue_city'],'Paterson');self.assertEqual(r['grounds'][0]['visit_count'],1)
 def test_one_physical_ground_can_appear_in_league_and_cup_without_duplicate_visits(self):
  self.seed_competitions();a=self.attend(10);b=self.attend(11);self.attend(10)
  r=self.projection();self.assertEqual(len(r['grounds']),1);self.assertEqual(r['grounds'][0]['visit_count'],2)
  groups=r['footprint']['attendance_competitions'];self.assertEqual(len(groups),2);self.assertEqual({v for x in groups for g in x['grounds'] for v in g['visit_ids']},{a.visit_id,b.visit_id})
 def test_manual_ground_and_dated_visit_do_not_inherit_current_home_competition(self):
  self.seed_competitions();main.record_manual_venue_visit(1,VenueVisitCreate(collection_only=True),self.owner);main.record_manual_venue_visit(2,VenueVisitCreate(visit_date=date(2026,10,1)),self.owner)
  r=self.projection();self.assertEqual(r['footprint']['attendance_competitions'],[]);self.assertEqual(len(r['grounds']),2)
 def test_change_fixture_moves_competition_and_remove_final_clears_group(self):
  self.seed_competitions();a=self.attend(10);main.update_venue_visit_fixture(1,a.visit_id,VenueVisitUpdate(fixture_id=20,allow_ground_change=True),self.owner)
  groups=self.projection()['footprint']['attendance_competitions'];self.assertEqual([x['competition_id'] for x in groups],[7003]);self.assertEqual(groups[0]['grounds'][0]['venue_id'],2)
  main.delete_personal_matchday(2,a.visit_id,identity=self.owner);self.assertEqual(self.projection()['footprint']['attendance_competitions'],[])
 def test_remove_one_competition_then_ground_keeps_other_owner(self):
  self.seed_competitions();a=self.attend(10);self.attend(11);self.attend(10,self.other);self.remove(a)
  self.assertEqual([x['competition_id'] for x in self.projection()['footprint']['attendance_competitions']],[7002]);p=main.preview_personal_ground_removal(1,self.owner);main.delete_personal_ground(1,p['revision'],self.owner)
  self.assertEqual(self.projection()['footprint']['attendance_competitions'],[]);self.assertEqual(len(main.get_my_grounds(self.other)),1)
 def test_missing_competition_metadata_falls_back_without_inventing_identity(self):
  self.attend(10);self.assertEqual(self.projection()['footprint']['attendance_competitions'],[])

 def test_known_competition_without_season_still_groups_without_inventing_calendar(self):
  self.seed_competitions()
  with self.sessions.begin() as db:db.get(Fixture,10).season=None
  self.attend(10);group=self.projection()['footprint']['attendance_competitions'][0]
  self.assertEqual(group['name'],'USL League One');self.assertIsNone(group['season']);self.assertIsNone(group['season_start']);self.assertIsNone(group['season_end'])
 def test_concurrent_tip_retries_and_aliases_create_one_canonical_row(self):
  from concurrent.futures import ThreadPoolExecutor
  from threading import Barrier
  barrier=Barrier(2)
  def submit(venue):
   with self.sessions.begin() as db:
    barrier.wait(timeout=5);return community_tips.create(db,MatchdayTipCreate(venue_id=venue,tip='Concurrent advice'),self.owner)['tip_id']
  with ThreadPoolExecutor(max_workers=2) as pool:
   a=pool.submit(submit,1);b=pool.submit(submit,3);self.assertEqual(a.result(timeout=15),b.result(timeout=15))
  with self.sessions() as db:self.assertEqual(db.query(MatchdayTip).count(),1);self.assertEqual(db.query(MatchdayTip).one().venue_id,1)

class CommunityTipTests(unittest.TestCase):
 setUp=photos.PhotoB1Tests.setUp
 tearDown=photos.PhotoB1Tests.tearDown
 def client(self):
  main.app.dependency_overrides[optional_current_identity]=lambda:type('Owner',(),{'user_id':self.owner.user_id})()
  self.addCleanup(main.app.dependency_overrides.pop,optional_current_identity,None)
  return TestClient(main.app,raise_server_exceptions=False)
 def test_full_pending_queue_approval_correct_ground_and_rejection_lifecycle(self):
  with patch.object(main,'SessionLocal',return_value=self.db),patch.object(self.db,'close'):
   c=self.client();result=c.post('/tips',json={'venue_id':self.venue.venue_id,'tip':'Use the signed pedestrian entrance.'});self.assertEqual(result.status_code,200,result.text);tip=result.json();self.assertEqual(tip['status'],'pending')
   row=self.db.get(MatchdayTip,tip['tip_id']);self.assertEqual(row.author_user_id,self.owner.user_id);self.assertIsNotNone(row.created_at)
   self.assertEqual(c.get(f'/venues/{self.venue.venue_id}/tips').json(),[])
   queue=c.get('/moderator/tips',headers={'Authorization':'Bearer synthetic'});self.assertEqual(queue.status_code,200,queue.text);self.assertIn(tip['tip_id'],[x['tip_id'] for x in queue.json()['tips']])
   approve=c.post(f"/moderator/tips/{tip['tip_id']}",json={'decision':'APPROVE','expected_status':'PENDING'},headers={'Authorization':'Bearer synthetic'});self.assertEqual(approve.status_code,200,approve.text)
   public=c.get(f'/venues/{self.venue.venue_id}/tips');self.assertEqual(public.headers['cache-control'],'no-store');self.assertEqual([x['tip_id'] for x in public.json()],[tip['tip_id']]);self.assertNotIn('author_user_id',public.json()[0]);self.assertNotIn('user_id',public.json()[0])
   other=Venue(name='Unrelated ground');self.db.add(other);self.db.flush();self.assertEqual(c.get(f'/venues/{other.venue_id}/tips').json(),[])
   reopened=self.client();self.assertEqual(reopened.get(f'/venues/{self.venue.venue_id}/tips').json()[0]['tip_id'],tip['tip_id'])
   reject=c.post(f"/moderator/tips/{tip['tip_id']}",json={'decision':'REJECT','expected_status':'APPROVED'},headers={'Authorization':'Bearer synthetic'});self.assertEqual(reject.status_code,200,reject.text);self.assertEqual(c.get(f'/venues/{self.venue.venue_id}/tips').json(),[])
 def test_pending_and_rejected_are_private_and_reactions_cannot_disclose_them(self):
  row=MatchdayTip(venue_id=self.venue.venue_id,tip='Private advice',status='pending',author_user_id=self.owner.user_id);self.db.add(row);self.db.flush()
  with patch.object(main,'SessionLocal',return_value=self.db),patch.object(self.db,'close'):
   c=self.client()
   for status in ['pending','rejected']:
    row.status=status;self.db.flush();self.assertEqual(c.get(f'/venues/{self.venue.venue_id}/tips').json(),[])
    self.assertEqual(c.post(f'/tips/{row.tip_id}/helpful').status_code,404);self.assertEqual(c.post(f'/tips/{row.tip_id}/report').status_code,404)
 def test_authorization_is_server_side_and_submitter_cannot_self_approve(self):
  row=MatchdayTip(venue_id=self.venue.venue_id,tip='Tip',status='pending',author_user_id=self.other.user_id);self.db.add(row);self.db.flush();self.provider.subject=str(self.other.user_id)
  for action in [lambda:community_tips.queue(self.db,'Bearer synthetic','PENDING',24,0),lambda:community_tips.moderate(self.db,'Bearer synthetic',row.tip_id,'APPROVE','PENDING')]:
   with self.assertRaises(HTTPException) as cm:action()
   self.assertEqual(cm.exception.status_code,403)
  with patch('terraces.verify_claim_provider_identity',side_effect=HTTPException(401,'Sign in')):
   with self.assertRaises(HTTPException):community_tips.queue(self.db,None,'PENDING',24,0)
  self.assertEqual(row.status,'pending')
 def test_duplicate_taps_do_not_create_rows_or_accept_spoofed_status(self):
  with patch.object(main,'SessionLocal',return_value=self.db),patch.object(self.db,'close'):
   c=self.client();payload={'venue_id':self.venue.venue_id,'tip':'  Keep the access gate clear.  ','status':'active','author_user_id':self.other.user_id}
   a=c.post('/tips',json=payload);b=c.post('/tips',json=payload);self.assertEqual(a.status_code,200,a.text);self.assertEqual(a.json()['tip_id'],b.json()['tip_id']);self.assertEqual(a.json()['status'],'pending');self.assertEqual(self.db.query(MatchdayTip).count(),1)
 def test_validation_and_missing_ground(self):
  with patch.object(main,'SessionLocal',return_value=self.db),patch.object(self.db,'close'):
   c=self.client()
   for tip in ['','   ','x'*2001,'bad\x00text']:
    self.assertEqual(c.post('/tips',json={'venue_id':self.venue.venue_id,'tip':tip}).status_code,422)
   self.assertEqual(c.post('/tips',json={'venue_id':999999999,'tip':'Valid advice'}).status_code,404);self.assertEqual(self.db.query(MatchdayTip).count(),0)
 def test_stale_moderation_cannot_override_and_repetition_is_idempotent(self):
  row=MatchdayTip(venue_id=self.venue.venue_id,tip='Advice',status='pending');self.db.add(row);self.db.flush()
  a=community_tips.moderate(self.db,'Bearer synthetic',row.tip_id,'APPROVE','PENDING');self.assertEqual(a['status'],'APPROVED');self.assertEqual(community_tips.moderate(self.db,'Bearer synthetic',row.tip_id,'APPROVE','PENDING')['status'],'APPROVED')
  with self.assertRaises(HTTPException) as cm:community_tips.moderate(self.db,'Bearer synthetic',row.tip_id,'REJECT','PENDING')
  self.assertEqual(cm.exception.status_code,409);self.assertEqual(row.status,'active')
 def test_canonical_alias_and_text_rendering_payload_preserve_identity_and_privacy(self):
  alias=Venue(name='Verified alias',canonical_venue_id=self.venue.venue_id,equivalence_source='https://synthetic.test/ground');self.db.add(alias);self.db.flush();self.db.info.pop('venue_resolution',None)
  text='<script>alert("not executable text")</script>';data=MatchdayTipCreate(venue_id=alias.venue_id,tip=text)
  a=community_tips.create(self.db,data,None);b=community_tips.create(self.db,MatchdayTipCreate(venue_id=self.venue.venue_id,tip=text),None);self.assertEqual(a['tip_id'],b['tip_id']);self.assertEqual(a['venue_id'],self.venue.venue_id);self.assertEqual(a['tip'],text);self.assertNotIn('author_user_id',a)
 def test_reported_tips_return_to_pending_queue_and_do_not_become_public(self):
  self.db.add(MatchdayTip(venue_id=self.venue.venue_id,tip='Reported advice',status='reported'));self.db.flush();page=community_tips.queue(self.db,'Bearer synthetic','PENDING',24,0);self.assertEqual(page['pending_count'],1);self.assertEqual(page['tips'][0]['status'],'PENDING')

 def test_failed_database_commit_returns_error_and_rolls_back_tip(self):
  with patch.object(main,'SessionLocal',return_value=self.db),patch.object(self.db,'close'),patch.object(self.db,'commit',side_effect=RuntimeError('synthetic commit failure')):
   c=self.client();response=c.post('/tips',json={'venue_id':self.venue.venue_id,'tip':'Uncommitted advice'})
   self.assertEqual(response.status_code,500);self.assertEqual(self.db.query(MatchdayTip).filter_by(tip='Uncommitted advice').count(),0)
 def test_withdrawn_tip_is_not_public(self):
  tip=MatchdayTip(venue_id=self.venue.venue_id,tip='Withdrawn advice',status='withdrawn');self.db.add(tip);self.db.flush()
  with patch.object(main,'SessionLocal',return_value=self.db),patch.object(self.db,'close'):
   self.assertEqual(self.client().get(f'/venues/{self.venue.venue_id}/tips').json(),[])

 def test_legacy_missing_ground_remains_reviewable_but_cannot_be_approved(self):
  row=MatchdayTip(venue_id=None,tip='Legacy unbound advice',status='pending',created_at=None);self.db.add(row);self.db.flush()
  queue=community_tips.queue(self.db,'Bearer synthetic','PENDING',24,0);self.assertEqual(queue['tips'][0]['venue_name'],'Ground not recorded')
  with self.assertRaises(HTTPException) as cm:community_tips.moderate(self.db,'Bearer synthetic',row.tip_id,'APPROVE','PENDING')
  self.assertEqual(cm.exception.status_code,409);self.assertEqual(community_tips.moderate(self.db,'Bearer synthetic',row.tip_id,'REJECT','PENDING')['status'],'REJECTED')
