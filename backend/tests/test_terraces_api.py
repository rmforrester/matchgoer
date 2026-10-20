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
    def test_owned_photo_upload_capability_uses_current_fail_closed_allowlist(self):
        with patch.dict('os.environ', {'TERRACES_UPLOAD_USER_IDS':str(self.owner.user_id)}):
            result=api.owned_photos(self.visit.visit_id,Response(),authorization='Bearer synthetic')
            self.assertTrue(result['can_submit'])
        for value in ('', 'not-an-id', str(self.other.user_id)):
            with patch.dict('os.environ', {'TERRACES_UPLOAD_USER_IDS':value}):
                result=api.owned_photos(self.visit.visit_id,Response(),authorization='Bearer synthetic')
                self.assertFalse(result['can_submit'])
                self.assertTrue(result['reconciliation_supported'])
        self.provider.subject=str(self.other.user_id)
        with self.assertRaises(HTTPException) as failure:
            api.owned_photos(self.visit.visit_id,Response(),authorization='Bearer synthetic')
        self.assertEqual(failure.exception.status_code,404)

    def test_owner_submission_reconciliation_key_is_private(self):
        identifier = self.submit()['photo_id']
        row = self.db.get(Photo, identifier)
        result = api.owned_photos(self.visit.visit_id, Response(), authorization='Bearer synthetic')
        self.assertTrue(result['reconciliation_supported'])
        owned = result['photos']
        self.assertEqual(owned[0]['submission_key'], row.submission_key)
        self.assertEqual(owned[0]['upload_state'], 'ready')
        import terraces_service as service
        self.assertNotIn('submission_key', service.photo_payload(self.db, self.storage, row))
        self.assertNotIn('submission_key', service.photo_payload(self.db, self.storage, row, private=True))
        self.provider.subject = str(self.other.user_id)
        with self.assertRaises(HTTPException):
            api.owned_photos(self.visit.visit_id, Response(), authorization='Bearer synthetic')

    def test_public_photo_http_route_requires_explicit_activation(self):
        from fastapi import FastAPI
        app=FastAPI();app.include_router(api.router)
        async def get():
            messages=[]
            async def receive():return {'type':'http.request','body':b'','more_body':False}
            async def send(message):messages.append(message)
            scope={'type':'http','asgi':{'version':'3.0'},'http_version':'1.1','method':'GET','scheme':'http','path':'/terraces/photos','raw_path':b'/terraces/photos','query_string':b'','root_path':'','headers':[(b'authorization',b'Bearer synthetic')],'client':('127.0.0.1',1),'server':('127.0.0.1',1)}
            await app(scope,receive,send)
            return next(m['status'] for m in messages if m['type']=='http.response.start')
        with patch('terraces_service.public_page',return_value={'photos':[],'next_cursor':None}) as reader:
            self.assertEqual(asyncio.run(get()),404);reader.assert_not_called()
            with patch.dict('os.environ', {'TERRACES_PUBLIC_READS_ENABLED':'true'}):
                self.assertEqual(asyncio.run(get()),200)
                self.provider.subject=str(self.other.user_id)
                self.assertEqual(asyncio.run(get()),200)
    def test_controlled_access_missing_malformed_or_other_account_denied(self):
        from terraces import require_photo_submitter
        for value in ('', '0', '-1', '1,,2', '1,', ',1', '1,invalid', '1,0', '1,-2', '1,2147483648', '2147483648', 'not-an-id'):
            with patch.dict('os.environ',{'TERRACES_UPLOAD_USER_IDS':value}),self.assertRaises(HTTPException):
                require_photo_submitter(self.db,'Bearer synthetic')
        self.provider.subject=str(self.other.user_id)
        with self.assertRaises(HTTPException):api.controlled_photo_access('Bearer synthetic')
    def test_two_upload_accounts_and_independent_moderator_configuration(self):
        from terraces import PhotoActor, require_photo_submitter, require_moderator
        with patch.dict('os.environ', {'TERRACES_UPLOAD_USER_IDS':'1347, 830', 'TERRACES_MODERATOR_USER_ID':''}):
            for identifier in (1347,830):
                with patch('terraces.require_verified_account',return_value=PhotoActor(identifier)):
                    self.assertEqual(require_photo_submitter(self.db,'Bearer synthetic').user_id,identifier)
                    with self.assertRaises(HTTPException):require_moderator(self.db,'Bearer synthetic')
            with patch('terraces.require_verified_account',return_value=PhotoActor(999)):
                with self.assertRaises(HTTPException):require_photo_submitter(self.db,'Bearer synthetic')
            with patch.dict('os.environ',{'TERRACES_MODERATOR_USER_ID':'1347'}):
                with patch('terraces.require_verified_account',return_value=PhotoActor(1347)):
                    self.assertEqual(require_moderator(self.db,'Bearer synthetic').user_id,1347)
                with patch('terraces.require_verified_account',return_value=PhotoActor(830)):
                    with self.assertRaises(HTTPException):require_moderator(self.db,'Bearer synthetic')

    def test_allowlist_whitespace_duplicates_and_invalid_member(self):
        from terraces import configured_upload_user_ids
        with patch.dict('os.environ',{'TERRACES_UPLOAD_USER_IDS':'1347, 830,1347'}):
            self.assertEqual(configured_upload_user_ids(),frozenset((1347,830)))
        for value in ('1347,bad','1347,2147483648','1347,','', '1347,8 30'):
            with patch.dict('os.environ',{'TERRACES_UPLOAD_USER_IDS':value}):
                self.assertEqual(configured_upload_user_ids(),frozenset())

    def test_upload_denied_before_decode_or_storage_and_routes_are_guarded(self):
        self.provider.subject=str(self.other.user_id)
        with patch('terraces_api.decode') as decoder,self.assertRaises(HTTPException):self.upload(self.encoded())
        decoder.assert_not_called();self.assertEqual(self.storage.objects,{})
        self.assertTrue(api.router.routes)
        for route in api.router.routes:
            self.assertTrue(any(dependency.dependency is api.photo_access for dependency in route.dependencies))
    def test_submitter_and_moderator_permissions_are_independent(self):
        from terraces import require_moderator,require_photo_submitter
        with patch.dict('os.environ',{'TERRACES_MODERATOR_USER_ID':''}):
            self.assertEqual(require_photo_submitter(self.db,'Bearer synthetic').user_id,self.owner.user_id)
            with self.assertRaises(HTTPException):require_moderator(self.db,'Bearer synthetic')
        with patch.dict('os.environ',{'TERRACES_UPLOAD_USER_IDS':''}):
            self.assertEqual(require_moderator(self.db,'Bearer synthetic').user_id,self.owner.user_id)
            with self.assertRaises(HTTPException):api.controlled_photo_access('Bearer synthetic')
    def test_allowed_account_still_cannot_upload_to_another_attendance(self):
        self.provider.subject=str(self.other.user_id)
        with patch.dict('os.environ',{'TERRACES_UPLOAD_USER_IDS':str(self.other.user_id)}),self.assertRaises(HTTPException) as error:
            self.upload(self.encoded())
        self.assertEqual(error.exception.status_code,404)
    def test_guest_unverified_identity_denied_even_with_submitter_configuration(self):
        self.provider.subject=str(self.guest.user_id)
        with self.assertRaises(HTTPException):api.controlled_photo_access('Bearer synthetic')
        with patch('terraces.verify_claim_provider_identity',side_effect=HTTPException(401,'Unverified synthetic account')),self.assertRaises(HTTPException):
            api.controlled_photo_access('Bearer synthetic')
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
        result=self.upload(self.encoded());self.assertEqual(result['status'],'APPROVED')
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
