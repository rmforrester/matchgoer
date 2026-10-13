import unittest
from contextlib import nullcontext
from io import StringIO
from unittest.mock import patch,Mock
from terraces_cleanup import main
from terraces_storage import StorageUnavailable

class CleanupCommandTests(unittest.TestCase):
    def test_explicit_confirmation_required_before_database_access(self):
        with patch('database.SessionLocal') as session,patch('sys.stderr',new_callable=StringIO):
            for args in ([],['--execute'],['--confirm-private-cleanup']):
                with self.assertRaises(SystemExit) as error:main(args)
                self.assertEqual(error.exception.code,2)
            session.assert_not_called()
    def test_limit_is_bounded_before_database_access(self):
        with patch('database.SessionLocal') as session,patch('sys.stderr',new_callable=StringIO):
            for value in ('0','501'):
                with self.assertRaises(SystemExit):main(['--execute','--confirm-private-cleanup','--limit',value])
            session.assert_not_called()
    def execute(self,result=None,error=None):
        db=Mock()
        with patch('database.SessionLocal',return_value=nullcontext(db)),patch('terraces_service.cleanup',return_value=result,side_effect=error) as cleanup,patch('sys.stdout',new_callable=StringIO),patch('sys.stderr',new_callable=StringIO) as stderr:
            code=main(['--execute','--confirm-private-cleanup','--limit','25'])
            if error is None:self.assertEqual(cleanup.call_args.kwargs['limit'],25)
            return code,stderr.getvalue()
    def test_clean_and_repeated_empty_run_exit_success(self):
        self.assertEqual(self.execute({'cleaned':3,'retry_pending':0})[0],0)
        self.assertEqual(self.execute({'cleaned':0,'retry_pending':0})[0],0)
    def test_retry_failure_exits_nonzero(self):
        self.assertEqual(self.execute({'cleaned':1,'retry_pending':2})[0],1)
    def test_storage_and_database_errors_do_not_log_private_details(self):
        from sqlalchemy.exc import DBAPIError
        for error in (StorageUnavailable('private detail'),DBAPIError('private SQL',{},Exception('private detail'))):
            code,message=self.execute(error=error)
            self.assertEqual(code,1);self.assertNotIn('private',message)
