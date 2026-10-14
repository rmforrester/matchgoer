import hashlib,json,subprocess,unittest
from unittest.mock import patch,MagicMock
from fastapi import HTTPException
import terraces_api as api
from terraces_images import sanitise_photo,UnsafeImage

def header(major=b'heic',compatible=b'heic'):
    return (20).to_bytes(4,'big')+b'ftyp'+major+b'\0'*4+compatible

class RequestDiagnosticTests(unittest.TestCase):
    def snapshot(self,data,content_type='image/heif',reference=None,guard='signature_or_major_brand'):
        error=api.image_rejection('unsupported_image_encoding');error.image_guard=guard
        reference=reference or hashlib.sha256(data).hexdigest()
        with patch.dict('os.environ',{'TERRACES_REQUEST_DIAGNOSTIC_SHA256':reference,'TERRACES_MODERATOR_USER_ID':'1'}),patch('terraces_api.logging.getLogger') as logger:
            api.record_image_rejection(data,content_type,error,1)
            args=logger.return_value.warning.call_args.args
            return json.loads(args[1]),args

    def test_non_founder_or_missing_moderator_never_logs(self):
        for moderator,actor in [('1',2),('',1),('invalid',1),('1',None),('1',True)]:
            with patch.dict('os.environ',{'TERRACES_REQUEST_DIAGNOSTIC_SHA256':'a'*64,'TERRACES_MODERATOR_USER_ID':moderator}),patch('terraces_api.logging.getLogger') as logger:
                api.record_image_rejection(b'body','image/heif',api.image_rejection('unsupported_image_encoding'),actor)
                logger.assert_not_called()

    def test_default_off_and_invalid_reference_emit_nothing(self):
        for value in ('','not-a-hash','a'*63,'g'*64,'"'+'a'*64+'"','a'*64+'\n'):
            with patch.dict('os.environ',{'TERRACES_REQUEST_DIAGNOSTIC_SHA256':value,'TERRACES_MODERATOR_USER_ID':'1'}),patch('terraces_api.logging.getLogger') as logger:
                api.record_image_rejection(b'private','secret',api.image_rejection('unsupported_image_encoding'),1)
                logger.assert_not_called()

    def test_only_allowlisted_fields_no_private_header_bytes_or_digest(self):
        data=b'private-image-material';digest=hashlib.sha256(data).hexdigest()
        record,args=self.snapshot(data,'image/heif; filename=private; token=private')
        self.assertEqual(set(record),{'request_content_type','file_mime_classification','file_byte_length','image_signature_classification','matches_known_original','rejection_category','rejecting_guard'})
        self.assertTrue(record['matches_known_original']);self.assertEqual(record['request_content_type'],'image/heif')
        self.assertNotIn('private',json.dumps(args));self.assertNotIn(digest,json.dumps(args))
        record,_=self.snapshot(data,'secret-header',reference='a'*64,guard='private')
        self.assertFalse(record['matches_known_original']);self.assertEqual(record['request_content_type'],'other');self.assertEqual(record['rejecting_guard'],'unavailable')

    def test_signature_and_actual_mime_classifications(self):
        cases=[(b'\xff\xd8\xff','jpeg','image/jpeg'),(b'\x89PNG\r\n\x1a\n','png','image/png'),(header(),'ftyp_heic','image/heic'),(header(b'mif1'),'ftyp_mif1','image/heif'),(header(b'avif',b'avif'),'ftyp_avif','unknown'),(header(b'xxxx'),'ftyp_other','unknown'),(b'--private\r\n','multipart_prefix','unknown'),(b'','empty','unknown')]
        for data,signature,mime in cases:
            with self.subTest(signature=signature):
                record,_=self.snapshot(bytearray(data))
                self.assertEqual(record['image_signature_classification'],signature);self.assertEqual(record['file_mime_classification'],mime)

    def test_exact_unsupported_guards(self):
        for data,expected in [(b'bad','signature_or_major_brand'),(header(b'mif1',b'avif'),'heif_compatible_codec')]:
            with self.assertRaises(UnsafeImage) as caught:sanitise_photo(data)
            self.assertEqual(caught.exception.guard,expected);self.assertEqual(caught.exception.code,'unsupported_image_encoding')
        with patch('terraces_images.Image.open') as opened:
            source=MagicMock();source.format='OTHER';opened.return_value.__enter__.return_value=source
            with self.assertRaises(UnsafeImage) as caught:sanitise_photo(b'\xff\xd8\xffsynthetic')
        self.assertEqual(caught.exception.guard,'decoded_format')

    def test_worker_guard_is_retained_privately_and_validated(self):
        for guard in (*api.IMAGE_REJECTION_GUARDS,'private',[]):
            payload=json.dumps({'error_code':'unsupported_image_encoding','guard':guard}).encode()
            with patch('terraces_api.subprocess.run',return_value=subprocess.CompletedProcess([],2,payload,b'private')):
                with self.assertRaises(HTTPException) as caught:api.decode(b'synthetic')
            error=caught.exception
            self.assertEqual(error.detail,{'code':'unsupported_image_encoding','message':'Photograph could not be safely processed'})
            self.assertEqual(error.image_guard,guard if isinstance(guard,str) and guard in api.IMAGE_REJECTION_GUARDS else None)

    def test_actual_worker_propagates_predecode_guards(self):
        for data,guard in [(b'bad','signature_or_major_brand'),(header(b'mif1',b'avif'),'heif_compatible_codec')]:
            with self.assertRaises(HTTPException) as caught:api.decode(data)
            self.assertEqual(caught.exception.image_guard,guard)

    def test_no_diagnostic_for_other_http_validation(self):
        for detail in ('private',{'code':'private'},{'code':[]}):
            with patch.dict('os.environ',{'TERRACES_REQUEST_DIAGNOSTIC_SHA256':'a'*64,'TERRACES_MODERATOR_USER_ID':'1'}),patch('terraces_api.logging.getLogger') as logger:
                api.record_image_rejection(b'body','image/heif',HTTPException(422,detail),1);logger.assert_not_called()

