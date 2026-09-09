import copy, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from sqlalchemy import Boolean, Column, Date, DateTime, Float, Integer, MetaData, String, Table, create_engine, select
from config.leagues import LeagueScope
from ingestion.pipeline import TerraceTalkImporter

class Client:
    failures=[]; requests_made=cache_hits=0
    def league_for_season(self, league, season): return [{"league":{"id":league}}]
    def teams(self,*args): return copy.deepcopy(self.team_rows)
    def fixtures(self,*args): return []

class VenueIdentityGuardIntegrationTest(unittest.TestCase):
    def test_identity_change_is_flagged_and_stale_coordinate_row_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine=create_engine("sqlite:///"+str(Path(tmp)/"test.db")); m=MetaData()
            v=Table("venues",m,Column("venue_id",Integer,primary_key=True),Column("provider_venue_id",Integer),Column("name",String),Column("city",String),Column("country",String),Column("address",String),Column("capacity",Integer),Column("latitude",Float),Column("longitude",Float))
            Table("venue_names",m,Column("venue_name_id",Integer,primary_key=True),Column("venue_id",Integer),Column("name",String),Column("normalized_name",String),Column("name_type",String),Column("source",String),Column("valid_to",Date))
            Table("venue_provider_refs",m,Column("venue_provider_ref_id",Integer,primary_key=True),Column("venue_id",Integer),Column("provider",String),Column("provider_venue_id",Integer),Column("is_primary",Boolean))
            Table("teams",m,Column("team_id",Integer,primary_key=True),Column("team_name",String),Column("venue_id",Integer),Column("active",Boolean))
            Table("fixtures",m,Column("fixture_id",Integer,primary_key=True),Column("fixture_date",DateTime),Column("venue_id",Integer),Column("venue_name",String),Column("venue_city",String),Column("league_id",Integer),Column("league_name",String),Column("country",String),Column("season",Integer),Column("round",String),Column("status",String),Column("home_team_id",Integer),Column("home_team",String),Column("away_team_id",Integer),Column("away_team",String),Column("home_goals",Integer),Column("away_goals",Integer));m.create_all(engine)
            canonical={"venue_id":566,"provider_venue_id":566,"name":"Wembley Stadium","city":"London","country":"England","address":"Wembley","capacity":90000,"latitude":51.556070,"longitude":-0.279603}
            with engine.begin() as c:
                c.execute(v.insert().values(**canonical));c.execute(m.tables["venue_provider_refs"].insert().values(venue_provider_ref_id=1,venue_id=566,provider="api_football",provider_venue_id=566,is_primary=True));c.execute(m.tables["teams"].insert().values(team_id=65,team_name="Nottingham Forest",venue_id=566,active=True))
            client=Client();client.team_rows=[{"team":{"id":65,"name":"Nottingham Forest"},"venue":{"id":566,"name":"The City Ground","city":"Nottingham","country":"England","address":"Pavilion Road","capacity":30576}}]
            with patch("ingestion.pipeline.create_engine",return_value=engine): importer=TerraceTalkImporter(client,"unused")
            report=importer.write_import(LeagueScope("England",39,"Premier League",2026,"2026/27"),geocode=False)
            with engine.connect() as c: stored=dict(c.execute(select(v)).mappings().one())
            self.assertEqual(stored,canonical);self.assertEqual(len(report.provider_reference_review_candidates),1);self.assertEqual(set(report.provider_reference_review_candidates[0]["reasons"]),{"conflicting_city","unresolved_name_change"})
            importer.engine.dispose();engine.dispose()

if __name__=="__main__": unittest.main()
