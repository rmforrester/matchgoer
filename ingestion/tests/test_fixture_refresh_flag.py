import os
import unittest
from unittest.mock import patch
from test_fixture_reconciliation import candidate, provider
import test_fixture_refresh_safety as safety
import refresh_fixture_states as refresh

class ExpandedFlagTests(unittest.TestCase):
    def test_unset_false_true(self):
        for value,expected in ((None,False),('',False),('FALSE',False),('false',False),('TRUE',True),('true',True)):
            with patch.dict(os.environ,{},clear=True):
                if value is not None:os.environ['ENABLE_EXPANDED_FIXTURE_REFRESH']=value
                self.assertEqual(refresh.expanded_refresh_enabled(),expected)
    def test_invalid_fails_before_connections(self):
        for value in ('1','yes','enabled','typo'):
            with patch.dict(os.environ,{'ENABLE_EXPANDED_FIXTURE_REFRESH':value}),patch.object(refresh,'create_engine') as connect,patch('sys.argv',['refresh','--nightly','--write','--confirm-write']):
                with self.assertRaises(SystemExit):refresh.main()
                connect.assert_not_called()
    def test_disabled_no_venue_in_update(self):
        helper=safety.RefreshSafetyTests();row=helper.row();item=provider();item['fixture']['venue']=dict(id=70,name='Example',city='Town')
        m,v=refresh.classify_candidate(row,[item],helper.context(),expanded=False)
        self.assertEqual(m['venue_mapping'],'DISABLED');self.assertNotIn('venue_id',v)
        self.assertTrue(refresh.validate_plan([row],[m],{100:v},{},expanded=False)['passed'])
        self.assertFalse(refresh.validate_plan([row],[m],{100:dict(v,venue_id=7)},{},expanded=False)['passed'])
    def test_enabled_guarded_venue(self):
        helper=safety.RefreshSafetyTests();row=helper.row();item=provider();item['fixture']['venue']=dict(id=70,name='Example',city='Town')
        m,v=refresh.classify_candidate(row,[item],helper.context(),expanded=True);self.assertEqual(v['venue_id'],7)
        item['fixture']['venue']['id']=999;m,v=refresh.classify_candidate(row,[item],helper.context(),expanded=True);self.assertEqual(v['venue_id'],3)
