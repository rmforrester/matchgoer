import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine, text

import apply_know_btm_publication as publisher
import know_btm_remediation as rem


BEFORE = {"know_fact_id":1,"editorial_key":"old","team_id":None,"club_venue_id":10,"venue_id":None,"fixture_id":None,"module":"MATCHDAY","headline":"Old","content":"Generic old text.","display_order":1,"publication_status":"PUBLISHED","confidence":"HIGH","claim_sensitivity":"STANDARD","reviewed_at":"2026-09-20","review_after":"2027-03-20","expires_at":None,"approved_at":"2026-09-20T00:00:00+00:00","approved_by":"Editor"}

def candidate(operation="UPDATE"):
    op={"operation_key":"fact-old","operation":operation,"club_venue_id":10,"fact_id":1,"expected_before":copy.deepcopy(BEFORE),"expected_before_sha256":rem.fingerprint(BEFORE),"changes":{"content":"Useful new text."},"evidence":[{"source_type":"OFFICIAL","source_title":"Club","source_url":"https://example.test","source_date":"2026-09-20","evidence_note":"Supports replacement.","disposition":"SUPPORTS","review_status":"ACCEPTED","contributor_user_id":None}]}
    if operation=="RETIRE": op["changes"]={"publication_status":"ARCHIVED"}; op["evidence"]=[]
    if operation=="KEEP": op["changes"]={}; op["evidence"]=[]
    return {"schema_version":2,"mode":rem.CONTRACT_MODE,"original_editorial_candidate_sha256":"9C6E419A04E72EB22C9A0DB55B97DA142F059AFE0E461631289DFB8E870D78BE","relationships":[{"club_venue_id":10,"team_id":1,"team_name":"Club","venue_id":2,"venue_name":"Ground","relationship_type":"HOME","status":"CURRENT"}],"blocked_relationships":[],"know_operations":[op],"btm_operations":[],"allowed_mutations":{"know_facts":int(operation!="KEEP"),"know_fact_evidence":len(op["evidence"]),"pre_match_spots":0,"pre_match_spot_evidence":0}}

def database():
    e=create_engine("sqlite://")
    with e.begin() as c:
        c.execute(text("CREATE TABLE teams(team_id INTEGER PRIMARY KEY,team_name TEXT)")); c.execute(text("CREATE TABLE venues(venue_id INTEGER PRIMARY KEY,name TEXT)")); c.execute(text("CREATE TABLE club_venues(club_venue_id INTEGER PRIMARY KEY,team_id INTEGER,venue_id INTEGER,relationship_type TEXT,status TEXT)"))
        c.execute(text("CREATE TABLE know_facts(know_fact_id INTEGER PRIMARY KEY AUTOINCREMENT,editorial_key TEXT UNIQUE,team_id INTEGER,club_venue_id INTEGER,venue_id INTEGER,fixture_id INTEGER,module TEXT,headline TEXT,content TEXT,display_order INTEGER,publication_status TEXT,confidence TEXT,claim_sensitivity TEXT,reviewed_at TEXT,review_after TEXT,expires_at TEXT,approved_at TEXT,approved_by TEXT,updated_at TEXT)"))
        c.execute(text("CREATE TABLE know_fact_evidence(evidence_id INTEGER PRIMARY KEY AUTOINCREMENT,know_fact_id INTEGER,source_type TEXT,source_title TEXT,source_url TEXT,source_date DATE,evidence_note TEXT,disposition TEXT,review_status TEXT,contributor_user_id INTEGER)"))
        c.execute(text("CREATE TABLE pre_match_spots(pre_match_spot_id INTEGER PRIMARY KEY,club_venue_id INTEGER,display_name TEXT,classification TEXT,audience TEXT,supporting_line TEXT,maps_destination TEXT,location_context TEXT,confidence TEXT,status TEXT,business_status TEXT,reviewed_at TEXT,review_after TEXT,display_order INTEGER,approved_at TEXT,approved_by TEXT)")); c.execute(text("CREATE TABLE pre_match_spot_evidence(evidence_id INTEGER PRIMARY KEY,pre_match_spot_id INTEGER,source_type TEXT,source_url TEXT,source_date TEXT,disposition TEXT,evidence_note TEXT,contributor_user_id INTEGER,review_status TEXT)"))
        c.execute(text("INSERT INTO teams VALUES(1,'Club')")); c.execute(text("INSERT INTO venues VALUES(2,'Ground')")); c.execute(text("INSERT INTO club_venues VALUES(10,1,2,'HOME','CURRENT')"))
        cols=",".join(BEFORE); vals=",".join(':'+x for x in BEFORE); c.execute(text(f"INSERT INTO know_facts({cols}) VALUES({vals})"),BEFORE)
    return e

