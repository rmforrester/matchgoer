import tempfile
import unittest
from pathlib import Path

from audit_coordinates import audit_missing_venues, scopes_from_cohort_report
from ingestion.coordinates import CoordinateResult


class _Enricher:
    def __init__(self):
        self.calls = []

    def enrich(self, venue, strict_uniqueness=False):
        self.calls.append((venue["provider_venue_id"], strict_uniqueness))
        return CoordinateResult(51.0, -1.0, "nominatim", 1)


class CoordinateAuditTests(unittest.TestCase):
    def test_provider_id_skip_null_process_and_resume(self):
        venues = {
            10: {"provider_venue_id": 10, "name": "Existing"},
            20: {"provider_venue_id": 20, "name": "Missing"},
            30: {"provider_venue_id": 30, "name": "Resumed"},
        }
        hosted = {10: (51.5, -0.1), 20: (None, None), 30: (None, None)}
        checkpoint = {"30": {"status": "unresolved", "errors": []}}
        enricher = _Enricher()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "custom-checkpoint.json"
            states, processed = audit_missing_venues(venues, hosted, checkpoint, path, enricher)
            self.assertEqual(states, {10: "database", 20: "geocoded", 30: "unresolved"})
            self.assertEqual(processed, 1)
            self.assertEqual(enricher.calls, [(20, True)])
            self.assertTrue(path.exists())
            second = _Enricher()
            states, processed = audit_missing_venues(venues, hosted, checkpoint, path, second)
            self.assertEqual(processed, 0)
            self.assertEqual(second.calls, [])

    def test_custom_cohort_report_supplies_exact_league_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cohort.json"
            path.write_text(
                '{"summary":{"safe":[{"country":"Greece","league":"Super League 1","league_id":197}],"partial":[{"country":"Wales","league":"Premier League","league_id":110}]}}',
                encoding="utf-8",
            )
            scopes = scopes_from_cohort_report(path, 2026)
            self.assertEqual([scope.league_id for scope in scopes], [197, 110])

    def test_audit_module_has_no_database_write_api(self):
        import audit_coordinates
        source = Path(audit_coordinates.__file__).read_text(encoding="utf-8")
        self.assertNotIn("write_import(", source)
        self.assertNotIn("engine.begin(", source)
        self.assertNotIn("from sqlalchemy import insert", source)
        self.assertNotIn("from sqlalchemy import update", source)
        self.assertNotIn("from sqlalchemy import delete", source)


if __name__ == "__main__":
    unittest.main()
