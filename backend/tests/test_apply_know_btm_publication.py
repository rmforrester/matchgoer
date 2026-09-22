import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import apply_know_btm_publication as publisher


def review():
    return {"value_route": "PRACTICAL", "why_matchgoer_cares": "It gives a concrete action.", "disappearance_loss": "The supporter loses a concrete action.", "ui_duplicate": False, "know_duplicate": False, "btm_duplicate": False, "decide_duplicate": False, "editorial_standard_version": "2026-09-22"}


def candidate():
    return {
        "schema_version": 2, "mode": "PUBLICATION_CANDIDATE_NO_WRITE",
        "relationships": [{"relationship_key": "club-ground", "team_id": 1, "team_name": "Club", "venue_id": 10, "venue_name": "Ground", "relationship_type": "HOME", "status": "CURRENT"}],
        "know_facts": [{"editorial_key": "fact", "relationship_key": "club-ground", "team_id": None, "club_venue_id": "RELATIONSHIP", "venue_id": None, "fixture_id": None, "module": "MATCHDAY", "headline": "Arrival", "content": "Enter through the north turnstile beside the station.", "display_order": 1, "publication_status": "PUBLISHED", "confidence": "HIGH", "claim_sensitivity": "STANDARD", "durability": "SEASONAL", "reviewed_at": "2026-09-18", "review_after": "2027-03-18", "expires_at": None, "approved_at": "2026-09-18T00:00:00+00:00", "approved_by": "Editor", "editorial_review": review()}],
        "know_fact_evidence": [{"fact_editorial_key": "fact", "source_type": "OFFICIAL", "source_title": "Club", "source_url": "https://example.test", "source_date": "2026-09-18", "evidence_note": "Official evidence.", "disposition": "SUPPORTS", "review_status": "ACCEPTED", "contributor_user_id": None}],
        "pre_match_spots": [{"spot_key": "spot", "relationship_key": "club-ground", "display_name": "Club lot", "classification": "CLUB_MATCHDAY_VENUE", "audience": "HOME", "supporting_line": "Open before kickoff.", "maps_destination": None, "location_context": "At the ground", "confidence": "HIGH", "status": "CURRENT", "business_status": "NOT_APPLICABLE", "durability": "SEASONAL", "reviewed_at": "2026-09-18", "review_after": "2027-03-18", "display_order": 1, "approved_at": "2026-09-18T00:00:00+00:00", "approved_by": "Editor", "editorial_review": review()}],
        "pre_match_spot_evidence": [{"spot_key": "spot", "source_type": "OFFICIAL", "source_url": "https://example.test", "source_date": "2026-09-18", "disposition": "SUPPORTS", "evidence_note": "Official evidence.", "contributor_user_id": None, "review_status": "ACCEPTED"}],
        "ticket_actions": [], "reviewed_btm_omissions": [], "secondary_withholds": [],
        "allowed_mutations": {"club_venues": 1, "know_facts": 1, "know_fact_evidence": 1, "pre_match_spots": 1, "pre_match_spot_evidence": 1, "venue_guide_facts": 0, "fixtures": 0, "venues": 0, "coordinates": 0, "provider_refs": 0, "aliases": 0, "deletes": 0},
    }


