import unittest
import base64,json
from unittest.mock import Mock,patch
from terraces_storage import PrivatePhotoStorage,StorageUnavailable,credential_headers

class StorageTests(unittest.TestCase):
    def setUp(self):
        self.modern='sb_secret_'+'synthetic_only_not_a_real_key_00000'
        self.environment=patch.dict('os.environ',{'SUPABASE_URL':'https://synthetic.supabase.co','SUPABASE_SECRET_KEY':self.modern,'SUPABASE_SERVICE_ROLE_KEY':''})
        self.environment.start();self.session=Mock();self.storage=PrivatePhotoStorage(session=self.session)
        self.key='photos/'+'a'*32+'/display.jpg'
    def tearDown(self):self.environment.stop()
    def response(self,code,body=None,data=b'image'):
        value=Mock(status_code=code);value.json.return_value=body;value.iter_content.return_value=[data];return value
    def test_unconfigured_storage_denies(self):
        with patch.dict('os.environ',{},clear=True),self.assertRaises(StorageUnavailable):PrivatePhotoStorage()
    def test_keys_and_https_are_not_client_selected(self):
        for key in ['../other.jpg','photos/../display.jpg','photos/'+'a'*32+'/original.heic','https://other.test/image']:
            with self.assertRaises(StorageUnavailable):self.storage.put(key,b'image')
        self.session.request.assert_not_called()
        with patch.dict('os.environ',{'SUPABASE_URL':'http://localhost'}),self.assertRaises(StorageUnavailable):PrivatePhotoStorage()
    def test_immutable_put_and_safe_retry(self):
        self.session.request.side_effect=[self.response(409),self.response(200,data=b'image')]
        self.storage.put(self.key,b'image')
        request=self.session.request.call_args_list[0]
        self.assertEqual(request.kwargs['headers']['x-upsert'],'false')
        self.assertFalse(request.kwargs['allow_redirects'])
    def test_mismatched_object_never_overwritten(self):
        self.session.request.side_effect=[self.response(409),self.response(200,data=b'different')]
        with self.assertRaises(StorageUnavailable):self.storage.put(self.key,b'image')
        self.assertEqual([r.args[0] for r in self.session.request.call_args_list],['POST','GET'])
    def test_delete_uses_private_bucket_bulk_contract(self):
        self.session.request.return_value=self.response(200,[]);self.storage.delete(self.key)
        call=self.session.request.call_args
        self.assertEqual(call.args[0],'DELETE');self.assertTrue(call.args[1].endswith('/object/terraces-photos'))
        self.assertEqual(call.kwargs['json'],{'prefixes':[self.key]})
        self.session.request.return_value=self.response(404)
        with self.assertRaises(StorageUnavailable):self.storage.delete(self.key)
    def test_signed_urls_short_lived_same_host(self):
        self.session.request.return_value=self.response(200,{'signedURL':'/object/sign/terraces-photos/'+self.key+'?token=synthetic'})
        url=self.storage.signed(self.key);self.assertTrue(url.startswith('https://synthetic.supabase.co/storage/v1/object/sign/'))
        self.assertEqual(self.session.request.call_args.kwargs['json'],{'expiresIn':90})
        self.session.request.return_value=self.response(200,{'signedURL':'https://evil.test/object/sign/terraces-photos/'+self.key})
        with self.assertRaises(StorageUnavailable):self.storage.signed(self.key)

    def legacy(self,role='service_role',exp=4102444800,alg='HS256'):
        def encode(value):return base64.urlsafe_b64encode(json.dumps(value).encode()).decode().rstrip('=')
        return '.'.join((encode({'alg':alg,'typ':'JWT'}),encode({'role':role,'exp':exp}),base64.urlsafe_b64encode(b'synthetic-signature-not-valid!!!').decode().rstrip('=')))

    def test_modern_headers_for_upload_delete_and_sign(self):
        self.session.request.side_effect=[self.response(200),self.response(200,[]),self.response(200,{'signedURL':'/object/sign/terraces-photos/'+self.key+'?token=synthetic'})]
        self.storage.put(self.key,b'image');self.storage.delete(self.key);self.storage.signed(self.key)
        for call in self.session.request.call_args_list:
            self.assertEqual(call.kwargs['headers']['apikey'],self.modern)
            self.assertNotIn('Authorization',call.kwargs['headers'])

    def test_legacy_fallback_preserves_headers(self):
        token=self.legacy()
        with patch.dict('os.environ',{'SUPABASE_SECRET_KEY':'','SUPABASE_SERVICE_ROLE_KEY':token}):
            storage=PrivatePhotoStorage(session=self.session)
        self.session.request.return_value=self.response(200);storage.put(self.key,b'image')
        headers=self.session.request.call_args.kwargs['headers']
        self.assertEqual(headers['apikey'],token);self.assertEqual(headers['Authorization'],'Bearer '+token)

    def test_modern_preference_and_no_fallback_from_invalid_preferred_key(self):
        with patch.dict('os.environ',{'SUPABASE_SERVICE_ROLE_KEY':self.legacy()}):
            self.assertEqual(PrivatePhotoStorage().auth_headers,{'apikey':self.modern})
        with patch.dict('os.environ',{'SUPABASE_SECRET_KEY':'malformed','SUPABASE_SERVICE_ROLE_KEY':self.legacy()}),self.assertRaises(StorageUnavailable):PrivatePhotoStorage()

    def test_missing_malformed_publishable_and_wrong_role_denied(self):
        for value in ('','sb_secret_',self.modern+'\n','sb_secret_'+'x'*513,'sb_secret_bad value','"'+self.modern+'"','sb_publishable_'+'x'*40,self.legacy('anon'),self.legacy(exp=1),self.legacy(alg='none'),'a.b.c','x'*8193):
            with patch.dict('os.environ',{'SUPABASE_SECRET_KEY':value,'SUPABASE_SERVICE_ROLE_KEY':''}),self.assertRaises(StorageUnavailable) as failure:PrivatePhotoStorage()
            self.assertNotIn(value,str(failure.exception)) if value else None
        self.session.request.assert_not_called()

    def test_auth_header_override_rejected(self):
        for name in ('Authorization','authorization','APIKEY'):
            with self.assertRaises(StorageUnavailable):self.storage.request('POST','/storage/v1/object',headers={name:'synthetic'})
        self.session.request.assert_not_called()

    def test_request_error_does_not_expose_key(self):
        import requests
        self.session.request.side_effect=requests.Timeout(self.modern)
        with self.assertRaises(StorageUnavailable) as failure:self.storage.put(self.key,b'image')
        self.assertNotIn(self.modern,str(failure.exception));self.assertTrue(failure.exception.__suppress_context__)

    def test_opaque_secret_has_no_invented_minimum_length(self):
        for length in (1,31,32,512):
            synthetic='sb_secret_'+'x'*length
            with patch.dict('os.environ',{'SUPABASE_SECRET_KEY':synthetic}):
                storage=PrivatePhotoStorage(session=self.session)
            self.assertEqual(storage.auth_headers,{'apikey':synthetic})
        self.session.request.assert_not_called()

    def test_shape_acceptance_does_not_override_provider_authentication(self):
        synthetic='sb_secret_'+'x'*31
        with patch.dict('os.environ',{'SUPABASE_SECRET_KEY':synthetic}):storage=PrivatePhotoStorage(session=self.session)
        self.session.request.return_value=self.response(401,{'message':'synthetic invalid key'})
        with self.assertRaises(StorageUnavailable) as failure:storage.put(self.key,b'image')
        self.assertNotIn(synthetic,str(failure.exception));self.assertEqual(self.session.request.call_count,1)

    def test_control_characters_are_rejected_without_environment_round_trip(self):
        # The OS rejects embedded NUL before getenv; exercise the parser itself.
        for control in ('\x00','\t','\r','\n'):
            with self.assertRaises(StorageUnavailable):credential_headers(self.modern+control)
