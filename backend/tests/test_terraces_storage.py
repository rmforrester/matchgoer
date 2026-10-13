import unittest
from unittest.mock import Mock,patch
from terraces_storage import PrivatePhotoStorage,StorageUnavailable

class StorageTests(unittest.TestCase):
    def setUp(self):
        self.environment=patch.dict('os.environ',{'SUPABASE_URL':'https://synthetic.supabase.co','SUPABASE_SERVICE_ROLE_KEY':'synthetic-not-a-secret'})
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
