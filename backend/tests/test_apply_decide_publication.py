import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import apply_decide_publication as publisher


def fact(key="team-support", subject="TEAM", owner=1, category="EXCEPTIONAL_SUPPORT"):
    row = {
        "stable_editorial_key": key, "subject": "Subject", "subject_type": subject,
        "team_a_id": None, "team_b_id": None, "venue_id": None, "team_id": None,
        "attribute_key": category, "label": "Support", "explanation": "Approved explanation.",
        "publication_status": "PUBLISHED", "confidence": "HIGH", "lead_priority": "NORMAL",
        "reviewed_at": "2026-09-20T00:00:00+00:00", "reviewed_by": "Editor",
        "evidence_url": "https://example.test/source", "evidence_sources": ["https://example.test/source"],
    }
    if subject == "TEAM": row["team_id"] = owner
    elif subject == "VENUE": row["venue_id"] = owner
    else: row["team_a_id"], row["team_b_id"] = owner
    return row


def candidate(rows=None):
    rows = rows or [fact()]
    return {"schema_version": 1, "catalogue_status": "APPROVED_NOT_YET_PUBLISHED", "fact_count": len(rows), "facts": rows}


class Rows:
    def __init__(self, values): self.values = values
    def mappings(self): return self
    def scalars(self): return self
    def all(self): return self.values
    def scalar_one(self): return self.values[0]


class Transaction:
    def __init__(self): self.is_active=True; self.committed=False; self.rolled_back=False
    def commit(self): self.committed=True; self.is_active=False
    def rollback(self): self.rolled_back=True; self.is_active=False


class FakeConnection:
    def __init__(self):
        self.teams={1,2,3990,4010}; self.venues={10,1620,22806,27806}; self.facts=[]; self.evidence=[]; self.tx=None; self.next_fact=100
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def begin(self): self.tx=Transaction(); return self.tx
    def execute(self, statement, params=None):
        sql=" ".join(str(statement).split()); params=params or {}
        if sql.startswith("SET TRANSACTION"): return Rows([])
        if sql.startswith("SELECT count(*) FROM decision_facts"): return Rows([len(self.facts)])
        if sql.startswith("SELECT count(*) FROM decision_evidence"): return Rows([len(self.evidence)])
        if sql.startswith("SELECT team_id FROM teams"):
            return Rows([value for value in params["ids"] if value in self.teams])
        if sql.startswith("SELECT venue_id FROM venues"):
            return Rows([params["id"]] if params["id"] in self.venues else [])
        if sql.startswith("SELECT * FROM decision_facts"):
            fields=("subject_type","attribute_key","team_a_id","team_b_id","venue_id","team_id")
            return Rows([row for row in self.facts if all(row.get(name)==params.get(name) for name in fields)])
        if sql.startswith("SELECT * FROM decision_evidence"):
            return Rows([row for row in self.evidence if row["source_title"]==params["source_title"]])
        if sql.startswith("INSERT INTO decision_facts"):
            row=dict(params); row["fact_id"]=self.next_fact; self.next_fact+=1; self.facts.append(row); return Rows([row["fact_id"]])
        if sql.startswith("INSERT INTO decision_evidence"):
            self.evidence.append(dict(params)); return Rows([])
        raise AssertionError(sql)


class Engine:
    def __init__(self, connection): self.connection=connection
    def connect(self): return self.connection


