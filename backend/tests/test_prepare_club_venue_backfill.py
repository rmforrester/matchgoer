import csv
import hashlib
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from prepare_club_venue_backfill import (  # noqa: E402
    APPROVAL_FIELDS,
    AUDIT_VERSION,
    SafetyError,
    Snapshot,
    evaluate,
    identity_hash,
    load_approvals,
)


def approval(team_id=1, venue_id=10):
    row = {"team_id": str(team_id), "team_name": f"Team {team_id}", "venue_id": str(venue_id),
           "venue_name": f"Venue {venue_id}", "relationship_type": "HOME", "status": "CURRENT",
           "audit_version": AUDIT_VERSION, "approval_state": "APPROVED",
           "latest_fixture_season": "2026", "latest_home_fixture_count": "2",
           "latest_fixture_venue_ids": str(venue_id), "all_fixture_venue_ids": str(venue_id)}
    row["identity_sha256"] = identity_hash(row)
    return row


def snapshot():
    return Snapshot(
        teams={1: {"team_id": 1, "team_name": "Team 1", "venue_id": 10}},
        venues={10: {"venue_id": 10, "name": "Venue 10"}},
        fixture_evidence={1: [{"team_id": 1, "season": 2026, "venue_id": 10, "fixture_count": 2}]},
        venue_team_usage={10: {1}}, existing=[], content_counts={})


class EvaluationTests(unittest.TestCase):
    def assert_reason(self, changed, reason, classification=None):
        results, drift = evaluate([approval()], changed)
        self.assertIn(reason, {item["reason"] for item in drift})
        self.assertNotEqual(results[0]["classification"], "INSERT")
        if classification:
            self.assertEqual(results[0]["classification"], classification)

    def test_canonical_insert(self):
        results, drift = evaluate([approval()], snapshot())
        self.assertEqual(results[0]["classification"], "INSERT")
        self.assertEqual(drift, [])

    def test_team_venue_drift_fails_closed(self):
        data = snapshot(); data.teams[1]["venue_id"] = 11
        self.assert_reason(data, "TEAM_VENUE_DRIFT", "REVIEW_REQUIRED")

    def test_fixture_venue_drift_fails_closed(self):
        data = snapshot(); data.fixture_evidence[1][0]["venue_id"] = 11
        self.assert_reason(data, "AMBIGUOUS_OR_DRIFTED_FIXTURE_VENUE", "REVIEW_REQUIRED")

    def test_missing_fixture_venue_fails_closed(self):
        data = snapshot(); data.fixture_evidence[1].append({"team_id": 1, "season": 2026, "venue_id": None, "fixture_count": 1})
        self.assert_reason(data, "MISSING_LATEST_FIXTURE_VENUE", "BLOCKING_CONFLICT")

    def test_existing_conflicting_current_relationship_fails_closed(self):
        data = snapshot(); data.existing.append({"club_venue_id": 1, "team_id": 1, "venue_id": 11, "relationship_type": "HOME", "status": "CURRENT"})
        self.assert_reason(data, "CONFLICTING_CURRENT_RELATIONSHIP", "BLOCKING_CONFLICT")

    def test_shared_venue_conflict_fails_closed(self):
        data = snapshot(); data.venue_team_usage[10].add(999)
        self.assert_reason(data, "NEW_SHARED_VENUE_USAGE", "REVIEW_REQUIRED")

    def test_missing_team_fails_closed(self):
        data = snapshot(); del data.teams[1]
        self.assert_reason(data, "MISSING_TEAM", "BLOCKING_CONFLICT")

    def test_missing_venue_fails_closed(self):
        data = snapshot(); del data.venues[10]
        self.assert_reason(data, "MISSING_VENUE", "BLOCKING_CONFLICT")

    def test_safe_existing_is_not_an_insert(self):
        data = snapshot(); data.existing.append({"club_venue_id": 1, "team_id": 1, "venue_id": 10, "relationship_type": "HOME", "status": "CURRENT"})
        results, drift = evaluate([approval()], data)
        self.assertEqual(results[0]["classification"], "SAFE_EXISTING")
        self.assertEqual(drift, [])


class ApprovalArtifactTests(unittest.TestCase):
    def write_rows(self, rows):
        temp = tempfile.TemporaryDirectory()
        path = Path(temp.name) / "approval.csv"
        with path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=APPROVAL_FIELDS); writer.writeheader(); writer.writerows(rows)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        return temp, path, digest

    def canonical_rows(self):
        return [approval(team_id=index, venue_id=1000 + index) for index in range(1, 251)]

    def assert_rejected(self, rows):
        temp, path, digest = self.write_rows(rows)
        try:
            with self.assertRaises(SafetyError):
                load_approvals(path, digest)
        finally:
            temp.cleanup()

    def test_duplicate_approval_row_is_rejected(self):
        rows = self.canonical_rows(); rows.append(deepcopy(rows[0]))
        self.assert_rejected(rows)

    def test_bromley_is_rejected(self):
        rows = self.canonical_rows(); rows[0] = approval(1832, 511)
        self.assert_rejected(rows)

    def test_worcester_is_rejected(self):
        rows = self.canonical_rows(); rows[0] = approval(9010, 11867)
        self.assert_rejected(rows)


if __name__ == "__main__":
    unittest.main()
