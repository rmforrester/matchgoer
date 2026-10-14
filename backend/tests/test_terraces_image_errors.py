"""Fixed diagnostic protocol; never return worker text or private image details."""
import json
import subprocess
import unittest
from unittest.mock import patch
from fastapi import HTTPException
import terraces_api as api
from terraces_images import sanitise_photo, UnsafeImage

class ImageErrorTests(unittest.TestCase):
    def rejection(self, result=None, error=None):
        with patch('terraces_api.subprocess.run', return_value=result, side_effect=error):
            with self.assertRaises(HTTPException) as caught: api.decode(b'synthetic')
        self.assertEqual(caught.exception.status_code,422)
        self.assertNotIn('private',json.dumps(caught.exception.detail))
        return caught.exception.detail['code']

    def test_each_fixed_category_is_retained_without_worker_details(self):
        for code in api.IMAGE_ERROR_CODES:
            with self.subTest(code=code):
                result=subprocess.CompletedProcess([],2,json.dumps({'error_code':code,'private':'ignored'}).encode(),b'private credentials')
                self.assertEqual(self.rejection(result),code)

    def test_unknown_malformed_and_large_diagnostics_fail_closed(self):
        for body in (b'', b'invalid', b'[]', b'{"error_code":"private"}', b'{"error_code":[]}', b'x'*257):
            with self.subTest(body_length=len(body)):
                self.assertEqual(self.rejection(subprocess.CompletedProcess([],2,body,b'private')),'image_processing_failed')
        self.assertEqual(self.rejection(subprocess.CompletedProcess([],0,b'not json',b'private')),'image_processing_failed')

    def test_timeout_and_resource_signals(self):
        self.assertEqual(self.rejection(error=subprocess.TimeoutExpired('private',15)),'image_resource_limit')
        for signal in (-9,-24):
            self.assertEqual(self.rejection(subprocess.CompletedProcess([],signal,b'',b'private')),'image_resource_limit')
        self.assertEqual(self.rejection(error=OSError('private')),'image_processing_failed')

    def test_sanitiser_classifies_without_changing_rejection(self):
        for data,code in ((b'not image','unsupported_image_encoding'),(b'','image_validation_failed'),(b'\xff\xd8\xffbad','image_decode_failed')):
            with self.assertRaises(UnsafeImage) as caught:sanitise_photo(data)
            self.assertEqual(caught.exception.code,code)

    def test_worker_emits_only_fixed_categories_without_exception_text(self):
        import runpy
        from pathlib import Path
        from io import BytesIO, StringIO
        from types import SimpleNamespace
        from contextlib import redirect_stdout
        cases=[(UnsafeImage('private',code),code) for code in api.IMAGE_ERROR_CODES]
        cases += [(MemoryError('private'),'image_resource_limit'),(RuntimeError('private'),'image_processing_failed'),(UnsafeImage('private','private'),'image_processing_failed')]
        for error,code in cases:
            with self.subTest(code=code):
                output=StringIO()
                # Protocol-only in-process test; native Linux limits are tested
                # in isolated worker subprocesses, never applied to the suite.
                with patch('sys.platform','win32'),patch('sys.stdin',SimpleNamespace(buffer=BytesIO(b'synthetic'))),redirect_stdout(output),patch('terraces_images.sanitise_photo',side_effect=error):
                    with self.assertRaises(SystemExit) as exit_code:
                        runpy.run_path(str(Path(api.__file__).with_name('terraces_image_worker.py')),run_name='__main__')
                self.assertEqual(exit_code.exception.code,2)
                self.assertEqual(json.loads(output.getvalue()),{'error_code':code})

    def test_actual_worker_preserves_jpeg_png_success_and_fixed_errors(self):
        from io import BytesIO
        from PIL import Image
        for fmt in ('JPEG','PNG'):
            output=BytesIO();Image.new('RGB',(32,20),'green').save(output,format=fmt)
            photo=api.decode(output.getvalue())
            self.assertEqual(photo.display.width,32)
            with Image.open(BytesIO(photo.display.data)) as clean:self.assertFalse(clean.getexif())
        with self.assertRaises(HTTPException) as caught:api.decode(b'not image')
        self.assertEqual(caught.exception.detail['code'],'unsupported_image_encoding')
