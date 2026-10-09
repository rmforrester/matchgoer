import unittest
from unittest.mock import patch
import refresh_fixture_states as r


class ExitOutcomeTests(unittest.TestCase):
    def outcome(self, **changes):
        args = dict(write_requested=True, commit_confirmed=True, expanded=True,
                    incomplete=False, write_error=None, provider_failures=[],
                    validation={"passed": True}, manifest=[])
        args.update(changes)
        return r.execution_outcome(**args)

    def test_complete_success(self):
        self.assertEqual(self.outcome(), (True, 0))

    def test_expected_exclusions_after_commit(self):
        for classification in ("IDENTITY_MISMATCH", "MANUAL_REVIEW_HOLD", "PROVIDER_MISSING",
                               "TERMINAL_CONFLICT_REVIEW", "PROVIDER_STILL_UNRESOLVED"):
            with self.subTest(classification=classification):
                self.assertEqual(self.outcome(incomplete=True, manifest=[{"classification": classification}]), (True, 0))

    def test_unresolved_venue_preserved(self):
        self.assertEqual(self.outcome(incomplete=True, manifest=[{"classification": "NO_CHANGE", "venue_mapping": "UNKNOWN"}]), (True, 0))

    def test_validation_failure(self):
        self.assertEqual(self.outcome(validation={"passed": False}), (False, 1))

    def test_transaction_failures(self):
        for error in ("OperationalError", "CommitError", "PreimageMismatch", "ReconciliationError"):
            with self.subTest(error=error):
                self.assertEqual(self.outcome(commit_confirmed=False, write_error=error), (False, 1))

    def test_unknown_commit(self):
        self.assertEqual(self.outcome(commit_confirmed=False), (False, 1))

    def test_provider_failure(self):
        self.assertEqual(self.outcome(provider_failures=["timeout"]), (False, 1))

    def test_unexpected_records_fail(self):
        for classification in ("PROVIDER_MALFORMED", "PROVIDER_DUPLICATE", "UNRECOGNIZED"):
            self.assertEqual(self.outcome(manifest=[{"classification": classification}]), (False, 1))

    def test_dry_run_original_policy(self):
        for expanded in (True, False):
            for incomplete in (True, False):
                expected = not (expanded and incomplete)
                self.assertEqual(self.outcome(write_requested=False, commit_confirmed=False,
                                             expanded=expanded, incomplete=incomplete), (expected, 0 if expected else 1))

    def test_database_connection_failure_propagates(self):
        with patch.dict(r.os.environ, {"DATABASE_URL": "synthetic", "API_FOOTBALL_KEY": "mock", "ENABLE_EXPANDED_FIXTURE_REFRESH": "true"}), patch("sys.argv", ["refresh", "--nightly"]), patch.object(r, "create_engine", side_effect=RuntimeError("synthetic connection failure")):
            with self.assertRaises(RuntimeError):
                r.main()