class CandidateContractTests(unittest.TestCase):
    def assert_invalid(self, change):
        value=candidate(); change(value)
        with self.assertRaises(publisher.PublicationError): publisher.validate_candidate(value)

    def test_valid_team_fact(self): publisher.validate_candidate(candidate())
    def test_valid_venue_fact(self): publisher.validate_candidate(candidate([fact("venue","VENUE",10,"CLASSIC_GROUND")]))
    def test_valid_rivalry_fact(self): publisher.validate_candidate(candidate([fact("pair","TEAM_PAIR",(1,2),"SIGNIFICANT_RIVALRY")]))
    def test_malformed_identity(self): self.assert_invalid(lambda c: c["facts"][0].update(team_id=None))
    def test_same_team_rivalry(self):
        with self.assertRaises(publisher.PublicationError): publisher.validate_candidate(candidate([fact("pair","TEAM_PAIR",(1,1),"SIGNIFICANT_RIVALRY")]))
    def test_duplicate_stable_key(self):
        one=fact(); two=copy.deepcopy(one)
        with self.assertRaises(publisher.PublicationError): publisher.validate_candidate(candidate([one,two]))
    def test_duplicate_canonical_fact(self):
        one=fact(); two=copy.deepcopy(one); two["stable_editorial_key"]="other"
        with self.assertRaises(publisher.PublicationError): publisher.validate_candidate(candidate([one,two]))
    def test_duplicate_evidence(self):
        value=candidate(); value["facts"][0]["evidence_sources"].append(value["facts"][0]["evidence_sources"][0])
        with self.assertRaises(publisher.PublicationError): publisher.validate_candidate(value)
    def test_hash_match(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"c.json"; p.write_text(json.dumps(candidate()),encoding="utf-8"); expected=hashlib.sha256(p.read_bytes()).hexdigest()
            loaded,actual=publisher.load_candidate(p,expected); self.assertEqual(loaded["fact_count"],1); self.assertEqual(actual,expected.upper())
    def test_hash_mismatch_precedes_validation_and_db(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"c.json"; p.write_text("not json",encoding="utf-8")
            with self.assertRaisesRegex(publisher.PublicationError,"SHA-256"): publisher.load_candidate(p,"0"*64)
    def test_country_and_competition_independent(self):
        source=Path(publisher.__file__).read_text(encoding="utf-8").casefold()
        self.assertNotIn("usa",source); self.assertNotIn("five-country",source); self.assertNotIn("competition",source)


class PreflightTests(unittest.TestCase):
    def test_insert_paths(self):
        connection=FakeConnection(); plan=publisher.preflight(connection,candidate())
        self.assertEqual(plan["operations"]["decision_facts"]["insert"],1); self.assertEqual(plan["operations"]["decision_evidence"]["insert"],1)
    def test_exact_fact_and_evidence_reuse(self):
        connection=FakeConnection(); first=publisher.preflight(connection,candidate()); publisher.apply_candidate(connection,candidate(),first)
        second=publisher.preflight(connection,candidate())
        self.assertEqual(second["operations"]["decision_facts"]["reuse"],1); self.assertEqual(second["operations"]["decision_evidence"]["reuse"],1)
    def test_fact_conflict_rejected(self):
        connection=FakeConnection(); first=publisher.preflight(connection,candidate()); publisher.apply_candidate(connection,candidate(),first); connection.facts[0]["label"]="Different"
        with self.assertRaisesRegex(publisher.PublicationError,"conflicts"): publisher.preflight(connection,candidate())
    def test_evidence_conflict_rejected(self):
        connection=FakeConnection(); first=publisher.preflight(connection,candidate()); publisher.apply_candidate(connection,candidate(),first); connection.evidence[0]["review_status"]="REJECTED"
        with self.assertRaisesRegex(publisher.PublicationError,"conflicts"): publisher.preflight(connection,candidate())
    def test_evidence_stable_key_cannot_belong_to_another_fact(self):
        connection=FakeConnection(); connection.evidence.append({"fact_id":999,"source_title":"team-support","source_url":"https://other.test","evidence_note":"Other","disposition":"SUPPORTS","retrieved_at":None,"reviewed_at":None,"review_status":"ACCEPTED"})
        with self.assertRaisesRegex(publisher.PublicationError,"EVIDENCE_STABLE_KEY_ALREADY_OWNED"): publisher.preflight(connection,candidate())
    def test_missing_team_rejected(self):
        connection=FakeConnection(); connection.teams.clear()
        with self.assertRaisesRegex(publisher.PublicationError,"missing canonical team"): publisher.preflight(connection,candidate())
    def test_richmond_and_lynchburg_are_distinct(self):
        rows=[fact("richmond","VENUE",22806,"CLASSIC_GROUND"),fact("lynchburg","VENUE",27806,"CLASSIC_GROUND")]
        publisher.validate_candidate(candidate(rows)); plan=publisher.preflight(FakeConnection(),candidate(rows)); self.assertEqual(plan["operations"]["decision_facts"]["insert"],2)
    def test_subaru_park_is_id_bound(self):
        row=fact("subaru","VENUE",1620,"UNIQUE_SETTING"); publisher.validate_candidate(candidate([row])); self.assertEqual(row["venue_id"],1620)
    def test_strict_table_boundary(self):
        self.assertEqual(publisher.MUTABLE_TABLES,{"decision_facts","decision_evidence"})
        source=Path(publisher.__file__).read_text(encoding="utf-8")
        mutations=[line for line in source.splitlines() if "INSERT INTO " in line or "UPDATE " in line or "DELETE FROM " in line]
        self.assertTrue(mutations); self.assertTrue(all("decision_facts" in line or "decision_evidence" in line for line in mutations))


class ExecutionTests(unittest.TestCase):
    def test_write_requires_confirmation_before_engine(self):
        with self.assertRaisesRegex(publisher.PublicationError,"confirm-write"): publisher.execute("unused",candidate(),"A"*64,"write")
    def test_dry_run_is_read_only(self):
        connection=FakeConnection()
        with patch.object(publisher,"create_engine",return_value=Engine(connection)):
            result=publisher.execute("unused",candidate(),"A"*64,"dry-run")
        self.assertEqual(result["transaction_outcome"],"ROLLED_BACK_READ_ONLY"); self.assertFalse(result["persistent_mutation"]); self.assertEqual(connection.facts,[])
    def test_rollback_only_and_idempotence(self):
        connection=FakeConnection()
        with patch.object(publisher,"create_engine",return_value=Engine(connection)), patch.object(publisher,"verify_database_target",return_value={}):
            result=publisher.execute("unused",candidate(),"A"*64,"rollback-only",expected_target=object(),target_environment="test")
        self.assertEqual(result["transaction_outcome"],"INTENTIONAL_ROLLBACK"); self.assertEqual(result["temporary_idempotence"]["decision_facts"],{"insert":0,"reuse":1,"conflict":0}); self.assertFalse(result["persistent_mutation"]); self.assertTrue(connection.tx.rolled_back)
    def test_transaction_failure_rolls_back(self):
        connection=FakeConnection()
        with patch.object(publisher,"create_engine",return_value=Engine(connection)), patch.object(publisher,"verify_database_target",return_value={}):
            result=publisher.execute("unused",candidate(),"A"*64,"rollback-only",failure_hook=lambda _: (_ for _ in ()).throw(RuntimeError("boom")),expected_target=object(),target_environment="test")
        self.assertEqual(result["status"],"FAIL"); self.assertTrue(connection.tx.rolled_back); self.assertFalse(result["persistent_mutation"])
    def test_write_confirmation_commits(self):
        connection=FakeConnection()
        with patch.object(publisher,"create_engine",return_value=Engine(connection)), patch.object(publisher,"verify_database_target",return_value={}):
            result=publisher.execute("unused",candidate(),"A"*64,"write",confirm_write=True,expected_target=object(),target_environment="test")
        self.assertEqual(result["transaction_outcome"],"COMMITTED"); self.assertTrue(result["persistent_mutation"]); self.assertTrue(connection.tx.committed)
    def test_mutation_mode_requires_database_target(self):
        connection=FakeConnection()
        with patch.object(publisher,"create_engine",return_value=Engine(connection)):
            result=publisher.execute("unused",candidate(),"A"*64,"rollback-only")
        self.assertEqual(result["status"],"FAIL"); self.assertIn("target",result["exception_message"])


if __name__ == "__main__": unittest.main()
