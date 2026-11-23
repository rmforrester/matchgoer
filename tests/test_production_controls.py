"""Offline production controls, with no hosted database or provider transport."""
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from datetime import datetime, timezone
from sqlalchemy import create_engine, text, select

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "backend"), str(ROOT / "ingestion/tests")]
from backend.fixture_integrity import META, VENUES
from backend.fixture_catalogue_recheck import protect_original_bindings, reevaluate, PREIMAGE_CONFLICT


class OriginalBindings(unittest.TestCase):
    def test_five_bonnyrigg_controls_survive_update_then_recheck(self):
        ids = [1578860, 1578893, 1578940, 1578980, 1578997]
        engine = create_engine("sqlite://")
        with engine.begin() as c:
            c.exec_driver_sql("CREATE TABLE fixtures(fixture_id INTEGER PRIMARY KEY, venue_id INTEGER, country TEXT, fixture_date DATETIME, status TEXT, league_id INTEGER, season INTEGER)")
            c.exec_driver_sql("CREATE TABLE venues(venue_id INTEGER PRIMARY KEY, canonical_venue_id INTEGER)")
            c.exec_driver_sql("CREATE TABLE venue_names(venue_id INTEGER,name TEXT,valid_to TEXT)")
            c.exec_driver_sql("CREATE TABLE venue_provider_refs(venue_id INTEGER,provider TEXT,provider_venue_id INTEGER,valid_to TEXT)")
            META.create_all(c)
            # Synthetic conflicting sites; exact production control fixture IDs.
            c.exec_driver_sql("INSERT INTO venues VALUES(100,NULL),(27851,NULL)")
            preimages = {}
            for fid in ids:
                preimages[fid] = {"fixture_id": fid, "venue_id": 100}
                c.execute(text("INSERT INTO fixtures VALUES(:id,27851,'Scotland','2026-12-20 15:00:00','NS',179,2026)"), {"id": fid})
                c.execute(VENUES.insert().values(fixture_id=fid, venue_id=None, identity={},
                          state="UNRESOLVED", actor="AUTOMATED_CANONICAL_CONFLICT", history=[], revision=1))
            blocked = protect_original_bindings(c, preimages, ids)
            self.assertEqual(blocked, set(ids))
            result = reevaluate(c, now=datetime(2026, 11, 23, tzinfo=timezone.utc),
                                preimages=preimages, registry={"scopes": [], "venue_reviews": []})
            self.assertEqual(result["released"], 0)
            rows = list(c.execute(select(VENUES)).mappings())
            self.assertEqual(len(rows), 5)
            for row in rows:
                self.assertEqual(row["state"], "UNRESOLVED")
                self.assertTrue(any(x.get("reason") == PREIMAGE_CONFLICT for x in row["history"]))
            self.assertEqual(protect_original_bindings(c, preimages, ids), set(ids))
        engine.dispose()


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


class BackupBaseline(unittest.TestCase):
    def test_backup_configuration_parser_does_not_require_source_changes(self):
        b = module("backup", ROOT / "ops/postgres_backup/backup.py")
        env = {"BACKUP_R2_ENDPOINT": "https://" + "a" * 32 + ".r2.cloudflarestorage.com",
               "BACKUP_R2_BUCKET": "matchgoer-postgres-backups",
               "BACKUP_R2_ACCESS_KEY_ID": "synthetic", "BACKUP_R2_SECRET_ACCESS_KEY": "synthetic"}
        self.assertEqual(b.config(env, require_recipient=False)["BACKUP_R2_BUCKET"],
                         "matchgoer-postgres-backups")
        with self.assertRaises(b.BackupError):
            b.config({**env, "BACKUP_R2_ENDPOINT": "http://invalid.example"}, require_recipient=False)

    def test_live_three_and_approved_four_are_both_valid(self):
        profiles = json.loads((ROOT / "ops/production_sources.json").read_text())["services"]
        for service, count in [("backup", 3), ("backup-approved-test-orphan", 4)]:
            item = profiles[service]["files"]["identity_monitor.py"]
            m = module(service, ROOT / item["source"])
            approved = m.baseline()
            self.assertEqual(len(approved["acknowledged_orphans"]), count)

    def test_only_expected_test_orphan_added(self):
        approved = json.loads((ROOT / "ops/postgres_backup/identity-continuity-baseline.json").read_text())
        self.assertEqual(approved["acknowledged_orphans"][-1]["identity_key"],
                         "1344c0a548b27908d8e377215d78363f8d9521182aee4ee5117dda1bc42332fe")
        self.assertIn("FOUNDER_TEST_ACCOUNT_MANUAL_AUTH_DELETION",
                      approved["acknowledged_orphans"][-1]["disposition"])

    def test_future_new_orphan_and_duplicate_still_fail(self):
        m = module("approved_identity_monitor", ROOT / "ops/postgres_backup/identity_monitor.py")
        identities = [{"issuer": "synthetic", "subject": "present", "user_id": 1,
                       "account_status": "registered"}]
        approved = {"relationships": [{"identity_key": m.identity_key("synthetic", "present"),
                                       "user_key": m.user_key(1)}], "acknowledged_orphans": []}
        self.assertTrue(m.classify(identities, {"present"}, approved)["passed"])
        self.assertFalse(m.classify(identities * 2, {"present"}, approved)["passed"])
        identities.append({"issuer": "synthetic", "subject": "new-orphan", "user_id": 2,
                           "account_status": "registered"})
        self.assertEqual(m.classify(identities, {"present"}, approved)["new_orphans"], 1)


if __name__ == "__main__":
    unittest.main()
