from datetime import datetime, timezone
from types import SimpleNamespace
import unittest

from refresh_fixture_states import ALLOWED_FIELDS, classify_candidate, validate_plan


KICKOFF = datetime(2026, 9, 1, 19, 45, tzinfo=timezone.utc)


def candidate(status="NS", home_goals=None, away_goals=None, fixture_date=KICKOFF):
    return SimpleNamespace(
        fixture_id=100, fixture_date=fixture_date, status=status, home_goals=home_goals, away_goals=away_goals,
        league_id=39, season=2026, home_team_id=1, away_team_id=2, home_team="Home", away_team="Away",
    )


def provider(status="FT", home_goals=2, away_goals=1, fixture_date=KICKOFF, **identity):
    values = {"fixture_id": 100, "league_id": 39, "season": 2026, "home_team_id": 1, "away_team_id": 2}
    values.update(identity)
    return {
        "fixture": {"id": values["fixture_id"], "date": fixture_date.isoformat(), "status": {"short": status}},
        "league": {"id": values["league_id"], "season": values["season"]},
        "teams": {"home": {"id": values["home_team_id"]}, "away": {"id": values["away_team_id"]}},
        "goals": {"home": home_goals, "away": away_goals},
    }


class FixtureReconciliationTests(unittest.TestCase):
    def assert_update(self, stored_status, classification="WOULD_UPDATE_TO_FINAL"):
        result, values = classify_candidate(candidate(status=stored_status), [provider()])
        self.assertEqual(result["classification"], classification)
        self.assertEqual(set(values), set(ALLOWED_FIELDS))
        self.assertEqual(values["status"], "FT")

    def test_ns_to_ft(self):
        self.assert_update("NS")

    def test_live_states_to_ft(self):
        for status in ("1H", "HT", "2H"):
            with self.subTest(status=status):
                self.assert_update(status)

    def test_tbd_to_ft(self):
        self.assert_update("TBD")

    def test_pst_to_rescheduled_ft(self):
        moved = KICKOFF.replace(day=8)
        result, values = classify_candidate(candidate(status="PST"), [provider(fixture_date=moved)])
        self.assertEqual(result["classification"], "WOULD_UPDATE_RESCHEDULED")
        self.assertEqual(values["fixture_date"], moved)

    def test_provider_still_unresolved(self):
        result, values = classify_candidate(candidate(), [provider(status="NS", home_goals=None, away_goals=None)])
        self.assertEqual(result["classification"], "PROVIDER_STILL_UNRESOLVED")
        self.assertIsNone(values)

    def test_identity_mismatch_fails_closed(self):
        for field in ("fixture_id", "league_id", "season", "home_team_id", "away_team_id"):
            with self.subTest(field=field):
                result, values = classify_candidate(candidate(), [provider(**{field: 999})])
                self.assertEqual(result["classification"], "IDENTITY_MISMATCH")
                self.assertEqual(result["provider_status"], "FT")
                self.assertIsNone(values)

    def test_provider_missing_and_duplicate_fail_closed(self):
        self.assertEqual(classify_candidate(candidate(), [])[0]["classification"], "PROVIDER_MISSING")
        self.assertEqual(classify_candidate(candidate(), [provider(), provider()])[0]["classification"], "PROVIDER_DUPLICATE")

    def test_final_to_nonfinal_and_terminal_conflicts_require_review(self):
        for status in ("FT", "AET", "PEN", "CANC", "ABD", "AWD", "WO"):
            with self.subTest(status=status):
                result, values = classify_candidate(candidate(status=status, home_goals=2, away_goals=1), [provider(status="NS", home_goals=None, away_goals=None)])
                self.assertEqual(result["classification"], "TERMINAL_CONFLICT_REVIEW")
                self.assertIsNone(values)

    def test_score_and_date_changes_are_explicit(self):
        moved = KICKOFF.replace(hour=20)
        result, values = classify_candidate(candidate(status="2H", home_goals=1, away_goals=1), [provider(away_goals=0, fixture_date=moved)])
        self.assertEqual(result["classification"], "WOULD_UPDATE_RESCHEDULED")
        self.assertEqual(set(result["proposed_changed_fields"]), set(ALLOWED_FIELDS))
        self.assertEqual(values["home_goals"], 2)

    def test_idempotent_rerun(self):
        final = candidate(status="FT", home_goals=2, away_goals=1)
        result, values = classify_candidate(final, [provider()])
        self.assertEqual(result["classification"], "NO_CHANGE")
        self.assertIsNone(values)

        postponed = provider(status="PST", home_goals=None, away_goals=None)
        first_values = classify_candidate(candidate(), [postponed])[1]
        applied = candidate(status=first_values["status"], home_goals=None, away_goals=None)
        result, values = classify_candidate(applied, [postponed])
        self.assertEqual(result["classification"], "PROVIDER_STILL_UNRESOLVED")
        self.assertIsNone(values)

    def test_bounded_validation_and_permitted_fields(self):
        row = candidate()
        manifest, values = classify_candidate(row, [provider()])
        validation = validate_plan([row], [manifest], {row.fixture_id: values}, {(KICKOFF, 1, 2): {row.fixture_id}})
        self.assertTrue(validation["passed"])
        self.assertTrue(validation["idempotent"])
        invalid = dict(values, venue_name="Wrong scope")
        validation = validate_plan([row], [manifest], {row.fixture_id: invalid}, {(KICKOFF, 1, 2): {row.fixture_id}})
        self.assertFalse(validation["passed"])

    def test_duplicate_natural_key_fails_validation(self):
        row = candidate()
        manifest, values = classify_candidate(row, [provider()])
        validation = validate_plan([row], [manifest], {100: values}, {(KICKOFF, 1, 2): {999}})
        self.assertFalse(validation["passed"])


if __name__ == "__main__":
    unittest.main()
