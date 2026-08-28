from __future__ import annotations

import copy
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine, text

from apply_english_know_batch2 import require_mode, require_scope
from english_know_batch2_population import (
    APPROVED_ARTIFACT,
    EXPECTED_COUNTS,
    EXPECTED_SHA256,
    candidate_state,
    dry_run,
    execute_rollback,
    execute_write,
    load_pack,
    validate_pack,
)
from know_population import (
    dry_run as generic_dry_run,
    execute_rollback as generic_execute_rollback,
    execute_write as generic_execute_write,
    load_candidate,
)


class ArtifactGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pack, cls.digest = load_pack()

    def test_approved_artifact_hash_version_and_counts(self):
        self.assertEqual(self.digest, EXPECTED_SHA256)
        self.assertEqual(len(self.pack["clubs"]), 25)
        self.assertEqual({name: len(self.pack[name]) for name in EXPECTED_COUNTS}, EXPECTED_COUNTS)

    def test_real_operation_rejects_arbitrary_path(self):
        with self.assertRaisesRegex(RuntimeError, "approved artifact path"):
            load_pack(Path(__file__))

    def test_wrong_hash_and_changed_bytes_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "candidate.json"
            path.write_bytes(APPROVED_ARTIFACT.read_bytes() + b" ")
            with self.assertRaisesRegex(RuntimeError, "artifact hash mismatch"):
                load_pack(path, test_only=True, expected_sha256=EXPECTED_SHA256)

    def _structural_failure(self, change, message):
        candidate = copy.deepcopy(self.pack)
        change(candidate)
        with self.assertRaisesRegex(RuntimeError, message):
            validate_pack(candidate)

    def test_unexpected_extra_and_missing_records_fail(self):
        self._structural_failure(lambda pack: pack["venue_guide_facts"].append(copy.deepcopy(pack["venue_guide_facts"][0])), "record count")
        self._structural_failure(lambda pack: pack["pre_match_spots"].pop(), "record count")

    def test_duplicate_topic_and_spot_fail(self):
        def duplicate_fact(pack):
            pack["venue_guide_facts"][1]["club_venue_id"] = pack["venue_guide_facts"][0]["club_venue_id"]
            pack["venue_guide_facts"][1]["topic"] = pack["venue_guide_facts"][0]["topic"]
            pack["venue_guide_facts"][1]["identity_sha256"] = self._identity(pack["venue_guide_facts"][1])
        def duplicate_spot(pack):
            pack["pre_match_spots"][1]["club_venue_id"] = pack["pre_match_spots"][0]["club_venue_id"]
            pack["pre_match_spots"][1]["display_name"] = pack["pre_match_spots"][0]["display_name"]
            pack["pre_match_spots"][1]["identity_sha256"] = self._identity(pack["pre_match_spots"][1])
        self._structural_failure(duplicate_fact, "duplicate guide topic")
        self._structural_failure(duplicate_spot, "duplicate pre-match spot")

    def test_low_confidence_research_status_and_missing_maps_fail(self):
        def low(pack):
            pack["pre_match_spots"][0]["confidence"] = "LOW"
            pack["pre_match_spots"][0]["identity_sha256"] = self._identity(pack["pre_match_spots"][0])
        def unresolved(pack):
            pack["venue_guide_facts"][0]["status"] = "RESEARCH_REQUIRED"
            pack["venue_guide_facts"][0]["identity_sha256"] = self._identity(pack["venue_guide_facts"][0])
        def no_maps(pack):
            pack["pre_match_spots"][0]["maps_destination"] = ""
            pack["pre_match_spots"][0]["identity_sha256"] = self._identity(pack["pre_match_spots"][0])
        self._structural_failure(low, "unpublishable")
        self._structural_failure(unresolved, "unpublishable")
        self._structural_failure(no_maps, "unpublishable")

    def test_orphan_evidence_and_wrong_owner_fail(self):
        def orphan(pack):
            pack["pre_match_spot_evidence"][0]["spot_identity_sha256"] = "0" * 64
            pack["pre_match_spot_evidence"][0]["identity_sha256"] = self._identity(pack["pre_match_spot_evidence"][0])
        def owner(pack):
            pack["venue_guide_facts"][0]["club_venue_id"] = 999999
            pack["venue_guide_facts"][0]["identity_sha256"] = self._identity(pack["venue_guide_facts"][0])
        self._structural_failure(orphan, "orphan")
        self._structural_failure(owner, "unsupported content owner")

    def test_write_authorization_and_remote_intent_gates(self):
        self.assertFalse(require_mode(False, False))
        for flags in ((True, False), (False, True)):
            with self.assertRaisesRegex(RuntimeError, "both"):
                require_mode(*flags)
        self.assertTrue(require_mode(True, True))
        with self.assertRaisesRegex(RuntimeError, "allow-remote-audit"):
            require_scope("postgresql://u:p@example.test/db", False, False, False)
        with self.assertRaisesRegex(RuntimeError, "allow-remote-write"):
            require_scope("postgresql://u:p@example.test/db", True, False, False)

    @staticmethod
    def _identity(row):
        value = dict(row)
        value.pop("identity_sha256", None)
        payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest().upper()


