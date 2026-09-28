import os, unittest
from pathlib import Path
from sqlalchemy import create_engine, text

URL=os.environ.get("MATCHGOER_TICKETING_V2_TEST_DATABASE_URL")
M=Path(__file__).parents[1]/"migrations"

@unittest.skipUnless(URL,"disposable local Ticketing V2 PostgreSQL URL not supplied")
class TicketingV2MigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine=create_engine(URL)
        if cls.engine.url.host not in {"localhost","127.0.0.1","::1"}: raise RuntimeError("local PostgreSQL required")

    def exec_file(self,name):
        with self.engine.connect().execution_options(isolation_level="AUTOCOMMIT") as c:
            c.exec_driver_sql((M/name).read_text())

    def test_forward_constraints_rollback_reapply(self):
        self.exec_file("20260927_ticketing_v2_t1.sql")
        with self.engine.begin() as c:
            c.execute(text("insert into venues(venue_id,name) values (990001,'T1 Ground')"))
            c.execute(text("insert into teams(team_id,name) values (990001,'T1 Club')"))
            c.execute(text("insert into club_venues(club_venue_id,team_id,venue_id,relationship_type,status) values (990001,990001,990001,'HOME','CURRENT')"))
            c.execute(text("insert into fixtures(fixture_id,home_team_id,away_team_id) values (990001,990001,990002)"))
            sid=c.execute(text("insert into ticket_sources(club_venue_id,source_url,source_domain,source_state,ticketing_model,adapter_type) values (990001,'https://example.test/tickets','example.test','VERIFIED_DIRECT_PURCHASE_SOURCE','ONLINE_DIRECT','STATIC_OFFICIAL_HTML') returning ticket_source_id")).scalar_one()
            oid=c.execute(text("insert into ticket_availability_observations(fixture_id,ticket_source_id,observed_state,observed_at,valid_until,matching_outcome,matching_evidence) values (990001,:s,'ON_SALE',now(),now()+interval '1 day','MATCHED_CANONICAL_FIXTURE',cast(:e as jsonb)) returning ticket_availability_observation_id"),{"s":sid,"e":'{"date":"exact","opponent":"approved"}'}).scalar_one()
            c.execute(text("insert into fixture_ticket_availability(fixture_id,ticket_source_id,current_observation_id,availability_state,observed_at) values (990001,:s,:o,'ON_SALE',now())"),{"s":sid,"o":oid})
            with self.assertRaises(Exception):
                with c.begin_nested(): c.execute(text("update ticket_availability_observations set observed_state='SOLD_OUT' where ticket_availability_observation_id=:o"),{"o":oid})
            with self.assertRaises(Exception):
                with c.begin_nested(): c.execute(text("insert into ticket_sources(club_venue_id,source_state,ticketing_model,adapter_type) values (990001,'INVALID','UNKNOWN','OTHER')"))
            with self.assertRaises(Exception):
                with c.begin_nested(): c.execute(text("insert into ticket_sources(club_venue_id,source_url,source_domain,source_state,ticketing_model,adapter_type) values (990001,'https://example.test/tickets','example.test','VERIFIED_DIRECT_PURCHASE_SOURCE','ONLINE_DIRECT','STATIC_OFFICIAL_HTML')"))
        self.exec_file("20260927_ticketing_v2_t1_rollback.sql")
        self.exec_file("20260927_ticketing_v2_t1.sql")
        self.exec_file("20260927_ticketing_v2_t1_rollback.sql")

if __name__ == "__main__": unittest.main()