class ContractTests(unittest.TestCase):
    def assert_invalid(self, mutate):
        value = candidate(); mutate(value)
        with self.assertRaises(publisher.PublicationError): publisher.validate_candidate(value)

    def test_01_clean_candidate(self): publisher.validate_candidate(candidate())
    def test_02_duplicate_relationship(self): self.assert_invalid(lambda c: c["relationships"].append(copy.deepcopy(c["relationships"][0])))
    def test_03_duplicate_fact(self): self.assert_invalid(lambda c: c["know_facts"].append(copy.deepcopy(c["know_facts"][0])))
    def test_04_duplicate_spot(self): self.assert_invalid(lambda c: c["pre_match_spots"].append(copy.deepcopy(c["pre_match_spots"][0])))
    def test_05_missing_team(self): self.assert_invalid(lambda c: c["relationships"][0].update(team_id=None))
    def test_06_missing_venue(self): self.assert_invalid(lambda c: c["relationships"][0].update(venue_id=None))
    def test_07_bad_relationship_type(self): self.assert_invalid(lambda c: c["relationships"][0].update(relationship_type="UNKNOWN"))
    def test_08_fact_missing_relationship(self): self.assert_invalid(lambda c: c["know_facts"][0].update(relationship_key="other"))
    def test_09_evidence_missing_fact(self): self.assert_invalid(lambda c: c["know_fact_evidence"][0].update(fact_editorial_key="other"))
    def test_10_btm_missing_relationship(self): self.assert_invalid(lambda c: c["pre_match_spots"][0].update(relationship_key="other"))
    def test_11_btm_evidence_missing_spot(self): self.assert_invalid(lambda c: c["pre_match_spot_evidence"][0].update(spot_key="other"))
    def test_12_btm_not_know(self):
        c = candidate(); self.assertNotIn("spot_key", c["know_facts"][0]); publisher.validate_candidate(c)
    def test_13_invalid_lifecycle(self): self.assert_invalid(lambda c: c["know_facts"][0].update(durability="FOREVER"))
    def test_14_invalid_schema_enum(self): self.assert_invalid(lambda c: c["pre_match_spots"][0].update(classification="PUB"))
    def test_15_mutation_boundary(self): self.assert_invalid(lambda c: c["allowed_mutations"].update(fixtures=1))
    def test_16_omission_is_artifact_only(self):
        c = candidate(); c["pre_match_spots"] = []; c["pre_match_spot_evidence"] = []; c["reviewed_btm_omissions"] = [{"relationship_key": "club-ground", "status": "OMISSION_REVIEWED", "reason": "NONE"}]; c["allowed_mutations"].update(pre_match_spots=0, pre_match_spot_evidence=0); publisher.validate_candidate(c)
    def test_17_secondary_occupant_is_not_owner(self):
        c = candidate(); c["secondary_withholds"] = [{"team_id": 2, "venue_id": 10, "status": "WITHHOLD_INSUFFICIENT_EVIDENCE"}]; publisher.validate_candidate(c); self.assertEqual(c["know_facts"][0]["relationship_key"], "club-ground")
    def test_18_same_name_venues_are_id_bound(self):
        c = candidate(); c["relationships"].append({"relationship_key": "other-city", "team_id": 2, "team_name": "Other", "venue_id": 11, "venue_name": "Ground", "relationship_type": "HOME", "status": "CURRENT"}); c["allowed_mutations"]["club_venues"] = 2; publisher.validate_candidate(c); self.assertNotEqual(c["relationships"][0]["venue_id"], c["relationships"][1]["venue_id"])
    def test_19_hash_mismatch_precedes_database(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "candidate.json"; p.write_text(json.dumps(candidate()), encoding="utf-8")
            with self.assertRaisesRegex(publisher.PublicationError, "SHA-256"):
                publisher.load_candidate(p, "0" * 64)
    def test_20_hash_match(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "candidate.json"; p.write_text(json.dumps(candidate()), encoding="utf-8"); sha = hashlib.sha256(p.read_bytes()).hexdigest()
            loaded, actual = publisher.load_candidate(p, sha); self.assertEqual(loaded["schema_version"], 2); self.assertEqual(actual, sha.upper())
    def test_21_write_confirmation_guard(self):
        with self.assertRaisesRegex(publisher.PublicationError, "confirm-write"):
            publisher.execute("postgresql://unused", candidate(), "A" * 64, "write")
    def test_22_failure_receipt_has_no_persistent_mutation(self):
        class BadEngine:
            def connect(self): raise RuntimeError("boom")
        with patch.object(publisher, "create_engine", return_value=BadEngine()):
            result = publisher.execute("postgresql://unused", candidate(), "A" * 64, "rollback-only")
        self.assertEqual(result["status"], "FAIL"); self.assertFalse(result["persistent_mutation"])
    def test_23_duplicate_know_evidence_is_rejected(self): self.assert_invalid(lambda c: c["know_fact_evidence"].append(copy.deepcopy(c["know_fact_evidence"][0])))
    def test_24_duplicate_btm_evidence_is_rejected(self): self.assert_invalid(lambda c: c["pre_match_spot_evidence"].append(copy.deepcopy(c["pre_match_spot_evidence"][0])))
    def test_25_mid_transaction_failure_rolls_back(self):
        class Tx:
            is_active = True
            committed = False
            rolled_back = False
            def commit(self): self.committed = True; self.is_active = False
            def rollback(self): self.rolled_back = True; self.is_active = False
        class Connection:
            def __init__(self): self.tx = Tx()
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def begin(self): return self.tx
            def execute(self, *args): return None
        connection = Connection()
        class Engine:
            def connect(self): return connection
        empty_plan = {"operations": {}, "ids": {}, "reviewed_omissions": {}, "blocked": [], "conflicts": [], "unrelated_mutations": {}}
        with patch.object(publisher, "create_engine", return_value=Engine()), patch.object(publisher, "preflight", return_value=empty_plan), patch.object(publisher, "_insert", return_value=["club_venues"]), patch.object(publisher, "verify_database_target", return_value={}):
            result = publisher.execute("postgresql://unused", candidate(), "A" * 64, "rollback-only", failure_hook=lambda _: (_ for _ in ()).throw(RuntimeError("mid-write")), expected_target=object(), target_environment="test")
        self.assertTrue(connection.tx.rolled_back); self.assertFalse(connection.tx.committed); self.assertFalse(result["persistent_mutation"])
    def test_26_rollback_only_never_commits(self):
        source = Path(publisher.__file__).read_text(encoding="utf-8")
        rollback_block = source[source.index('if mode == "rollback-only"'):source.index('except Exception as exc:')]
        self.assertIn("transaction.rollback()", rollback_block)
    def test_27_provider_derived_compatible_receipt_is_accepted(self):
        c = candidate(); c["relationships"][0].update(provider_derived=True, identity_receipt={
            "provider":"api_football","provider_team_id":1,"canonical_team_id":1,
            "observed_name":"Club","canonical_name":"Club","league_id":39,"season":2026,
            "identity_resolution":"IDENTITY_COMPATIBLE","approved_override_id":None,
            "resolver_version":"team-identity-option1-v1",
        }); publisher.validate_candidate(c)
    def test_28_provider_derived_missing_receipt_is_rejected(self):
        self.assert_invalid(lambda c: c["relationships"][0].update(provider_derived=True))
    def test_29_provider_derived_unresolved_receipt_is_rejected(self):
        def change(c):
            c["relationships"][0].update(provider_derived=True, identity_receipt={
                "provider":"api_football","provider_team_id":1,"canonical_team_id":1,
                "observed_name":"Club","canonical_name":"Club","league_id":39,"season":2026,
                "identity_resolution":"NEEDS_IDENTITY_REVIEW","approved_override_id":None,
                "resolver_version":"team-identity-option1-v1",
            })
        self.assert_invalid(change)
    def test_30_mutation_mode_requires_database_target(self):
        class Connection:
            def __enter__(self): return self
            def __exit__(self,*args): return False
            def begin(self):
                class Tx:
                    is_active=True
                    def rollback(self): self.is_active=False
                return Tx()
            def execute(self,*args): return None
        class Engine:
            def connect(self): return Connection()
        with patch.object(publisher,"create_engine",return_value=Engine()):
            result=publisher.execute("unused",candidate(),"A"*64,"rollback-only")
        self.assertEqual(result["status"],"FAIL"); self.assertIn("target",result["exception_message"])

    def test_31_club_preserves_team_owner(self):
        c=candidate(); f=c["know_facts"][0]; f.update(module="CLUB",team_id=1,club_venue_id=None)
        publisher.validate_candidate(c); self.assertEqual(publisher._expected_fact(f,99)["team_id"],1)
    def test_32_supporters_preserves_team_owner(self):
        c=candidate(); f=c["know_facts"][0]; f.update(module="SUPPORTERS",team_id=1,club_venue_id=None)
        publisher.validate_candidate(c); self.assertEqual(publisher._expected_fact(f,99)["team_id"],1)
    def test_33_matchday_preserves_relationship_owner(self):
        c=candidate(); publisher.validate_candidate(c); self.assertEqual(publisher._expected_fact(c["know_facts"][0],99)["club_venue_id"],99)
    def test_34_invalid_module_owner_fails(self):
        self.assert_invalid(lambda c:c["know_facts"][0].update(module="CLUB"))
    def test_35_multiple_owners_fail(self):
        self.assert_invalid(lambda c:c["know_facts"][0].update(team_id=1))
    def test_36_missing_editorial_review_fails(self):
        self.assert_invalid(lambda c:c["know_facts"][0].pop("editorial_review"))
    def test_37_duplicate_flag_fails(self):
        self.assert_invalid(lambda c:c["know_facts"][0]["editorial_review"].update(ui_duplicate=True))
    def test_38_valid_ticket_action(self):
        c=candidate(); c["ticket_actions"]=[{"action_key":"tickets","relationship_key":"club-ground","section":"tickets_entry","topic":"official_ticket_portal","content":"Buy match tickets online.","source_type":"official","source_label":"Club tickets","source_url":"https://example.test/tickets","reviewed_at":"2026-09-18","confidence":"high","status":"current","review_after":"2027-03-18","expires_at":None,"display_order":1,"editorial_review":review()}]; c["allowed_mutations"]["venue_guide_facts"]=1; publisher.validate_candidate(c)
        self.assertEqual(publisher._expected_guide(c["ticket_actions"][0],99)["source_url"],"https://example.test/tickets")
    def test_39_invalid_ticket_url_fails(self):
        c=candidate(); c["ticket_actions"]=[{"action_key":"tickets","relationship_key":"club-ground","section":"tickets_entry","topic":"official_ticket_portal","content":"Buy match tickets online.","source_type":"official","source_label":"Club tickets","source_url":"http://example.test/tickets","reviewed_at":"2026-09-18","confidence":"high","status":"current","review_after":"2027-03-18","expires_at":None,"display_order":1,"editorial_review":review()}]; c["allowed_mutations"]["venue_guide_facts"]=1
        with self.assertRaises(publisher.PublicationError): publisher.validate_candidate(c)


if __name__ == "__main__": unittest.main()
