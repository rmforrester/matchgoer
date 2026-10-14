import asyncio,base64,json,unittest,subprocess
from contextlib import nullcontext
from io import BytesIO
from unittest.mock import patch
from fastapi import HTTPException,Response
from starlette.requests import Request
from PIL import Image
import terraces_api as api
from backend.tests import test_terraces_b1 as fixtures
from terraces_storage import LazyPrivatePhotoStorage
from models import TerracePhoto as Photo

class PhotoApiTests(unittest.TestCase):
    submit=fixtures.PhotoB1Tests.submit
    def setUp(self):
        fixtures.PhotoB1Tests.setUp(self)
        self.session=patch('terraces_api.SessionLocal',lambda:nullcontext(self.db));self.session.start()
        self.storage_factory=patch('terraces_api.PrivatePhotoStorage',lambda:self.storage);self.storage_factory.start()
    def tearDown(self):
        self.storage_factory.stop();self.session.stop();fixtures.PhotoB1Tests.tearDown(self)
    def request(self,data):
        sent=False
        async def receive():
            nonlocal sent
            if sent:return {'type':'http.request','body':b'','more_body':False}
            sent=True;return {'type':'http.request','body':data,'more_body':False}
        return Request({'type':'http','method':'POST','path':'/','headers':[]},receive=receive)
    def encoded(self):
        raw=BytesIO();Image.new('RGB',(16,10),'red').save(raw,format='JPEG');return raw.getvalue()
    def upload(self,data,metadata=None):
        meta=base64.urlsafe_b64encode(json.dumps(metadata or self.meta).encode()).decode()
        return asyncio.run(api.submit(self.visit.visit_id,self.request(data),Response(),authorization='Bearer synthetic',idempotency_key='f1d8e839-7807-4690-88e2-3f0711b65b32',x_terraces_metadata=meta))
    def test_real_jpeg_subprocess_and_header_contract(self):
        result=self.upload(self.encoded());self.assertEqual(result['status'],'PENDING')
        self.assertEqual(len(self.storage.objects),2)
    def test_oversized_stream_and_malicious_image(self):
        for data in (b'x'*10_000_001,b'<svg><script>bad</script></svg>'):
            with self.assertRaises(HTTPException) as error:self.upload(data)
            self.assertIn(error.exception.status_code,(413,422))
        self.assertEqual(self.storage.objects,{})
    def test_consent_and_extra_canonical_fields_rejected(self):
        for meta in ({**self.meta,'public_consent':'yes'},{**self.meta,'venue_id':1},{**self.meta,'caption':'x'*201}):
            with self.assertRaises(HTTPException) as error:self.upload(self.encoded(),meta)
            self.assertEqual(error.exception.status_code,422)
    def test_worker_timeout_safe_no_persistence(self):
        with patch('terraces_api.subprocess.run',side_effect=subprocess.TimeoutExpired('image',15)),self.assertRaises(HTTPException):
            api.decode(self.encoded())
        self.assertEqual(self.db.query(Photo).count(),0)
    def test_private_detail_cannot_be_read_by_other_owner(self):
        identifier=self.submit()['photo_id'];self.provider.subject=str(self.other.user_id)
        with self.assertRaises(HTTPException):api.photo_detail(identifier,Response(),authorization='Bearer synthetic')
        self.provider.subject=str(self.owner.user_id)
        self.assertEqual(api.photo_detail(identifier,Response(),authorization='Bearer synthetic')['status'],'PENDING')
        with self.assertRaises(HTTPException):api.photo_detail(identifier,Response(),authorization=None)
    def test_storage_unconfigured_does_not_prevent_unpublishing(self):
        identifier=self.submit()['photo_id'];import terraces_service as service
        service.approve(self.db,'Bearer synthetic',identifier)
        with patch.dict('os.environ',{},clear=True):
            result=service.remove(self.db,LazyPrivatePhotoStorage(),'Bearer synthetic',identifier)
        self.assertEqual(result['status'],'REMOVED');self.assertEqual(result['physical_cleanup'],'pending')
    def test_default_main_has_no_terraces_routes(self):
        import main
        self.assertFalse(any(getattr(route,'path','').startswith('/terraces') for route in main.app.routes))
    def test_database_error_is_safe_and_rolls_back(self):
        from sqlalchemy.exc import DBAPIError
        with self.assertRaises(HTTPException) as failure:
            api.transaction(lambda db: (_ for _ in ()).throw(DBAPIError('private SQL',{},Exception('private content'))))
        self.assertEqual(failure.exception.status_code,503)
        self.assertNotIn('private',failure.exception.detail)
