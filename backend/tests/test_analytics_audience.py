"""Audience categories use existing resolved identity, never caller-supplied data."""
import unittest
from unittest.mock import patch
from identity import ResolvedIdentity
from main import get_session


class AnalyticsAudienceTests(unittest.TestCase):
    def test_registered_accounts_have_only_the_approved_classification(self):
        for user_id, expected in [(1347, 'internal'), (830, 'internal'), (999, 'external')]:
            with self.subTest(user_id=user_id), patch('main.SessionLocal') as database:
                identity = ResolvedIdentity(user_id=user_id, account_status='registered', is_registered=True, auth_mode='bearer')
                result = get_session(identity)
                self.assertEqual(result['audience_class'], expected)
                self.assertFalse(result['anonymous'])
                database.assert_not_called()

    def test_anonymous_identity_never_inherits_founder_classification(self):
        for user_id in (1347, 830, 999):
            with self.subTest(user_id=user_id), patch('main.SessionLocal'), patch('main._has_meaningful_activity', return_value=False):
                identity = ResolvedIdentity(user_id=user_id, account_status='anonymous', is_registered=False, auth_mode='cookie')
                result = get_session(identity)
                self.assertEqual(result['audience_class'], 'unclassified')
                self.assertTrue(result['anonymous'])
