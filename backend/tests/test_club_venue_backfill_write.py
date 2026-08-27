import csv
import hashlib
import os
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from apply_club_venue_backfill import (  # noqa: E402
    EXPECTED_APPROVAL_SHA256,
    audit_on_connection,
    ensure_database_scope,
    execute_write,
    require_write_confirmation,
)
from prepare_club_venue_backfill import APPROVAL_FIELDS, AUDIT_VERSION, SafetyError, identity_hash, load_approvals, query_snapshot, evaluate  # noqa: E402
from rollback_club_venue_backfill import execute_rollback, require_rollback_confirmation  # noqa: E402


def synthetic(team_id, venue_id):
    row = {"team_id": str(team_id), "team_name": f"Team {team_id}", "venue_id": str(venue_id),
           "venue_name": f"Venue {venue_id}", "relationship_type": "HOME", "status": "CURRENT",
           "audit_version": AUDIT_VERSION, "approval_state": "APPROVED", "latest_fixture_season": "2026",
           "latest_home_fixture_count": "1", "latest_fixture_venue_ids": str(venue_id),
           "all_fixture_venue_ids": str(venue_id)}
    row["identity_sha256"] = identity_hash(row)
    return row


class ConfirmationAndArtifactTests(unittest.TestCase):
    def rows(self): return [synthetic(index, 10000 + index) for index in range(1, 251)]

    def write_file(self, rows):
        temp = tempfile.TemporaryDirectory(); path = Path(temp.name) / "approval.csv"
        with path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=APPROVAL_FIELDS); writer.writeheader(); writer.writerows(rows)
        return temp, path, hashlib.sha256(path.read_bytes()).hexdigest()

    def reject(self, rows):
        temp, path, digest = self.write_file(rows)
        try:
            with self.assertRaises(SafetyError): load_approvals(path, digest)
        finally: temp.cleanup()

    def test_01_missing_write_is_rejected(self):
        with self.assertRaisesRegex(SafetyError, "--write"): require_write_confirmation(False, True)

    def test_02_missing_confirm_write_is_rejected(self):
        with self.assertRaisesRegex(SafetyError, "--confirm-write"): require_write_confirmation(True, False)

    def test_03_no_write_flags_selects_dry_run(self): self.assertFalse(require_write_confirmation(False, False))

    def test_04_wrong_approval_hash_is_rejected(self):
        temp, path, _ = self.write_file(self.rows())
        try:
            with self.assertRaises(SafetyError): load_approvals(path, "0" * 64)
        finally: temp.cleanup()

    def test_05_approval_count_must_be_250(self): self.reject(self.rows()[:-1])
    def test_06_bromley_is_rejected(self):
        rows = self.rows(); rows[0] = synthetic(1832, 511); self.reject(rows)
    def test_07_worcester_is_rejected(self):
        rows = self.rows(); rows[0] = synthetic(9010, 11867); self.reject(rows)
    def test_08_duplicate_team_is_rejected(self):
        rows = self.rows(); rows[1] = deepcopy(rows[0]); self.reject(rows)
    def test_09_unexpected_relationship_type_is_rejected(self):
        rows = self.rows(); rows[0]["relationship_type"] = "GROUND_SHARE"; rows[0]["identity_sha256"] = identity_hash(rows[0]); self.reject(rows)
    def test_10_unexpected_status_is_rejected(self):
        rows = self.rows(); rows[0]["status"] = "HISTORICAL"; rows[0]["identity_sha256"] = identity_hash(rows[0]); self.reject(rows)

    def test_11_rollback_requires_both_flags(self):
        for flags in ((False, False), (True, False), (False, True)):
            with self.assertRaises(SafetyError): require_rollback_confirmation(*flags)

    def test_12_remote_intent_is_explicit_and_mode_specific(self):
        remote = "postgresql://user:password@example.test/railway"
        with self.assertRaisesRegex(SafetyError, "--allow-remote-audit"):
            ensure_database_scope(remote, False, False)
        with self.assertRaisesRegex(SafetyError, "--allow-remote-write"):
            ensure_database_scope(remote, False, True)
        self.assertEqual(ensure_database_scope(remote, False, False, True)[1], "remote")


