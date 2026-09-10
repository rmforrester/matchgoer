"""Disposable-PostgreSQL acceptance tests for KNOW v1.

Set MATCHGOER_KNOW_V1_TEST_DATABASE_URL to an isolated local clone. The test
publishes synthetic content and removes it through the production rollback.
"""

from __future__ import annotations

import os
import unittest
from datetime import date, datetime, timezone

from sqlalchemy import create_engine, text

from know_v1_publication import dry_run, identity_sha256, publish, rollback


URL = os.environ.get("MATCHGOER_KNOW_V1_TEST_DATABASE_URL")


def hashed(row):
    row["identity_sha256"] = identity_sha256(row)
    return row


@unittest.skipUnless(URL, "isolated local KNOW v1 PostgreSQL URL not supplied")
class KnowV1DatabaseAcceptance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(URL, pool_pre_ping=True)
        with cls.engine.connect() as connection:
            cls.context = dict(connection.execute(text("""
                SELECT f.fixture_id, f.home_team_id AS team_id, f.venue_id, cv.club_venue_id
                FROM fixtures f JOIN club_venues cv
                  ON cv.team_id=f.home_team_id AND cv.venue_id=f.venue_id
                 AND cv.relationship_type='HOME' AND cv.status='CURRENT'
                ORDER BY f.fixture_id LIMIT 1
            """)).mappings().one())
        fact = hashed({
            "editorial_key": "acceptance:know-v1:synthetic", "team_id": cls.context["team_id"],
            "club_venue_id": None, "venue_id": None, "fixture_id": None, "module": "CLUB",
            "headline": None, "content": "Synthetic database acceptance fact.", "display_order": 1,
            "publication_status": "PUBLISHED", "confidence": "HIGH", "claim_sensitivity": "STANDARD",
            "reviewed_at": "2026-09-10", "review_after": "2026-09-11", "expires_at": None,
            "approved_at": "2026-09-10T12:00:00+00:00", "approved_by": "Automated local acceptance",
        })
        evidence = hashed({
            "fact_editorial_key": fact["editorial_key"], "source_type": "OFFICIAL",
            "source_title": "Synthetic acceptance source", "source_url": "https://example.test/know-v1",
            "source_date": "2026-09-10", "evidence_note": "Synthetic evidence for local acceptance only.",
            "disposition": "SUPPORTS", "review_status": "ACCEPTED", "contributor_user_id": None,
        })
        cls.pack = {"artifact_version": "matchgoer-know-v1-publication",
                    "publication_state": "FROZEN_PUBLICATION_CANDIDATE",
                    "facts": [fact], "evidence": [evidence]}

    @classmethod
    def tearDownClass(cls):
        with cls.engine.begin() as connection:
            connection.execute(text("DELETE FROM know_facts WHERE editorial_key=:key"),
                               {"key": "acceptance:know-v1:synthetic"})
        cls.engine.dispose()

    def test_01_schema_constraints_indexes_and_foreign_keys_exist(self):
        with self.engine.connect() as connection:
            state = connection.execute(text("""
                SELECT pg_is_in_recovery() recovery,
                  (SELECT count(*) FROM pg_constraint WHERE conrelid='know_facts'::regclass) fact_constraints,
                  (SELECT count(*) FROM pg_constraint WHERE conrelid='know_fact_evidence'::regclass) evidence_constraints,
                  (SELECT count(*) FROM pg_indexes WHERE tablename='know_facts') fact_indexes,
                  (SELECT count(*) FROM pg_indexes WHERE tablename='know_fact_evidence') evidence_indexes
            """)).mappings().one()
        self.assertFalse(state.recovery)
        self.assertGreaterEqual(state.fact_constraints, 16)
        self.assertGreaterEqual(state.evidence_constraints, 8)
        self.assertGreaterEqual(state.fact_indexes, 10)
        self.assertGreaterEqual(state.evidence_indexes, 3)

    def test_02_publisher_dry_run_write_exact_set_idempotence_and_rollback(self):
        self.assertEqual(dry_run(URL, self.pack)["state"], "ABSENT")
        first = publish(URL, self.pack)
        self.assertEqual((first["fact_inserts"], first["evidence_inserts"]), (1, 1))
        self.assertEqual(dry_run(URL, self.pack)["state"], "EXACTLY_PRESENT")
        self.assertTrue(publish(URL, self.pack)["idempotent"])
        self.assertEqual(rollback(URL, self.pack), {"facts_deleted": 1, "evidence_deleted_by_cascade": 1})
        self.assertEqual(dry_run(URL, self.pack)["state"], "ABSENT")

    def test_03_database_rejects_cross_subject_and_duplicate_dont_miss(self):
        with self.engine.connect() as connection:
            transaction = connection.begin()
            with self.assertRaises(Exception):
                connection.execute(text("""INSERT INTO know_facts
                    (editorial_key,team_id,venue_id,module,content,publication_status)
                    VALUES ('acceptance:bad-subject',:team,:venue,'GOOD_TO_KNOW','Invalid','PUBLISHED')"""),
                                   {"team": self.context["team_id"], "venue": self.context["venue_id"]})
            transaction.rollback()

        with self.engine.connect() as connection:
            transaction = connection.begin()
            base = {"team": self.context["team_id"]}
            connection.execute(text("""INSERT INTO know_facts
                (editorial_key,team_id,module,content,publication_status)
                VALUES ('acceptance:dont-miss:1',:team,'DONT_MISS','One','PUBLISHED')"""), base)
            with self.assertRaises(Exception):
                connection.execute(text("""INSERT INTO know_facts
                    (editorial_key,team_id,module,content,publication_status)
                    VALUES ('acceptance:dont-miss:2',:team,'DONT_MISS','Two','PUBLISHED')"""), base)
            transaction.rollback()

    def test_04_fixture_api_scopes_fact_and_preserves_btm_contract(self):
        publish(URL, self.pack)
        from main import get_fixture_know
        result = get_fixture_know(self.context["fixture_id"])
        self.assertEqual([row["content"] for row in result["club"]], ["Synthetic database acceptance fact."])
        with self.engine.connect() as connection:
            other = connection.execute(text("""SELECT fixture_id FROM fixtures
                WHERE home_team_id<>:team_id ORDER BY fixture_id LIMIT 1"""), self.context).scalar_one()
        self.assertFalse(any(row.get("content") == "Synthetic database acceptance fact."
                             for rows in get_fixture_know(other).values() if isinstance(rows, list) for row in rows))
        rollback(URL, self.pack)

        with self.engine.connect() as connection:
            btm_fixture = connection.execute(text("""SELECT f.fixture_id,cv.club_venue_id
                FROM fixtures f JOIN club_venues cv ON cv.team_id=f.home_team_id AND cv.venue_id=f.venue_id
                JOIN pre_match_spots p ON p.club_venue_id=cv.club_venue_id
                WHERE cv.relationship_type='HOME' AND cv.status='CURRENT'
                GROUP BY f.fixture_id,cv.club_venue_id ORDER BY f.fixture_id LIMIT 1""")).mappings().first()
            if btm_fixture is None:
                self.skipTest("clone has no fixture-context BTM")
            expected = connection.execute(text("""SELECT pre_match_spot_id,display_order,location_context,maps_destination
                FROM pre_match_spots WHERE club_venue_id=:club_venue_id AND status='CURRENT'
                ORDER BY display_order,pre_match_spot_id"""), btm_fixture).mappings().all()
        actual = get_fixture_know(btm_fixture["fixture_id"])["before_match"]
        self.assertEqual([x["pre_match_spot_id"] for x in actual], [x["pre_match_spot_id"] for x in expected])
        for source, served in zip(expected, actual):
            self.assertEqual(served["location_context"], source["location_context"])
            self.assertEqual(served["directions_url"] is not None, source["maps_destination"] is not None)

    def test_05_new_contribution_defaults_pending_without_hiding_active_history(self):
        with self.engine.connect() as connection:
            transaction = connection.begin()
            pending = connection.execute(text("""INSERT INTO matchday_tips (venue_id,tip)
                VALUES (:venue_id,'Synthetic pending tip') RETURNING status"""), self.context).scalar_one()
            active = connection.execute(text("""INSERT INTO matchday_tips (venue_id,tip,status)
                VALUES (:venue_id,'Synthetic active history','active') RETURNING status"""), self.context).scalar_one()
            self.assertEqual((pending, active), ("pending", "active"))
            transaction.rollback()


if __name__ == "__main__":
    unittest.main()
