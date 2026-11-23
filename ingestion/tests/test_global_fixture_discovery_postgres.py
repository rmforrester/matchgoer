"""Real PostgreSQL insert-only and rollback contracts at a fixed disposable endpoint."""
import copy
import os
import unittest
from unittest.mock import patch
from sqlalchemy import create_engine
from sqlalchemy.orm import Session,sessionmaker
from sqlalchemy import text
import test_fixture_discovery_postgres as native
from test_fixture_discovery import Client
from test_global_fixture_discovery import cray,SCOPE,DAY
from ingestion.pipeline import run_fixture_discovery


class GlobalClient(Client):
    def fixtures_between(self,league,season,start,end):
        self.requests_made+=1
        return [cray()] if league==45 else []


class GlobalDiscoveryPostgresTests(native.DiscoveryPostgresTests):
    def setUp(self):
        super().setUp()
        with self.engine.begin() as c:
            c.execute(text("INSERT INTO teams VALUES (7711,'Cray Wanderers'),(4686,'Stockport County')"))
            c.execute(text("INSERT INTO venues VALUES (21325,'Flamingo Park','London','England',51.429584,.081368,21325,NULL)"))
    def run_global(self,**kwargs):
        key=(1646909,45,2026,7711,4686,'2026-11-08T14:15:00+00:00')
        return run_fixture_discovery(self.engine,GlobalClient(),DAY,write=True,approved_scopes=(SCOPE,),
            event_proofs={key:dict(venue_id=21325,source='https://www.cray-wanderers.com/official-fixture')},**kwargs)
    def test_cray_insert_exact_existing_canonical_and_idempotence(self):
        before=self.state()
        first=self.run_global();second=self.run_global()
        self.assertEqual((first['passed'],first['inserted'],second['inserted']),(True,1,0),first)
        with self.engine.connect() as c:
            self.assertEqual(c.execute(text('SELECT venue_id FROM fixtures WHERE fixture_id=1646909')).scalar(),21325)
        after=self.state()
        for name in before:
            if name!='fixtures':self.assertEqual(before[name],after[name])
        self.assertEqual(before['fixtures'][0],after['fixtures'][0])
    def test_global_trigger_existing_historical_drift_rolls_back(self):
        before=self.state()
        with self.engine.begin() as c:
            c.exec_driver_sql("CREATE FUNCTION corrupt_global() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN UPDATE fixtures SET status='BAD' WHERE fixture_id=42; RETURN NEW; END $$")
            c.exec_driver_sql('CREATE TRIGGER corrupt_global AFTER INSERT ON fixtures FOR EACH ROW EXECUTE FUNCTION corrupt_global()')
        r=self.run_global()
        self.assertFalse(r['passed']);self.assertEqual(r['inserted'],0)
        self.assertEqual(self.state(),before)

    def test_exact_approved_manifest_drift_refuses_insert(self):
        before=self.state()
        r=self.run_global(expected_rows=[])
        self.assertFalse(r['passed']);self.assertIn('APPROVED_DISCOVERY_MANIFEST_CHANGED',r['errors'])
        self.assertEqual(self.state(),before)
    def test_concurrent_same_identity_with_different_values_is_not_silently_skipped(self):
        from ingestion.pipeline import plan_fixture_discovery,apply_fixture_discovery_plan
        from test_global_fixture_discovery import START,END
        payloads={(45,2026):[cray()]}
        with self.engine.connect() as c:
            plan=plan_fixture_discovery(c,payloads,START,END,approved_scopes=(SCOPE,))
        self.assertEqual(apply_fixture_discovery_plan(self.engine,payloads,START,END,
            expected_rows=plan['rows'],approved_scopes=(SCOPE,)),1)
        with self.engine.begin() as c:c.execute(text("UPDATE fixtures SET status='PST' WHERE fixture_id=1646909"))
        before=self.state()
        with self.assertRaisesRegex(ValueError,'CONCURRENT_DISCOVERY_VALUE_CONFLICT'):
            apply_fixture_discovery_plan(self.engine,payloads,START,END,expected_rows=plan['rows'],
                approved_scopes=(SCOPE,),preflight_plan=plan)
        self.assertEqual(self.state(),before)


@unittest.skipUnless(os.getenv('MATCHGOER_LOCAL_POSTGRES_TEST')=='TRUE','Explicit fixed loopback PostgreSQL opt-in required')
class CrayGeographicAcceptanceTests(unittest.TestCase):
    def test_actual_nearby_endpoint_requires_existing_ground_coordinate_correction(self):
        from fastapi import Response
        import main as api
        from models import Base,Team,Venue,Fixture
        from ingestion.pipeline import plan_fixture_discovery,apply_fixture_discovery_plan
        from test_global_fixture_discovery import START,END
        admin=create_engine('postgresql+psycopg2://fixture_test@127.0.0.1:55439/postgres')
        with admin.begin() as c:
            c.exec_driver_sql('DROP SCHEMA IF EXISTS global_fixture_api_test CASCADE')
            c.exec_driver_sql('CREATE SCHEMA global_fixture_api_test')
        engine=create_engine('postgresql+psycopg2://fixture_test@127.0.0.1:55439/postgres',
            connect_args={'options':'-c search_path=global_fixture_api_test'})
        try:
            Base.metadata.create_all(engine)
            with Session(engine) as db:
                db.add_all([Team(team_id=7711,team_name='Cray Wanderers'),Team(team_id=4686,team_name='Stockport County'),
                    Venue(venue_id=21325,provider_venue_id=21325,name='Flamingo Park',country='England',city='London',latitude=51.548740,longitude=-.087615)])
                db.commit()
            proof={(1646909,45,2026,7711,4686,'2026-11-08T14:15:00+00:00'):dict(venue_id=21325,source='https://www.cray-wanderers.com/official-fixture')}
            payloads={(45,2026):[cray()]}
            with engine.connect() as c:
                plan=plan_fixture_discovery(c,payloads,START,END,approved_scopes=(SCOPE,),event_proofs=proof)
            self.assertEqual(apply_fixture_discovery_plan(engine,payloads,START,END,expected_rows=plan['rows'],approved_scopes=(SCOPE,),event_proofs=proof),1)
            def nearby():
                return api.get_nearby(Response(),51.429584,.081368,radius=1,date='2026-11-08',
                    league_id=[45],season=2026,limit=500,offset=0)
            with patch.object(api,'SessionLocal',sessionmaker(bind=engine)):
                self.assertEqual(nearby(),[],'Existing wrong coordinates must not count as correct local placement')
                with engine.begin() as c:
                    c.execute(text('UPDATE venues SET latitude=51.429584,longitude=.081368 WHERE venue_id=21325'))
                result=nearby()
                self.assertEqual([(x['fixture_id'],x['venue_id']) for x in result],[(1646909,21325)])
                with engine.begin() as c:c.execute(text('UPDATE fixtures SET venue_id=NULL WHERE fixture_id=1646909'))
                self.assertEqual(nearby(),[])
            with Session(engine) as db:self.assertEqual(db.query(Venue).count(),1)
        finally:
            engine.dispose()
            with admin.begin() as c:c.exec_driver_sql('DROP SCHEMA global_fixture_api_test CASCADE')
            admin.dispose()