@unittest.skipUnless(os.environ.get("MATCHGOER_TEST_DATABASE_URL"), "disposable PostgreSQL URL not supplied")
class PostgreSQLLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.url = os.environ["MATCHGOER_TEST_DATABASE_URL"]
        cls.engine = create_engine(cls.url)
        cls.pack, _ = load_pack()
        cls.generic_candidate = load_candidate(
            APPROVED_ARTIFACT,
            expected_sha256=EXPECTED_SHA256,
            expected_version=cls.pack["artifact_version"],
        )

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def setUp(self):
        self._reset_database()

    def _reset_database(self):
        schema = """
        DROP SCHEMA public CASCADE; CREATE SCHEMA public;
        CREATE TABLE venues(venue_id integer PRIMARY KEY,name text);
        CREATE TABLE teams(team_id integer PRIMARY KEY,team_name text,venue_id integer REFERENCES venues);
        CREATE TABLE club_venues(
          club_venue_id bigint PRIMARY KEY,team_id integer NOT NULL REFERENCES teams,venue_id integer NOT NULL REFERENCES venues,
          relationship_type varchar(30) NOT NULL,status varchar(20) NOT NULL,valid_from date,valid_until date);
        CREATE TABLE venue_guide_facts(
          fact_id bigserial PRIMARY KEY,venue_id integer REFERENCES venues,club_venue_id bigint REFERENCES club_venues,
          section varchar(30) NOT NULL,topic varchar(80) NOT NULL,content text NOT NULL,source_type varchar(30) NOT NULL,
          source_label varchar(160),source_url text,reviewed_at date,confidence varchar(10) NOT NULL,status varchar(20) NOT NULL,
          review_after date,expires_at date,display_order integer NOT NULL);
        CREATE TABLE pre_match_spots(
          pre_match_spot_id bigserial PRIMARY KEY,club_venue_id bigint NOT NULL REFERENCES club_venues,display_name varchar(160) NOT NULL,
          classification varchar(30) NOT NULL,audience varchar(10) NOT NULL,supporting_line varchar(180) NOT NULL,
          maps_destination varchar(300) NOT NULL,confidence varchar(10) NOT NULL,status varchar(20) NOT NULL,business_status varchar(20) NOT NULL,
          reviewed_at date,review_after date,display_order integer NOT NULL,approved_at timestamptz,approved_by varchar(160));
        CREATE TABLE pre_match_spot_evidence(
          evidence_id bigserial PRIMARY KEY,pre_match_spot_id bigint NOT NULL REFERENCES pre_match_spots ON DELETE CASCADE,
          source_type varchar(40) NOT NULL,source_url text,source_date date,disposition varchar(20) NOT NULL,evidence_note varchar(500) NOT NULL,
          review_status varchar(20) NOT NULL);
        """
        with self.engine.begin() as connection:
            connection.execute(text(schema))
            all_clubs = list(self.pack["clubs"])
            batch1 = [(33, 1, 556), (42, 10, 494), (1333, 48, 12456), (1359, 74, 551),
                      (4692, 135, 3541), (7656, 174, 5523), (8657, 225, 6187), (8659, 226, 6189)]
            venues = {club["venue_id"] for club in all_clubs} | {venue for _, _, venue in batch1} | {22950}
            for venue in venues:
                connection.execute(text("INSERT INTO venues(venue_id,name) VALUES (:id,:name)"), {"id": venue, "name": f"Venue {venue}"})
            for club in all_clubs:
                connection.execute(text("INSERT INTO teams(team_id,team_name,venue_id) VALUES (:id,:name,:venue)"), {"id": club["team_id"], "name": club["club_name"], "venue": club["venue_id"]})
                connection.execute(text("INSERT INTO club_venues VALUES (:cv,:team,:venue,'HOME','CURRENT',NULL,NULL)"), {"cv": club["club_venue_id"], "team": club["team_id"], "venue": club["venue_id"]})
            for team_id, club_venue_id, venue_id in batch1:
                connection.execute(text("INSERT INTO teams(team_id,team_name,venue_id) VALUES (:id,:name,:venue) ON CONFLICT DO NOTHING"), {"id": team_id, "name": f"Batch1 {team_id}", "venue": venue_id})
                connection.execute(text("INSERT INTO club_venues VALUES (:cv,:team,:venue,'HOME','CURRENT',NULL,NULL) ON CONFLICT DO NOTHING"), {"cv": club_venue_id, "team": team_id, "venue": venue_id})
                connection.execute(text("INSERT INTO venue_guide_facts(club_venue_id,section,topic,content,source_type,confidence,status,display_order) VALUES (:cv,'tickets_entry',:topic,'Batch 1 marker','official','high','current',1)"), {"cv": club_venue_id, "topic": f"batch1_{team_id}"})
            for index in range(11):
                connection.execute(text("INSERT INTO venue_guide_facts(venue_id,section,topic,content,source_type,confidence,status,display_order) VALUES (22950,'at_ground',:topic,'Hutnik marker','official','high','current',:n)"), {"topic": f"hutnik_{index}", "n": index})

    def _snapshot(self):
        with self.engine.connect() as connection:
            return {
                table: [tuple(row) for row in connection.execute(text(f'SELECT * FROM {table} ORDER BY 1')).all()]
                for table in ("venues", "teams", "club_venues", "venue_guide_facts", "pre_match_spots", "pre_match_spot_evidence")
            }

    def test_complete_write_idempotency_protection_and_rollback_lifecycle(self):
        before = self._snapshot()
        first = dry_run(self.url, self.pack)
        self.assertEqual(first["candidate_state"], "ABSENT")
        self.assertEqual(first["insert"], EXPECTED_COUNTS)
        self.assertEqual(first["total_proposed_mutations"], 78)
        write = execute_write(self.url, self.pack)
        self.assertEqual(write["delta"], {"club_venues": 0, **EXPECTED_COUNTS})
        with self.engine.connect() as connection:
            self.assertEqual(candidate_state(connection, self.pack), "EXACTLY_PRESENT")
        second = dry_run(self.url, self.pack)
        self.assertEqual(second["candidate_state"], "EXACTLY_PRESENT")
        self.assertEqual(second["total_proposed_mutations"], 0)
        self.assertEqual(second["safe_existing"], EXPECTED_COUNTS)
        with self.engine.begin() as connection:
            spot_id = connection.execute(text("SELECT pre_match_spot_id FROM pre_match_spots ORDER BY 1 LIMIT 1")).scalar_one()
            extra = connection.execute(text("INSERT INTO pre_match_spot_evidence(pre_match_spot_id,source_type,source_url,disposition,evidence_note,review_status) VALUES (:id,'EDITORIAL_RESEARCH','https://example.invalid/later','SUPPORTS','Later protected evidence','PENDING') RETURNING evidence_id"), {"id": spot_id}).scalar_one()
        with self.assertRaisesRegex(RuntimeError, "drifted"):
            execute_rollback(self.url, self.pack)
        with self.engine.begin() as connection:
            connection.execute(text("DELETE FROM pre_match_spot_evidence WHERE evidence_id=:id"), {"id": extra})
        rollback = execute_rollback(self.url, self.pack)
        self.assertEqual(rollback["candidate_state"], "ABSENT")
        self.assertEqual(self._snapshot(), before)

    def test_generic_publisher_matches_existing_candidate_exact_state_lifecycle(self):
        before = self._snapshot()
        first = generic_dry_run(self.url, self.generic_candidate)
        self.assertEqual(first["candidate_state"], "ABSENT")
        self.assertEqual(first["insert"], EXPECTED_COUNTS)
        write = generic_execute_write(self.url, self.generic_candidate)
        self.assertEqual(write["delta"], {"club_venues": 0, **EXPECTED_COUNTS})
        second = generic_dry_run(self.url, self.generic_candidate)
        self.assertEqual(second["candidate_state"], "EXACTLY_PRESENT")
        self.assertEqual(second["total_proposed_mutations"], 0)
        rollback = generic_execute_rollback(self.url, self.generic_candidate)
        self.assertEqual(rollback["candidate_state"], "ABSENT")
        self.assertEqual(self._snapshot(), before)

    def test_relationship_and_collision_fail_closed_cases(self):
        cases = (
            ("missing relationship", "DELETE FROM club_venues WHERE club_venue_id=:id", "identity mismatch"),
            ("wrong identity", "UPDATE club_venues SET venue_id=(SELECT venue_id FROM venues WHERE venue_id<>club_venues.venue_id LIMIT 1) WHERE club_venue_id=:id", "identity mismatch"),
            ("wrong team", "UPDATE club_venues SET team_id=(SELECT team_id FROM teams WHERE team_id<>club_venues.team_id LIMIT 1) WHERE club_venue_id=:id", "identity mismatch"),
            ("non-current", "UPDATE club_venues SET status='HISTORICAL' WHERE club_venue_id=:id", "non-current"),
            ("non-home", "UPDATE club_venues SET relationship_type='GROUND_SHARE' WHERE club_venue_id=:id", "non-current"),
            ("future", "UPDATE club_venues SET valid_from=CURRENT_DATE+1 WHERE club_venue_id=:id", "non-current"),
            ("expired", "UPDATE club_venues SET valid_until=CURRENT_DATE-1 WHERE club_venue_id=:id", "non-current"),
            ("ambiguous", "INSERT INTO club_venues(club_venue_id,team_id,venue_id,relationship_type,status) SELECT 9999,team_id,(SELECT venue_id FROM venues WHERE venue_id<>club_venues.venue_id LIMIT 1),'HOME','CURRENT' FROM club_venues WHERE club_venue_id=:id", "ambiguous"),
            ("conflict", "INSERT INTO venue_guide_facts(club_venue_id,section,topic,content,source_type,confidence,status,display_order) VALUES (:id,'at_ground','conflict','conflict','official','high','current',1)", "conflicting content"),
        )
        club_venue_id = self.pack["clubs"][0]["club_venue_id"]
        for name, statement, message in cases:
            with self.subTest(name=name):
                self._reset_database()
                with self.engine.begin() as connection:
                    connection.execute(text(statement), {"id": club_venue_id})
                with self.assertRaisesRegex(RuntimeError, message):
                    dry_run(self.url, self.pack)


if __name__ == "__main__":
    unittest.main()