@unittest.skipUnless(os.environ.get("CLUB_VENUE_WRITE_TEST_DATABASE_URL") and os.environ.get("CLUB_VENUE_APPROVAL_FILE"),
                     "disposable local PostgreSQL integration environment not supplied")
class DisposablePostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.url = os.environ["CLUB_VENUE_WRITE_TEST_DATABASE_URL"]
        parsed = make_url(cls.url)
        if parsed.host not in {"localhost", "127.0.0.1", "::1"}: raise RuntimeError("integration tests require local PostgreSQL")
        cls.approvals = load_approvals(Path(os.environ["CLUB_VENUE_APPROVAL_FILE"]), EXPECTED_APPROVAL_SHA256)
        cls.engine = create_engine(cls.url)

    def setUp(self):
        with self.engine.connect() as connection:
            self.assertEqual(connection.execute(text("SELECT count(*) FROM club_venues")).scalar_one(), 0)

    def audit_counts(self):
        with self.engine.connect() as connection:
            snapshot, _ = query_snapshot(connection, self.approvals)
            results, drift = evaluate(self.approvals, snapshot)
        counts = {name: sum(row["classification"] == name for row in results)
                  for name in ("INSERT", "SAFE_EXISTING", "REVIEW_REQUIRED", "BLOCKING_CONFLICT")}
        return counts, drift

    def test_13_full_write_audit_rollback_cycle_and_unrelated_survival(self):
        self.assertEqual(self.audit_counts()[0], {"INSERT": 250, "SAFE_EXISTING": 0, "REVIEW_REQUIRED": 0, "BLOCKING_CONFLICT": 0})
        result = execute_write(self.url, self.approvals)
        self.assertEqual(result["reconciliation"]["inserted"], 250)
        self.assertEqual(self.audit_counts()[0], {"INSERT": 0, "SAFE_EXISTING": 250, "REVIEW_REQUIRED": 0, "BLOCKING_CONFLICT": 0})
        with self.engine.begin() as connection:
            connection.execute(text("INSERT INTO club_venues(team_id,venue_id,relationship_type,status) VALUES (1832,20413,'HOME','DRAFT')"))
        rollback = execute_rollback(self.url, self.approvals)
        self.assertEqual(rollback["deleted"], 250)
        with self.engine.begin() as connection:
            self.assertEqual(connection.execute(text("SELECT count(*) FROM club_venues WHERE team_id=1832 AND status='DRAFT'")).scalar_one(), 1)
            connection.execute(text("DELETE FROM club_venues WHERE team_id=1832 AND venue_id=20413 AND status='DRAFT'"))
        self.assertEqual(self.audit_counts()[0], {"INSERT": 250, "SAFE_EXISTING": 0, "REVIEW_REQUIRED": 0, "BLOCKING_CONFLICT": 0})

    def test_14_prewrite_existing_current_fails_closed(self):
        first = self.approvals[0]
        with self.engine.begin() as connection:
            connection.execute(text("INSERT INTO club_venues(team_id,venue_id,relationship_type,status) VALUES (:t,:v,'HOME','CURRENT')"),
                               {"t": int(first["team_id"]), "v": int(first["venue_id"])})
        try:
            with self.assertRaises(SafetyError): execute_write(self.url, self.approvals)
        finally:
            with self.engine.begin() as connection: connection.execute(text("DELETE FROM club_venues WHERE team_id=:t"), {"t": int(first["team_id"])})

    def test_15_conflicting_relationship_fails_closed(self):
        first = self.approvals[0]
        with self.engine.begin() as connection:
            alternative = connection.execute(text("SELECT venue_id FROM venues WHERE venue_id<>:v ORDER BY venue_id LIMIT 1"), {"v": int(first["venue_id"])}).scalar_one()
            connection.execute(text("INSERT INTO club_venues(team_id,venue_id,relationship_type,status) VALUES (:t,:v,'HOME','CURRENT')"),
                               {"t": int(first["team_id"]), "v": alternative})
        try:
            with self.assertRaises(SafetyError): execute_write(self.url, self.approvals)
        finally:
            with self.engine.begin() as connection: connection.execute(text("DELETE FROM club_venues WHERE team_id=:t"), {"t": int(first["team_id"])})

    def test_16_missing_team_and_venue_fail_closed(self):
        missing_team = deepcopy(self.approvals); missing_team[0]["team_id"] = "999999"
        missing_venue = deepcopy(self.approvals); missing_venue[0]["venue_id"] = "999999"
        for changed in (missing_team, missing_venue):
            with self.assertRaises(SafetyError): execute_write(self.url, changed)
        with self.engine.connect() as connection: self.assertEqual(connection.execute(text("SELECT count(*) FROM club_venues")).scalar_one(), 0)

    def test_17_simulated_insert_failure_commits_zero(self):
        def fail(_connection): raise RuntimeError("simulated insert failure")
        with self.assertRaises(RuntimeError): execute_write(self.url, self.approvals, before_commit=fail)
        with self.engine.connect() as connection: self.assertEqual(connection.execute(text("SELECT count(*) FROM club_venues")).scalar_one(), 0)

    def test_18_reconciliation_mismatch_rolls_back(self):
        def damage(connection): connection.execute(text("DELETE FROM club_venues WHERE club_venue_id=(SELECT min(club_venue_id) FROM club_venues)"))
        with self.assertRaises(SafetyError): execute_write(self.url, self.approvals, after_inserts=damage)
        with self.engine.connect() as connection: self.assertEqual(connection.execute(text("SELECT count(*) FROM club_venues")).scalar_one(), 0)

    def test_19_rollback_refuses_pre_match_spot_child(self):
        execute_write(self.url, self.approvals)
        with self.engine.begin() as connection:
            club_id = connection.execute(text("SELECT min(club_venue_id) FROM club_venues")).scalar_one()
            connection.execute(text("""INSERT INTO pre_match_spots
                (club_venue_id,display_name,classification,audience,supporting_line,maps_destination,confidence,status,business_status,display_order)
                VALUES (:id,'Test','SUPPORTER_SPOT','HOME','Test','Test','HIGH','DRAFT','OPEN',1)"""), {"id": club_id})
        with self.assertRaisesRegex(SafetyError, "protected children"): execute_rollback(self.url, self.approvals)
        with self.engine.begin() as connection: connection.execute(text("DELETE FROM pre_match_spots WHERE club_venue_id=:id"), {"id": club_id})
        execute_rollback(self.url, self.approvals)

    def test_20_rollback_refuses_club_owned_guide_fact(self):
        execute_write(self.url, self.approvals)
        with self.engine.begin() as connection:
            club_id = connection.execute(text("SELECT min(club_venue_id) FROM club_venues")).scalar_one()
            fact_id = connection.execute(text("SELECT min(fact_id) FROM venue_guide_facts WHERE venue_id=22950")).scalar_one()
            connection.execute(text("UPDATE venue_guide_facts SET venue_id=NULL,club_venue_id=:c WHERE fact_id=:f"), {"c": club_id, "f": fact_id})
        with self.assertRaisesRegex(SafetyError, "protected children"): execute_rollback(self.url, self.approvals)
        with self.engine.begin() as connection: connection.execute(text("UPDATE venue_guide_facts SET venue_id=22950,club_venue_id=NULL WHERE fact_id=:f"), {"f": fact_id})
        execute_rollback(self.url, self.approvals)


if __name__ == "__main__": unittest.main()
