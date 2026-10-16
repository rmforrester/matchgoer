"""Synthetic local database tests; no real Storage or supporter data."""
import json
import time
import unittest
from datetime import datetime, timezone, timedelta
from uuid import uuid4
from unittest.mock import patch
from sqlalchemy import event
from models import TerracePhoto as Photo, TerracePhotoEvent as Event, Venue, VenueVisit
from backend.tests import test_terraces_public as fixtures
import terraces_service as service

class DiscoverPhotoTests(unittest.TestCase):
    setUp=fixtures.PublicPhotoTests.setUp
    tearDown=fixtures.PublicPhotoTests.tearDown
    request=fixtures.PublicPhotoTests.request
    def ground(self):
        row=Venue(name='Synthetic ground',country='Test');self.db.add(row);self.db.flush();return row
    def photo(self,venue=None,owner=None,at=None,status='APPROVED',ready=True,hold=False,deleted=False):
        venue=venue or self.venue;owner=owner or self.owner;at=at or datetime(2026,10,16,tzinfo=timezone.utc)
        visit=VenueVisit(user_id=owner.user_id,venue_id=venue.venue_id,source='manual');self.db.add(visit);self.db.flush()
        key=uuid4().hex
        row=Photo(owner_user_id=owner.user_id,visit_id=visit.visit_id,venue_id=venue.venue_id,source_sha256=key*2,original_bytes=1,display_key=f'photos/{key}/display.jpg',thumbnail_key=f'photos/{key}/thumbnail.jpg',width=1,height=1,thumbnail_width=1,thumbnail_height=1,submission_key=str(uuid4()),consent_version='terraces-public-v1',status='PENDING')
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
    def test_fills_spare_slots_and_public_exclusions(self):
        rows=[self.photo() for _ in range(3)]
        for status in ('PENDING','REJECTED','REMOVED'):self.photo(status=status)
        self.photo(ready=False);self.photo(hold=True);self.photo(deleted=True)
        self.assertEqual({p['photo_id'] for p in self.page()['photos']},{p.photo_id for p in rows})
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
    def test_filler_contributor_ties_use_internal_ids_without_displacing_newer(self):
        other=self.photo(owner=self.other)
        for _ in range(6):self.photo()
        self.assertIn(other.photo_id,[p['photo_id'] for p in self.page()['photos']])
        other.published_at=datetime(2020,1,1,tzinfo=timezone.utc);self.db.flush()
        self.assertNotIn(other.photo_id,[p['photo_id'] for p in self.page()['photos']])