class RequestDiagnosticRouteTests(unittest.TestCase):
    def setUp(self):
        from backend.tests.test_terraces_api import PhotoApiTests
        PhotoApiTests.setUp(self)
    def tearDown(self):
        from backend.tests.test_terraces_api import PhotoApiTests
        PhotoApiTests.tearDown(self)
    def upload(self,data):
        from backend.tests.test_terraces_api import PhotoApiTests
        def request(body):
            result=PhotoApiTests.request(self,body)
            result.scope['headers']=[(b'content-type',getattr(self,'content_type','image/heif').encode())]
            return result
        self.request=request
        return PhotoApiTests.upload(self,data)

    def test_rejection_logs_once_without_creating_photo_or_leaking_to_response(self):
        data=header();error=api.image_rejection('unsupported_image_encoding');error.image_guard='signature_or_major_brand'
        with patch.dict('os.environ',{'TERRACES_REQUEST_DIAGNOSTIC_SHA256':hashlib.sha256(data).hexdigest(),'TERRACES_MODERATOR_USER_ID':str(self.owner.user_id)}),patch('terraces_api.decode',side_effect=error) as decode,patch('terraces_api.logging.getLogger') as logger:
            with self.assertRaises(HTTPException) as caught:self.upload(data)
            logger.return_value.warning.assert_called_once();record=json.loads(logger.return_value.warning.call_args.args[1])
            self.assertTrue(record['matches_known_original']);self.assertEqual(record['rejecting_guard'],'signature_or_major_brand')
            self.assertEqual(decode.call_args.args[0],data);self.assertNotIn('guard',caught.exception.detail)
        self.assertEqual(self.storage.objects,{})

    def test_jpeg_success_has_no_diagnostic_even_enabled(self):
        from backend.tests.test_terraces_api import PhotoApiTests
        data=PhotoApiTests.encoded(self)
        with patch.dict('os.environ',{'TERRACES_REQUEST_DIAGNOSTIC_SHA256':hashlib.sha256(data).hexdigest(),'TERRACES_MODERATOR_USER_ID':str(self.owner.user_id)}),patch('terraces_api.logging.getLogger') as logger:
            self.assertEqual(self.upload(data)['status'],'PENDING');logger.assert_not_called()
        self.assertEqual(len(self.storage.objects),2)

    def test_multipart_body_rejected_and_classified_without_private_fields(self):
        data=b'--synthetic\r\nContent-Disposition: form-data; name="file"; filename="private"\r\n\r\ninvalid\r\n--synthetic--'
        self.content_type='multipart/form-data; boundary=synthetic'
        with patch.dict('os.environ',{'TERRACES_REQUEST_DIAGNOSTIC_SHA256':hashlib.sha256(data).hexdigest(),'TERRACES_MODERATOR_USER_ID':str(self.owner.user_id)}),patch('terraces_api.logging.getLogger') as logger:
            with self.assertRaises(HTTPException) as caught:self.upload(data)
            self.assertEqual(caught.exception.status_code,422)
            record=json.loads(logger.return_value.warning.call_args.args[1])
            self.assertEqual(record['image_signature_classification'],'multipart_prefix')
            self.assertEqual(record['request_content_type'],'multipart/form-data')
            self.assertEqual(record['rejecting_guard'],'signature_or_major_brand')
            self.assertTrue(record['matches_known_original']);self.assertNotIn('private',json.dumps(record))
        self.assertEqual(self.storage.objects,{})

    def test_raw_heif_success_preserves_body_and_sanitisation(self):
        from backend.tests.test_terraces_images import encoded
        from models import TerracePhoto
        from io import BytesIO
        from PIL import Image
        data=encoded('HEIF');self.content_type='image/heif'
        with patch.dict('os.environ',{'TERRACES_REQUEST_DIAGNOSTIC_SHA256':hashlib.sha256(data).hexdigest(),'TERRACES_MODERATOR_USER_ID':str(self.owner.user_id)}),patch('terraces_api.logging.getLogger') as logger:
            self.assertEqual(self.upload(data)['status'],'PENDING');logger.assert_not_called()
        self.assertEqual(self.db.query(TerracePhoto).one().source_sha256,hashlib.sha256(data).hexdigest())
        for contents in self.storage.objects.values():
            with Image.open(BytesIO(contents)) as image:
                self.assertEqual(image.format,'JPEG');self.assertFalse(image.getexif())
