"""Synthetic local database tests; no real Storage or supporter data."""
import json
import time
import unittest
from datetime import datetime, timezone, timedelta
from uuid import uuid4
from unittest.mock import patch
from sqlalchemy import event
from models import TerracePhoto as Photo, TerracePhotoEvent as Event, Venue, VenueVisit, Fixture
from backend.tests import test_terraces_public as fixtures
import terraces_service as service

class DiscoverPhotoTests(unittest.TestCase):
    setUp=fixtures.PublicPhotoTests.setUp
    tearDown=fixtures.PublicPhotoTests.tearDown
    request=fixtures.PublicPhotoTests.request
    def ground(self):
        row=Venue(name='Synthetic ground',country='Test');self.db.add(row);self.db.flush();return row
    def photo(self,venue=None,owner=None,at=None,status='APPROVED',ready=True,hold=False,deleted=False,fixture=None,visit=None):
        venue=venue or self.venue;owner=owner or self.owner;at=at or datetime(2026,10,16,tzinfo=timezone.utc)
        if visit is None:
            visit=VenueVisit(user_id=owner.user_id,venue_id=venue.venue_id,fixture_id=fixture.fixture_id if fixture else None,source='manual');self.db.add(visit);self.db.flush()
        key=uuid4().hex
        row=Photo(owner_user_id=owner.user_id,visit_id=visit.visit_id,venue_id=venue.venue_id,fixture_id=visit.fixture_id,source_sha256=key*2,original_bytes=1,display_key=f'photos/{key}/display.jpg',thumbnail_key=f'photos/{key}/thumbnail.jpg',width=1,height=1,thumbnail_width=1,thumbnail_height=1,submission_key=str(uuid4()),consent_version='terraces-public-v1',status='PENDING')
        self.db.add(row);self.db.flush()
        if ready:self.db.add(Event(photo_id=row.photo_id,event_type='STORAGE_READY',payload={},completed_at=at));self.db.flush()
        row.status=status;row.approved_at=at if status=='APPROVED' else None;row.published_at=at if status=='APPROVED' else None
        row.rejected_at=at if status=='REJECTED' else None;row.removed_at=at if status=='REMOVED' else None
        row.storage_deleted_at=at if deleted else None;row.dispute_reason='Synthetic hold' if hold else None;self.db.flush()
        return row
    def page(self,**kwargs):return service.public_page(self.db,self.storage,selection='discover',limit=5,**kwargs)
    def test_latest_per_ground_beyond_a_normal_page_and_bounded_signing(self):
        at=datetime(2026,10,16,tzinfo=timezone.utc)
        for i in range(30):self.photo(at=at-timedelta(seconds=i))
        others=[self.photo(venue=self.ground(),at=at-timedelta(seconds=40+i)) for i in range(4)]
        calls=[]
        def count(*args):calls.append(1)
        event.listen(self.connection,'before_cursor_execute',count);started=time.perf_counter()
        try:
            with patch.object(self.storage,'signed',wraps=self.storage.signed) as signer:
                result=self.page();self.assertEqual(signer.call_count,10)
        finally:event.remove(self.connection,'before_cursor_execute',count)
        self.assertEqual(len({p['venue_id'] for p in result['photos']}),5)
        self.assertEqual([p['photo_id'] for p in result['photos'][1:]],[p.photo_id for p in others])
        self.assertIsNone(result['next_cursor'])
        print(json.dumps({'discover_candidates':34,'sql_statements':len(calls),'elapsed_ms':round((time.perf_counter()-started)*1000,2),'signed_variants':10}))
    def test_internal_identity_tie_preference_and_identical_display_names(self):
        other=self.photo(venue=self.ground(),owner=self.other)
        candidates=[self.photo(venue=self.ground()) for _ in range(5)]
        result=self.page();ids=[p['photo_id'] for p in result['photos']]
        self.assertIn(other.photo_id,ids)
        self.assertEqual(ids,sorted(ids,reverse=True));self.assertEqual(len(ids),5)
        self.assertTrue(all(p['display_name']=='Synthetic supporter' for p in result['photos']))
        self.assertTrue(all(not {'owner_user_id','contributor_id','visit_id','submission_key','source_sha256'} & p.keys() for p in result['photos']))
        self.assertEqual(result,self.page())
        # No older representative replaces the newest at the same ground.
        newest=self.photo(venue=self.db.get(Venue,other.venue_id),at=datetime(2026,10,17,tzinfo=timezone.utc))
        self.assertEqual(self.page()['photos'][0]['photo_id'],newest.photo_id)
    def test_no_filler_and_public_exclusions(self):
        rows=[self.photo() for _ in range(3)]
        for status in ('PENDING','REJECTED','REMOVED'):self.photo(status=status)
        self.photo(ready=False);self.photo(hold=True);self.photo(deleted=True)
        self.assertEqual({p['photo_id'] for p in self.page()['photos']},{rows[-1].photo_id})
        self.assertIsNone(self.page()['photos'][0]['home_team']);self.assertIsNone(self.page()['photos'][0]['match_date'])
    def test_candidate_cap_and_ordinary_cursor_unchanged(self):
        old=self.photo(venue=self.ground(),at=datetime(2020,1,1,tzinfo=timezone.utc))
        for _ in range(121):self.photo()
        self.assertEqual({p['venue_id'] for p in self.page()['photos']},{self.venue.venue_id})
        cursor=None;ids=[]
        while True:
            page=service.public_page(self.db,self.storage,limit=24,cursor=cursor)
            ids.extend(p['photo_id'] for p in page['photos']);cursor=page['next_cursor']
            if not cursor:break
        self.assertEqual(len(ids),122);self.assertEqual(len(set(ids)),122);self.assertEqual(ids[-1],old.photo_id)
    def test_http_validation_activation_and_filter_separation(self):
        self.photo()
        with patch.dict('os.environ',{'TERRACES_PUBLIC_READS_ENABLED':'true'}):
            self.assertEqual(self.request('/terraces/photos?selection=discover&limit=24')[0],200)
            self.assertEqual(self.request('/terraces/photos?selection=invalid')[0],422)
            for query in ('venue_id=1','fixture_id=1','cursor=invalid'):
                self.assertEqual(self.request('/terraces/photos?selection=discover&'+query)[0],422)
        with patch.dict('os.environ',{'TERRACES_PUBLIC_READS_ENABLED':'false'}):
            self.assertEqual(self.request('/terraces/photos?selection=discover')[0],404)
    def test_contributor_does_not_replace_latest_photo_at_same_ground(self):
        other=self.photo(owner=self.other)
        for _ in range(6):self.photo()
        self.assertEqual(len(self.page()['photos']),1)
        self.assertNotIn(other.photo_id,[p['photo_id'] for p in self.page()['photos']])
        other.published_at=datetime(2020,1,1,tzinfo=timezone.utc);self.db.flush()
        self.assertNotIn(other.photo_id,[p['photo_id'] for p in self.page()['photos']])
    def test_four_grounds_six_photos_return_only_four(self):
        at=datetime(2026,10,16,tzinfo=timezone.utc)
        oldest=self.photo(at=at-timedelta(days=2))
        representatives=[self.photo(venue=self.ground(),at=at-timedelta(hours=i+1)) for i in range(3)]
        repeat=self.photo(at=at-timedelta(minutes=2))
        newest=self.photo(at=at-timedelta(minutes=1))
        result=self.page()['photos']
        self.assertEqual([p['photo_id'] for p in result],[newest.photo_id,*[p.photo_id for p in representatives]])
        self.assertEqual(len({p['venue_id'] for p in result}),4)
        self.assertNotIn(oldest.photo_id,[p['photo_id'] for p in result])
    def test_three_grounds_return_three_without_fallback(self):
        at=datetime(2026,10,16,tzinfo=timezone.utc)
        other=[self.photo(venue=self.ground(),at=at-timedelta(days=i+1)) for i in range(2)]
        for i in range(8):self.photo(at=at-timedelta(minutes=i))
        result=self.page()['photos']
        self.assertEqual(len(result),3);self.assertEqual(len({p['venue_id'] for p in result}),3)
        self.assertTrue({p.photo_id for p in other}.issubset({p['photo_id'] for p in result}))
        self.assertEqual(len({p['photo_id'] for p in result}),3)
    def test_canonical_identity_not_ground_name_controls_diversity(self):
        alias_ground=self.ground();alias_ground.name=self.venue.name;self.db.flush()
        self.photo(venue=alias_ground);self.photo();self.photo()
        result=self.page()['photos']
        self.assertEqual(len({p['venue_id'] for p in result}),2)
        self.assertEqual(len({p['venue_name'] for p in result}),1)
    def fixture(self,at=None):
        row=Fixture(fixture_id=900000020+self.db.query(Fixture).count(),home_team='Synthetic home',away_team='Synthetic away',venue_id=self.venue.venue_id,fixture_date=at)
        self.db.add(row);self.db.flush();return row
    def test_matchday_counts_all_contributors_and_only_eligible_fixture_photos(self):
        fixture=self.fixture(datetime(2001,7,3,tzinfo=timezone.utc));other_fixture=self.fixture()
        rows=[self.photo(fixture=fixture),self.photo(fixture=fixture,owner=self.other),self.photo(fixture=fixture)]
        self.photo(fixture=other_fixture)
        for status in ('PENDING','REJECTED','REMOVED'):self.photo(fixture=fixture,status=status)
        self.photo(fixture=fixture,ready=False);self.photo(fixture=fixture,hold=True);self.photo(fixture=fixture,deleted=True)
        for row in rows:self.assertEqual(service.public_matchday_metadata(self.db,row),{'matchday_photo_count':3})
        with patch.dict('os.environ',{'TERRACES_PUBLIC_READS_ENABLED':'true'}):
            code,data=self.request(f'/terraces/photos/{rows[0].photo_id}')
            self.assertEqual(code,200);self.assertEqual(data['matchday_photo_count'],3)
            self.assertFalse({'owner_user_id','visit_id','contributor_id','submission_key'} & data.keys())
        service.remove(self.db,self.storage,'Bearer synthetic',rows[-1].photo_id)
        self.assertEqual(service.public_matchday_metadata(self.db,rows[0]),{'matchday_photo_count':2})
        with patch.dict('os.environ',{'TERRACES_PUBLIC_READS_ENABLED':'true'}):
            self.assertEqual(self.request(f'/terraces/photos/{rows[0].photo_id}')[1]['matchday_photo_count'],2)
    def test_fixture_null_groups_only_same_recorded_visit_never_same_date_or_ground(self):
        rows=[self.photo(visit=self.visit) for _ in range(3)]
        unrelated=self.photo();other_owner=self.photo(owner=self.other)
        from datetime import date
        for row in (rows[0],unrelated,other_owner):self.db.get(VenueVisit,row.visit_id).visit_date=date(2001,7,3)
        self.db.flush()
        self.assertEqual(service.public_matchday_metadata(self.db,rows[0]),{'matchday_photo_count':3})
        self.assertEqual(service.public_matchday_metadata(self.db,unrelated),{'matchday_photo_count':1})
        from types import SimpleNamespace
        self.assertEqual(service.public_matchday_metadata(self.db,SimpleNamespace(venue_id=self.venue.venue_id,fixture_id=None,visit_id=None)),{})
    def test_count_is_complete_outside_candidate_window_and_ordinary_feed_unchanged(self):
        fixture=self.fixture()
        for i in range(123):self.photo(fixture=fixture,owner=self.other if i%2 else self.owner)
        page=self.page();self.assertEqual(len(page['photos']),1)
        self.assertEqual(page['photos'][0]['matchday_photo_count'],123)
        self.assertNotIn('matchday_photo_count',service.public_page(self.db,self.storage,limit=1)['photos'][0])
    def test_two_grounds_never_create_empty_slots_or_repeats(self):
        for _ in range(3):self.photo()
        self.photo(venue=self.ground())
        self.assertEqual(len(self.page()['photos']),2)
    def test_matchday_anchor_and_fixture_pages_share_stable_public_collection(self):
        fixture=self.fixture(datetime(2001,7,3,tzinfo=timezone.utc));different=self.fixture()
        rows=[self.photo(fixture=fixture,owner=self.other if i%2 else self.owner) for i in range(31)]
        self.photo(fixture=different);self.photo()
        expected=sorted([p.photo_id for p in rows],reverse=True)
        for filters in ({'matchday_of':rows[0].photo_id},{'venue_id':self.venue.venue_id,'fixture_id':fixture.fixture_id}):
            ids=[];cursor=None
            while True:
                page=service.public_page(self.db,self.storage,limit=7,cursor=cursor,**filters)
                for item in page['photos']:
                    self.assertFalse({'visit_id','owner_user_id','contributor_id','submission_key','display_key'} & item.keys())
                    self.assertEqual(item['fixture_id'],fixture.fixture_id)
                ids.extend(item['photo_id'] for item in page['photos']);cursor=page['next_cursor']
                if not cursor:break
            self.assertEqual(ids,expected);self.assertEqual(len(set(ids)),31)
    def test_fixture_null_public_anchor_never_exposes_or_merges_other_visits(self):
        from datetime import date
        rows=[self.photo(visit=self.visit) for _ in range(3)];unrelated=self.photo();other=self.photo(owner=self.other)
        for row in (rows[0],unrelated,other):self.db.get(VenueVisit,row.visit_id).visit_date=date(2001,7,3)
        self.db.flush()
        with patch.dict('os.environ',{'TERRACES_PUBLIC_READS_ENABLED':'true'}):
            code,data=self.request(f'/terraces/photos?matchday_of={rows[0].photo_id}&limit=2')
            self.assertEqual(code,200);self.assertEqual([p['photo_id'] for p in data['photos']],[rows[2].photo_id,rows[1].photo_id])
            self.assertTrue(data['next_cursor'])
            from urllib.parse import quote
            code,last=self.request(f'/terraces/photos?matchday_of={rows[0].photo_id}&limit=2&cursor='+quote(data['next_cursor']))
            self.assertEqual(code,200);self.assertEqual([p['photo_id'] for p in last['photos']],[rows[0].photo_id]);self.assertIsNone(last['next_cursor'])
            self.assertTrue(all(not {'visit_id','owner_user_id','contributor_id'} & p.keys() for p in data['photos']+last['photos']))
    def test_matchday_anchor_requires_current_public_eligibility_even_for_owner(self):
        private=[self.photo(status=status) for status in ('PENDING','REJECTED','REMOVED')]
        private.extend([self.photo(ready=False),self.photo(hold=True),self.photo(deleted=True)])
        self.db.commit()  # Keep fixtures across the API's expected error rollbacks.
        with patch.dict('os.environ',{'TERRACES_PUBLIC_READS_ENABLED':'true'}):
            for identifier in [p.photo_id for p in private]+[2147483647]:
                for token in (None,True):
                    if identifier!=2147483647:self.assertIsNotNone(self.db.get(Photo,identifier))
                    self.assertEqual(self.request(f'/terraces/photos?matchday_of={identifier}',token=token)[0],404)
    def test_matchday_anchor_validation_and_removal_are_fail_closed(self):
        anchor=self.photo();self.photo(visit=self.db.get(VenueVisit,anchor.visit_id));self.db.commit()
        with patch.dict('os.environ',{'TERRACES_PUBLIC_READS_ENABLED':'true'}):
            for value in ('0','-1','not-an-id'):self.assertEqual(self.request('/terraces/photos?matchday_of='+value)[0],422)
            for extra in ('venue_id=1','fixture_id=1','selection=discover'):
                self.assertEqual(self.request(f'/terraces/photos?matchday_of={anchor.photo_id}&'+extra)[0],422)
            self.assertEqual(self.request(f'/terraces/photos?matchday_of={anchor.photo_id}')[0],200)
            service.remove(self.db,self.storage,'Bearer synthetic',anchor.photo_id)
            self.assertEqual(self.request(f'/terraces/photos?matchday_of={anchor.photo_id}')[0],404)
        with patch.dict('os.environ',{'TERRACES_PUBLIC_READS_ENABLED':'false'}):
            self.assertEqual(self.request(f'/terraces/photos?matchday_of={anchor.photo_id}')[0],404)
