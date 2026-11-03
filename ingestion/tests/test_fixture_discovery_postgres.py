"""Explicit opt-in, disposable loopback-only PostgreSQL discovery integration."""
import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import create_engine, MetaData, DateTime, text
from ingestion.pipeline import run_fixture_discovery
from test_fixture_discovery import database, Client, DAY, payload

@unittest.skipUnless(os.getenv('MATCHGOER_LOCAL_POSTGRES_TEST') == 'TRUE', 'Explicit isolated loopback PostgreSQL test opt-in required')
class DiscoveryPostgresTests(unittest.TestCase):
    def setUp(self):
        # Deliberately fixed local test endpoint: never accept DATABASE_URL here.
        self.admin=create_engine('postgresql+psycopg2://fixture_test@127.0.0.1:55439/postgres')
        with self.admin.begin() as c:
            c.exec_driver_sql('DROP SCHEMA IF EXISTS fixture_discovery_test CASCADE')
            c.exec_driver_sql('CREATE SCHEMA fixture_discovery_test')
        self.engine=create_engine('postgresql+psycopg2://fixture_test@127.0.0.1:55439/postgres',
            connect_args={'options':'-c search_path=fixture_discovery_test'})
        local=database()
        try:
            old=MetaData();old.reflect(local); new=MetaData()
            for table in old.sorted_tables:
                clone=table.to_metadata(new)
                for column in clone.c:
                    if isinstance(column.type,DateTime): column.type=DateTime(timezone=True)
            new.create_all(self.engine)
            with local.connect() as src,self.engine.begin() as dst:
                for name, table in old.tables.items():
                    rows=[dict(r) for r in src.execute(table.select()).mappings()]
                    if rows: dst.execute(new.tables[name].insert(),rows)
        finally:local.dispose()

    def tearDown(self):
        self.engine.dispose()
        with self.admin.begin() as c:c.exec_driver_sql('DROP SCHEMA fixture_discovery_test CASCADE')
        self.admin.dispose()

    def state(self):
        with self.engine.connect() as c:
            return {t:list(c.exec_driver_sql('SELECT * FROM '+t+' ORDER BY 1'))
                    for t in ('fixtures','teams','venues','attendance','accounts','photos','editorial','supporter_intents')}

    def test_insert_idempotence_and_protected_tables(self):
        before=self.state()
        first=run_fixture_discovery(self.engine,Client(),DAY,write=True)
        second=run_fixture_discovery(self.engine,Client(),DAY,write=True)
        self.assertEqual((first['passed'],first['inserted'],second['passed'],second['inserted']),(True,1,True,0))
        after=self.state()
        for table in before:
            if table!='fixtures':self.assertEqual(before[table],after[table])
        self.assertEqual(before['fixtures'][0],after['fixtures'][0])

    def test_two_concurrent_writers(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:run_fixture_discovery(self.engine,Client(),DAY,write=True),range(2)))
        self.assertTrue(all(r['passed'] for r in results),results)
        self.assertEqual(sum(r['inserted'] for r in results),1)

    def test_trigger_drift_rolls_back_entire_insert(self):
        before=self.state()
        with self.engine.begin() as c:
            c.exec_driver_sql("CREATE FUNCTION corrupt() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN UPDATE fixtures SET status='BAD' WHERE fixture_id=42; RETURN NEW; END $$")
            c.exec_driver_sql('CREATE TRIGGER corrupt AFTER INSERT ON fixtures FOR EACH ROW EXECUTE FUNCTION corrupt()')
        report=run_fixture_discovery(self.engine,Client(),DAY,write=True)
        self.assertFalse(report['passed']);self.assertEqual(report['inserted'],0)
        self.assertEqual(self.state(),before)

    def test_null_venue_stored_without_default_ground(self):
        report=run_fixture_discovery(self.engine,Client([payload(1648321)]),DAY,write=True)
        self.assertTrue(report['passed'],report)
        with self.engine.connect() as c:
            self.assertIsNone(c.exec_driver_sql('SELECT venue_id FROM fixtures WHERE fixture_id=1648321').scalar())

    def test_primary_key_uniqueness(self):
        from sqlalchemy.exc import IntegrityError
        self.assertTrue(run_fixture_discovery(self.engine,Client(),DAY,write=True)['passed'])
        with self.assertRaises(IntegrityError):
            with self.engine.begin() as c:c.exec_driver_sql('INSERT INTO fixtures (fixture_id) VALUES (1647413)')

    def test_precommit_failure_preserves_all_data(self):
        from sqlalchemy import event
        before=self.state()
        def reject(c):raise RuntimeError('synthetic commit rejection')
        event.listen(self.engine,'commit',reject)
        try:
            report=run_fixture_discovery(self.engine,Client(),DAY,write=True)
            self.assertFalse(report['passed']);self.assertEqual(report['inserted'],0)
        finally:event.remove(self.engine,'commit',reject)
        self.assertEqual(self.state(),before)