class Contract(unittest.TestCase):
    def test_clean(self): rem.validate(candidate(), publisher.PublicationError)
    def test_expected_hash(self):
        c=candidate(); c["know_operations"][0]["expected_before_sha256"]="0"*64
        with self.assertRaisesRegex(publisher.PublicationError,"hash"): rem.validate(c,publisher.PublicationError)
    def test_blocked_relationship_fails(self):
        c=candidate(); c["blocked_relationships"]=[{"club_venue_id":10}]
        with self.assertRaisesRegex(publisher.PublicationError,"blocked"): rem.validate(c,publisher.PublicationError)
    def test_strict_boundary(self):
        c=candidate(); c["allowed_mutations"]["fixtures"]=0
        with self.assertRaisesRegex(publisher.PublicationError,"boundary"): rem.validate(c,publisher.PublicationError)
    def test_match_specific_btm_withheld(self):
        c=candidate("KEEP"); c["btm_operations"]=[{"operation_key":"spot","operation":"INSERT","club_venue_id":10,"durability":"MATCH_SPECIFIC"}]; c["allowed_mutations"]["pre_match_spots"]=1
        with self.assertRaisesRegex(publisher.PublicationError,"fixture-scoped"): rem.validate(c,publisher.PublicationError)
    def test_hash_before_database(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"c.json"; p.write_text(json.dumps(candidate()),encoding="utf-8")
            with self.assertRaisesRegex(publisher.PublicationError,"SHA-256"): publisher.load_candidate(p,"0"*64)
    def test_write_confirmation(self):
        with self.assertRaisesRegex(publisher.PublicationError,"confirm-write"): publisher.execute("unused",candidate(),"A"*64,"write")

class Database(unittest.TestCase):
    def test_update_and_idempotence(self):
        e=database(); cnd=candidate()
        with e.begin() as c:
            plan=rem.preflight(c,cnd,publisher.PublicationError); self.assertEqual(plan["operations"]["know_facts"]["update"],1)
            rem.apply(c,cnd,plan); post=rem.preflight(c,cnd,publisher.PublicationError)
            self.assertEqual(post["operations"]["know_facts"]["no_op"],1); self.assertEqual(post["operations"]["know_fact_evidence"]["reuse"],1)
    def test_expected_before_mismatch(self):
        e=database(); cnd=candidate(); cnd["know_operations"][0]["expected_before"]["content"]="wrong"; cnd["know_operations"][0]["expected_before_sha256"]=rem.fingerprint(cnd["know_operations"][0]["expected_before"])
        with e.connect() as c, self.assertRaisesRegex(publisher.PublicationError,"expected-before"): rem.preflight(c,cnd,publisher.PublicationError)
    def test_retire_preserves_evidence_and_no_longer_serves(self):
        e=database(); cnd=candidate("RETIRE")
        with e.begin() as c:
            c.execute(text("INSERT INTO know_fact_evidence(know_fact_id,source_type,source_title,source_url,evidence_note,disposition,review_status) VALUES(1,'OFFICIAL','Old source','u','old','SUPPORTS','ACCEPTED')"))
            plan=rem.preflight(c,cnd,publisher.PublicationError); rem.apply(c,cnd,plan)
            self.assertEqual(c.execute(text("SELECT publication_status FROM know_facts WHERE know_fact_id=1")).scalar_one(),"ARCHIVED")
            self.assertEqual(c.execute(text("SELECT count(*) FROM know_fact_evidence WHERE know_fact_id=1")).scalar_one(),1)
            self.assertEqual(c.execute(text("SELECT count(*) FROM know_facts WHERE publication_status='PUBLISHED'")).scalar_one(),0)
    def test_atomic_rollback(self):
        e=database(); cnd=candidate()
        with e.connect() as c:
            tx=c.begin(); plan=rem.preflight(c,cnd,publisher.PublicationError); rem.apply(c,cnd,plan); tx.rollback()
        with e.connect() as c: self.assertEqual(c.execute(text("SELECT content FROM know_facts WHERE know_fact_id=1")).scalar_one(),BEFORE["content"])
    def test_keep(self):
        e=database(); cnd=candidate("KEEP")
        with e.connect() as c: self.assertEqual(rem.preflight(c,cnd,publisher.PublicationError)["operations"]["know_facts"]["no_op"],1)

if __name__ == "__main__": unittest.main()
