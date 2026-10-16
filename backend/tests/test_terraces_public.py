import asyncio
import json
import os
import time
import unittest
from uuid import uuid4
from unittest.mock import patch

from fastapi import FastAPI
from sqlalchemy import event
from models import TerracePhoto as Photo, VenueVisit
from backend.tests import test_terraces_api as fixtures
import terraces_api as api
import terraces_service as service


class PublicPhotoTests(unittest.TestCase):
    setUp = fixtures.PhotoApiTests.setUp
    tearDown = fixtures.PhotoApiTests.tearDown
    submit = fixtures.PhotoApiTests.submit

    def request(self, path, method="GET", body=None, token=None):
        app = FastAPI(); app.include_router(api.router)
        raw, _, query = path.partition('?')
        headers = [(b'content-type', b'application/json')]
        if token: headers.append((b'authorization', b'Bearer synthetic'))
        async def invoke():
            messages = []
            async def receive(): return {'type':'http.request','body':json.dumps(body or {}).encode(),'more_body':False}
            async def send(message): messages.append(message)
            await app({'type':'http','asgi':{'version':'3.0'},'http_version':'1.1','method':method,'scheme':'http','path':raw,'raw_path':raw.encode(),'query_string':query.encode(),'root_path':'','headers':headers,'client':('127.0.0.1',1),'server':('127.0.0.1',1)}, receive, send)
            return next(m['status'] for m in messages if m['type']=='http.response.start'), json.loads(b''.join(m.get('body',b'') for m in messages if m['type']=='http.response.body'))
        return asyncio.run(invoke())

    def published(self):
        identifier = self.submit(label=uuid4().hex)['photo_id']
        service.approve(self.db, 'Bearer synthetic', identifier)
        return identifier

    def test_default_off_even_for_founder(self):
        self.published()
        with patch.dict(os.environ, {'TERRACES_PUBLIC_READS_ENABLED':'false'}):
            self.assertEqual(self.request('/terraces/photos')[0], 404)
            self.assertEqual(self.request('/terraces/photos', token=True)[0], 404)

    def test_guest_and_non_submitter_browse_without_attendance(self):
        identifier = self.published()
        with patch.dict(os.environ, {'TERRACES_PUBLIC_READS_ENABLED':'true'}):
            for token in (None, True):
                self.provider.subject = str(self.other.user_id)
                code, data = self.request('/terraces/photos', token=token)
                self.assertEqual(code, 200); self.assertEqual(data['photos'][0]['photo_id'], identifier)
                item = data['photos'][0]
                self.assertIsNone(item['fixture_id']); self.assertIsNone(item['match_date'])
                self.assertFalse({'owner_user_id','visit_id','submission_key','status','submitted_at','display_key','thumbnail_key'} & item.keys())

    def test_pending_private_detail_and_public_gate_separate(self):
        identifier = self.submit(label=uuid4().hex)['photo_id']
        with patch.dict(os.environ, {'TERRACES_PUBLIC_READS_ENABLED':'true'}):
            self.assertEqual(self.request(f'/terraces/photos/{identifier}')[0],404)
            self.provider.subject=str(self.other.user_id)
            self.assertEqual(self.request(f'/terraces/photos/{identifier}',token=True)[0],404)
            self.provider.subject=str(self.owner.user_id)
            self.assertEqual(self.request(f'/terraces/photos/{identifier}',token=True)[1]['status'],'PENDING')

    def test_hold_and_removal_exclude_new_public_reads(self):
        identifier = self.published()
        with patch.dict(os.environ, {'TERRACES_PUBLIC_READS_ENABLED':'true'}):
            self.assertEqual(self.request(f'/terraces/photos/{identifier}')[0],200)
            service.hold(self.db,'Bearer synthetic',identifier,'Synthetic legal hold')
            self.assertEqual(self.request('/terraces/photos')[1]['photos'],[])
            self.assertEqual(self.request(f'/terraces/photos/{identifier}')[0],404)
            service.hold(self.db,'Bearer synthetic',identifier,None)
            service.remove(self.db,self.storage,'Bearer synthetic',identifier)
            self.assertEqual(self.request('/terraces/photos')[1]['photos'],[])
            self.assertEqual(self.request(f'/terraces/photos/{identifier}')[0],404)

    def test_report_does_not_require_upload_allowlist(self):
        identifier=self.published(); self.provider.subject=str(self.other.user_id)
        with patch.dict(os.environ, {'TERRACES_PUBLIC_READS_ENABLED':'true'}):
            code,_=self.request(f'/terraces/photos/{identifier}/reports','POST',{'reason':'Synthetic concern'},True)
            self.assertEqual(code,200)
            self.assertEqual(self.request('/terraces/moderator/photos',token=True)[0],403)
            with patch('terraces_api.decode') as decoder:
                self.assertEqual(self.request(f'/terraces/visits/{self.visit.visit_id}/photos','POST',token=True)[0],403)
                decoder.assert_not_called()

    def test_venue_filter_and_page_limits(self):
        self.published()
        with patch.dict(os.environ, {'TERRACES_PUBLIC_READS_ENABLED':'true'}):
            self.assertEqual(len(self.request(f'/terraces/photos?venue_id={self.venue.venue_id}')[1]['photos']),1)
            self.assertEqual(self.request('/terraces/photos?venue_id=2147483647')[1]['photos'],[])
            for limit in (0,25): self.assertEqual(self.request(f'/terraces/photos?limit={limit}')[0],422)

    def test_bounded_page_benchmark(self):
        original=self.visit
        for _ in range(4):
            self.visit=VenueVisit(user_id=self.owner.user_id,venue_id=self.venue.venue_id,source='manual');self.db.add(self.visit);self.db.flush()
            for _ in range(3): self.published()
        calls=[]
        def count(*args): calls.append(1)
        event.listen(self.connection,'before_cursor_execute',count)
        started=time.perf_counter()
        try:
            with patch.object(self.storage,'signed',wraps=self.storage.signed) as signer:
                page=service.public_page(self.db,self.storage,limit=12)
                signing_calls=signer.call_count
        finally: event.remove(self.connection,'before_cursor_execute',count)
        elapsed=time.perf_counter()-started;self.visit=original
        self.assertEqual(len(page['photos']),12);self.assertEqual(signing_calls,24)
        print(json.dumps({'benchmark':'12-photo page, local PostgreSQL/fake Storage','elapsed_ms':round(elapsed*1000,2),'sql_statements':len(calls),'signing_calls':signing_calls,'real_storage_requests':0}))
