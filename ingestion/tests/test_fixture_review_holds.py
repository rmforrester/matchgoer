import copy
import unittest
from unittest.mock import patch
from test_fixture_reconciliation import candidate, provider
import refresh_fixture_states as refresh

class ReviewHoldTests(unittest.TestCase):
    def test_exact_fourteen_and_metadata(self):
        self.assertEqual(len(refresh.REVIEW_HOLDS),14)
        self.assertEqual(len(set(refresh.REVIEW_HOLDS)),14)
        for fid,hold in refresh.REVIEW_HOLDS.items():
            self.assertEqual(fid,hold['fixture_id'])
            self.assertTrue(hold['reason']);self.assertTrue(hold['evidence'])
            self.assertEqual(hold['review_status'],'PENDING_MANUAL_REVIEW')
    def test_all_fourteen_excluded_no_partial_updates(self):
        for fid in refresh.REVIEW_HOLDS:
            row=candidate();row.fixture_id=fid;row.venue_id=3;row.country='France';before=copy.deepcopy(vars(row))
            manifest,values=refresh.classify_candidate(row,[provider(fixture_id=fid)])
            self.assertIsNone(values);self.assertEqual(manifest['classification'],'MANUAL_REVIEW_HOLD')
            self.assertEqual(manifest['proposed_changed_fields'],[]);self.assertEqual(vars(row),before)
            self.assertEqual(manifest['manual_hold'],refresh.REVIEW_HOLDS[fid])
            self.assertEqual(refresh.classify_candidate(row,[provider(fixture_id=fid)])[0],manifest)
    def test_other_french_and_nonfrench_eligible(self):
        for country in ('France','England'):
            row=candidate();row.country=country
            self.assertIsNotNone(refresh.classify_candidate(row,[provider()])[1])
    def test_removal_restores_normal_plan(self):
        fid=next(iter(refresh.REVIEW_HOLDS));row=candidate();row.fixture_id=fid
        with patch.dict(refresh.REVIEW_HOLDS,{},clear=True):
            self.assertIsNotNone(refresh.classify_candidate(row,[provider(fixture_id=fid)])[1])
        self.assertIsNone(refresh.classify_candidate(row,[provider(fixture_id=fid)])[1])
    def test_validation_rejects_injected_held_update(self):
        fid=next(iter(refresh.REVIEW_HOLDS));row=candidate();row.fixture_id=fid
        with patch.dict(refresh.REVIEW_HOLDS,{},clear=True):manifest,values=refresh.classify_candidate(row,[provider(fixture_id=fid)])
        self.assertFalse(refresh.validate_plan([row],[manifest],{fid:values},{})['passed'])
    def test_existing_identity_and_missing_guards(self):
        for rows,label in (([], 'PROVIDER_MISSING'),([provider(home_team_id=9)], 'IDENTITY_MISMATCH')):
            manifest,values=refresh.classify_candidate(candidate(),rows)
            self.assertEqual(manifest['classification'],label);self.assertIsNone(values)
