"""Offline foundation regressions, mirrored against disposable loopback PostgreSQL."""
import copy
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import tempfile
import unittest
import uuid
from unittest.mock import patch, Mock

from sqlalchemy import create_engine, MetaData, Table, select, text, DateTime
from sqlalchemy.orm import Session
from ingestion.api_football import ApiFootballClient
from test_fixture_discovery import database
from backend.fixture_integrity import (META, SCHEDULE, VENUES, RUNS, identity, observation, utc,
    availability, detect_conflicts, reconcile_observations, set_verified_venue, set_schedule_evidence,
    RunReceipt, CURRENT_RUN, missed_run, eligibility_query, project_rows, transaction_integrity, venue_geography)

NOW = datetime(2026, 11, 10, 12, tzinfo=timezone.utc)
WHEN = datetime(2026, 12, 5, 15, tzinfo=timezone.utc)


def fixture(fid=1, *, home=10, away=11, league=45, kickoff=WHEN, status='NS', venue=22805):
    return dict(fixture_id=fid, fixture_date=kickoff, home_team_id=home, away_team_id=away,
        home_team='Home', away_team='Away', league_id=league, league_name='Competition',
        season=2026, country='USA', round='Final', status=status, venue_id=venue,
        venue_name='American Legion Memorial Stadium', venue_city='Charlotte', home_goals=None, away_goals=None)


def obs(r):
    return dict(r, fixture_date=utc(r['fixture_date']).isoformat(), venue=dict(id=None,name=r.get('venue_name')))


def payload(r):
    return dict(fixture=dict(id=r['fixture_id'],date=utc(r['fixture_date']).isoformat(),
        status=dict(short=r['status']), venue=dict(id=None,name=r.get('venue_name'))),
        league=dict(id=r['league_id'],season=r['season'],round=r['round'],country=r['country']),
        teams=dict(home=dict(id=r['home_team_id'],name=r['home_team']),away=dict(id=r['away_team_id'],name=r['away_team'])),
        goals=dict(home=None,away=None))


def attestation(r):
    return dict(timing_verified=True, timing_kickoff=utc(r['fixture_date']).isoformat(),
        senior_team_ids=[r['home_team_id'],r['away_team_id']], source_url='https://official.example/schedule',
        actor='authorised reviewer', review_after='2027-01-01T00:00:00+00:00', provisional=False)


class IntegrityTests(unittest.TestCase):
    def setUp(self):
        self.engine = database()
        META.create_all(self.engine)
        self.seed()

    def seed(self):
        with self.engine.begin() as c:
            self.fixtures = Table('fixtures', MetaData(), autoload_with=c)
            self.venues = Table('venues', MetaData(), autoload_with=c)
            c.execute(self.fixtures.delete())
            c.execute(self.venues.insert(), [dict(venue_id=22805,name='American Legion Memorial Stadium',city='Charlotte',country='USA',latitude=35.218163,longitude=-80.828929),
                dict(venue_id=27331,name='Mecklenburg County Sportsplex at Matthews',city='Matthews',country='USA',latitude=35.110755,longitude=-80.698566)])
            c.exec_driver_sql('CREATE TABLE personal_links (person_id integer, fixture_id integer REFERENCES fixtures(fixture_id), kind text)')

    def tearDown(self):
        self.engine.dispose()

    def insert(self, *rows):
        with self.engine.begin() as c:
            c.execute(self.fixtures.insert(), rows)

    def observe(self, *rows):
        with self.engine.begin() as c:
            return reconcile_observations(c, {r['fixture_id']:[obs(r)] for r in rows}, now=NOW)

    def state(self, fid):
        with self.engine.connect() as c:
            return dict(c.execute(select(SCHEDULE).where(SCHEDULE.c.fixture_id==fid)).mappings().one())

    def test_unknown_provider_reassignment_hides_stale_pin_and_later_resolution_releases(self):
        a=fixture();self.insert(a)
        unknown=dict(fixture_id=1,classification='NO_CHANGE',venue_mapping='UNKNOWN',
                     raw_provider_venue=dict(id=999999,name='New unmapped venue'))
        provider=payload(a);provider['fixture']['venue']=unknown['raw_provider_venue']
        with self.engine.begin() as c:
            transaction_integrity(c,[provider],manifest=[unknown])
            policy=dict(c.execute(select(VENUES)).mappings().one())
            self.assertEqual(policy['state'],'UNRESOLVED')
            self.assertEqual(c.execute(select(self.fixtures.c.venue_id)).scalar_one(),22805)
            transaction_integrity(c,[provider],manifest=[unknown])
            self.assertEqual(c.execute(select(VENUES.c.revision)).scalar_one(),policy['revision'])
            transaction_integrity(c,[payload(a)],manifest=[dict(unknown,venue_mapping='MISSING')])
            self.assertEqual(c.execute(select(VENUES.c.state)).scalar_one(),'UNRESOLVED')
            transaction_integrity(c,[payload(a)],manifest=[dict(unknown,venue_mapping='MATCHED')])
            self.assertEqual(c.execute(select(VENUES.c.state)).scalar_one(),'PROVIDER_ASSIGNED')
            self.assertEqual(c.execute(select(self.fixtures.c.venue_id)).scalar_one(),22805)

    def test_01_fa_cup_displacement_is_suspected_not_inferred_PST(self):
        a,b=fixture(1,league=39),fixture(2,away=12)
        self.insert(a,b);result=self.observe(a,b)
        self.assertEqual(len(result['cases']),1)
        self.assertEqual(self.state(1)['state'],'SUSPECTED_CONFLICT')
        self.assertFalse(self.state(1)['schedule_hold'])
        self.assertEqual(self.state(1)['effective_status'],'NS')

    def test_san_clemente_bad_coordinates_detected_with_NULL_provider_and_no_rebinding(self):
        a=dict(fixture(1618001,home=17619,away=9901,league=456),country='Spain');self.insert(a)
        provider=payload(a);provider['fixture']['venue']={'id':None,'name':None,'city':None}
        with self.engine.begin() as c:
            c.execute(self.venues.update().where(self.venues.c.venue_id==22805).values(country='Spain',latitude=-5.437638,longitude=-80.738506))
            result=transaction_integrity(c,[provider])
            self.assertEqual(c.execute(select(VENUES.c.state)).scalar_one(),'DISPUTED')
            self.assertEqual(c.execute(select(self.fixtures.c.venue_id)).scalar_one(),22805)
            self.assertEqual(float(c.execute(select(self.venues.c.latitude).where(self.venues.c.venue_id==22805)).scalar_one()),-5.437638)
            from sqlalchemy.orm import registry
            mapped=registry()
            class LocalFixture:pass
            mapped.map_imperatively(LocalFixture,self.fixtures)
            with Session(bind=c) as db:
                query,_=eligibility_query(db.query(LocalFixture),db,LocalFixture)
                self.assertEqual(query.all(),[])
            mapped.dispose()
            # Synthetic test-only repair, not a proposed real-pitch coordinate.
            c.execute(self.venues.update().where(self.venues.c.venue_id==22805).values(latitude=39.0,longitude=-2.0))
            transaction_integrity(c,[provider])
            self.assertEqual(c.execute(select(VENUES.c.state)).scalar_one(),'PROVIDER_ASSIGNED')

    def test_legacy_invalid_coordinates_fail_closed_outside_Spain(self):
        self.insert(fixture())
        from sqlalchemy.orm import registry
        mapped=registry()
        class LocalFixture:pass
        mapped.map_imperatively(LocalFixture,self.fixtures)
        try:
            for lat,lon in [(0,0),(999,-80),(35,999)]:
                with self.engine.begin() as c:
                    c.execute(self.venues.update().where(self.venues.c.venue_id==22805).values(latitude=lat,longitude=lon))
                    self.assertTrue(venue_geography({'country':'USA'},{'country':'USA','latitude':lat,'longitude':lon})['hold'])
                    with Session(bind=c) as db:
                        query,_=eligibility_query(db.query(LocalFixture),db,LocalFixture)
                        self.assertEqual(query.all(),[])
                    self.assertEqual(c.execute(select(self.fixtures.c.venue_id)).scalar_one(),22805)
        finally:mapped.dispose()

    def test_geographic_country_anchor_reviews_never_guess_replacement(self):
        ground=dict(venue_id=1,country='Peru',latitude=-5.437638,longitude=-80.738506)
        home=dict(venue_id=2,country='Spain',latitude=40,longitude=-3)
        result=venue_geography({'country':'Spain'},ground,club_countries=['Spain','Spain'],home_grounds=[home])
        self.assertIn('DOMESTIC_VENUE_COUNTRY_REVIEW',result['reasons'])
        self.assertIn('EXTREME_DISTANCE_FROM_KNOWN_HOMES_REVIEW',result['reasons'])
        self.assertFalse(result['hold'])  # neutral/cross-border possibility requires review
        for lat,lon in [(-5,-80),(35,139),(-33,151)]:
            self.assertTrue(venue_geography({'country':'Spain'},dict(ground,country='Spain',latitude=lat,longitude=lon))['hold'])

    def test_geographic_discovery_and_NULL_nightly_reject_bad_country_coordinates(self):
        from ingestion.discovery_venues import resolve_event_venue
        from refresh_fixture_states import resolve_venue
        from types import SimpleNamespace
        ground=dict(venue_id=26963,provider_venue_id=20167,name='Estadio Municipal San Clemente',city='San Clemente',country='Spain',latitude=-5.437638,longitude=-80.738506)
        scope=SimpleNamespace(country='Spain',venue_countries=(),venue_reviews=())
        with self.assertRaisesRegex(ValueError,'VENUE_GEOGRAPHIC_CONFLICT'):
            resolve_event_venue({'id':20167,'name':ground['name'],'city':ground['city']},scope,{26963:ground},[],[])
        a=dict(fixture(1618001,home=17619,away=9901,league=456,venue=26963),country='Spain')
        provider=payload(a);provider['fixture']['venue']={'id':None,'name':None,'city':None}
        self.assertEqual(resolve_venue(SimpleNamespace(**a),provider,[ground],[],[],{}),(26963,'DISPUTED'))

    def test_geographic_cross_border_islands_international_verified_neutral_preserved(self):
        for country,lat,lon in [('Spain',28.1,-15.4),('Spain',35.89,-5.31),('Andorra',42.53,1.58),('France',-21,55.5)]:
            result=venue_geography({'country':'Spain'},dict(venue_id=1,country=country,latitude=lat,longitude=lon),home_grounds=[dict(venue_id=1,country=country)])
            self.assertFalse(result['hold'])
        foreign=dict(venue_id=9,country='USA',latitude=40,longitude=-74)
        self.assertEqual(venue_geography({'country':'World'},foreign)['reasons'],[])
        self.assertEqual(venue_geography({'country':'Spain'},foreign,verification={'state':'OFFICIAL_VERIFIED','venue_id':9})['reasons'],[])

    def test_02_official_postponement_excludes_stale_upcoming_date(self):
        a=fixture();self.insert(a);self.observe(a)
        with self.engine.begin() as c:
            set_schedule_evidence(c,1,expected_revision=1,evidence=dict(attestation(a),
                official_schedule=dict(status='PST',fixture_date=a['fixture_date'].isoformat())),now=NOW)
        self.assertFalse(availability(self.state(1)['effective_status'],WHEN,now=NOW))

    def test_03_move_date_preserves_history_and_personal_links(self):
        a=fixture();self.insert(a)
        with self.engine.begin() as c:c.exec_driver_sql("INSERT INTO personal_links VALUES (1,1,'interested'),(2,1,'attended')")
        self.observe(a);changed=dict(a,fixture_date=WHEN+timedelta(days=30))
        with self.engine.begin() as c:c.execute(self.fixtures.update().where(self.fixtures.c.fixture_id==1).values(fixture_date=changed['fixture_date']))
        self.observe(changed);self.assertEqual(self.state(1)['state'],'CONFIRMED_RESCHEDULED')
        self.assertEqual(len(self.state(1)['history']),2)
        with self.engine.connect() as c:self.assertEqual(c.exec_driver_sql('SELECT count(*) FROM personal_links').scalar_one(),2)

    def test_04_cup_arrives_before_league_status_high_confidence_hold_only(self):
        a,b=fixture(1,league=39),fixture(2,away=12);self.insert(a,b);self.observe(a,b)
        with self.engine.begin() as c:
            for r in (a,b):set_schedule_evidence(c,r['fixture_id'],expected_revision=1,evidence=attestation(r),now=NOW)
        self.observe(a,b)
        self.assertTrue(self.state(1)['schedule_hold']);self.assertTrue(self.state(2)['schedule_hold'])
        self.assertEqual(self.state(1)['effective_status'],'NS')

    def test_05_same_date_nonoverlap_and_provisional_do_not_suppress(self):
        a,b=fixture(1),fixture(2,kickoff=WHEN+timedelta(hours=7),away=12)
        cases=detect_conflicts([a,b],{1:attestation(a),2:attestation(b)},now=NOW)
        self.assertTrue(cases);self.assertFalse(any(x['high_confidence'] for x in cases))
        b['fixture_date']=WHEN
        e=attestation(b);e['provisional']=True
        self.assertFalse(detect_conflicts([a,b],{1:attestation(a),2:e},now=NOW)[0]['high_confidence'])

    def test_06_reserve_identity_never_matches_first_team_by_name(self):
        a,b=fixture(1),fixture(2,home=99,away=12)
        self.assertEqual(detect_conflicts([a,b],{},now=NOW),[])

    def test_07_repeated_same_ID_moves_idempotent(self):
        a=fixture();self.insert(a);self.observe(a);self.observe(a)
        self.assertEqual(len(self.state(1)['history']),1)
        for days in (7,30,90):
            r=dict(a,fixture_date=WHEN+timedelta(days=days))
            with self.engine.begin() as c:c.execute(self.fixtures.update().where(self.fixtures.c.fixture_id==1).values(fixture_date=r['fixture_date']))
            self.observe(r)
        with self.engine.connect() as c:self.assertEqual(c.execute(select(self.fixtures.c.fixture_id)).scalars().all(),[1])
        self.assertEqual(len(self.state(1)['history']),4)

    def test_08_unproven_replacement_never_merges_personal_records(self):
        a=fixture();self.insert(a);self.observe(a)
        result=self.observe(dict(a,fixture_id=2))
        self.assertEqual(result['observed'],0)
        with self.engine.connect() as c:self.assertEqual(c.execute(select(self.fixtures.c.fixture_id)).scalars().all(),[1])

    def test_09_later_provider_postponement_resolves_pair(self):
        a,b=fixture(1),fixture(2,away=12);self.insert(a,b);self.observe(a,b)
        with self.engine.begin() as c:
            for r in (a,b):set_schedule_evidence(c,r['fixture_id'],expected_revision=1,evidence=attestation(r),now=NOW)
        self.observe(a,b);b['status']='PST'
        with self.engine.begin() as c:c.execute(self.fixtures.update().where(self.fixtures.c.fixture_id==2).values(status='PST'))
        self.observe(b)
        self.assertFalse(self.state(1)['schedule_hold'])
        self.assertEqual(self.state(1)['state'],'RESOLVED_CONFLICT')
        self.assertEqual(self.state(2)['state'],'CONFIRMED_POSTPONED')

    def test_10_released_hold_restores_only_active_fixture(self):
        self.test_09_later_provider_postponement_resolves_pair()
        self.assertTrue(availability(self.state(1)['effective_status'],WHEN,hold=self.state(1)['schedule_hold'],now=NOW))
        self.assertFalse(availability(self.state(2)['effective_status'],WHEN,now=NOW))

    def test_11_unresolved_case_persists_without_observations(self):
        a,b=fixture(1),fixture(2,away=12);self.insert(a,b);self.observe(a,b)
        before=self.state(1)['conflicts']
        with self.engine.begin() as c:reconcile_observations(c,{},now=NOW+timedelta(days=1))
        self.assertEqual(before,self.state(1)['conflicts'])

    def test_12_duplicate_noops_unrelated_rows_unchanged(self):
        a,b=fixture(1),fixture(9,home=98,away=99,league=135)
        self.insert(a,b);self.observe(a);self.observe(a)
        with self.engine.connect() as c:
            row=dict(c.execute(select(self.fixtures).where(self.fixtures.c.fixture_id==9)).mappings().one())
            self.assertEqual(row['status'],'NS');self.assertEqual(row['venue_id'],22805)
            self.assertEqual(c.execute(select(SCHEDULE.c.fixture_id)).scalars().all(),[1])

    def test_statuses_individually_and_historical_results(self):
        for status in ['PST','CANC','SUSP','INT','ABD','AWD','WO']:
            self.assertFalse(availability(status,WHEN,now=NOW),status)
        for status in ['NS','TBD','1H','HT','2H','ET','BT','P']:
            self.assertTrue(availability(status,WHEN,now=NOW),status)
        self.assertTrue(availability('FT',NOW-timedelta(days=1),now=NOW))
        self.assertFalse(availability('FT',WHEN,now=NOW))

    def test_USL_verified_override_raw_provider_retained_and_idempotent(self):
        a=fixture(1649529,home=3991,away=27251,league=489);self.insert(a)
        with self.engine.begin() as c:
            args=dict(source_url='https://www.acboise.com/2026-schedule/',evidence_sha256='a'*64,
                      actor='approved test reviewer',provider_venue=dict(id=None,name='American Legion Memorial Stadium'),now=NOW)
            self.assertTrue(set_verified_venue(c,1649529,27331,**args))
            self.assertFalse(set_verified_venue(c,1649529,27331,**args))
        self.observe(a)
        with self.engine.connect() as c:
            self.assertEqual(c.execute(select(self.fixtures.c.venue_id)).scalar_one(),27331)
            self.assertEqual(c.execute(select(self.fixtures.c.venue_name)).scalar_one(),'American Legion Memorial Stadium')
            self.assertEqual(c.execute(select(VENUES.c.provider_venue)).scalar_one()['name'],'American Legion Memorial Stadium')
            self.assertEqual(c.execute(select(VENUES.c.previous_provider_venue)).scalar_one()['name'],'American Legion Memorial Stadium')
        from refresh_fixture_states import resolve_venue
        from types import SimpleNamespace
        with self.engine.connect() as c:decisions={r['fixture_id']:dict(r) for r in c.execute(select(VENUES)).mappings()}
        self.assertEqual(resolve_venue(SimpleNamespace(**a),payload(a),[],[],[],dict(fixture_verifications=decisions)),(27331,'MATCHED_VERIFIED_OVERRIDE'))

    def test_schedule_official_decision_survives_stale_provider_NS(self):
        a=fixture();self.insert(a);self.observe(a)
        with self.engine.begin() as c:set_schedule_evidence(c,1,expected_revision=1,evidence=dict(attestation(a),official_schedule=dict(status='PST',fixture_date=WHEN.isoformat())),now=NOW)
        self.observe(a);self.assertEqual(self.state(1)['effective_status'],'PST')
        self.assertEqual(self.state(1)['provider_observation']['status'],'NS')

    def test_later_genuine_reschedule_resolves_official_old_slot_postponement(self):
        a=fixture();self.insert(a);self.observe(a)
        with self.engine.begin() as c:set_schedule_evidence(c,1,expected_revision=1,evidence=dict(attestation(a),official_schedule=dict(status='PST',fixture_date=WHEN.isoformat())),now=NOW)
        moved=dict(a,fixture_date=WHEN+timedelta(days=10))
        with self.engine.begin() as c:c.execute(self.fixtures.update().where(self.fixtures.c.fixture_id==1).values(fixture_date=moved['fixture_date']))
        self.observe(moved)
        self.assertEqual(self.state(1)['effective_status'],'NS')
        self.assertEqual(self.state(1)['state'],'CONFIRMED_RESCHEDULED')
        self.assertTrue(any(h.get('reason')=='RESCHEDULED_AFTER_OFFICIAL_POSTPONEMENT' for h in self.state(1)['history']))

    def test_superseded_fixture_and_multi_match_event_do_not_poison_active_match(self):
        a,b=fixture(1),fixture(2,away=12)
        self.assertEqual(detect_conflicts([dict(a,superseded_by=2),b],{1:attestation(a),2:attestation(b)},now=NOW),[])
        proof=dict(attestation(a),multi_match_event=True)
        self.assertFalse(detect_conflicts([a,b],{1:proof,2:attestation(b)},now=NOW)[0]['high_confidence'])

    def test_late_run_and_incomplete_coverage_are_distinct_from_never_started(self):
        row=dict(run_id='late',scheduled_for=NOW.replace(hour=4,minute=20),started_at=NOW,state='COMPLETED')
        self.assertEqual(missed_run([row],now=NOW)['reason'],'LATE_SCHEDULED_RUN')
        row.update(started_at=NOW.replace(hour=4,minute=24),state='INCOMPLETE')
        self.assertEqual(missed_run([row],now=NOW)['reason'],'COVERAGE_INCOMPLETE')

    def test_future_effective_schedule_is_checked_even_when_raw_date_is_in_past(self):
        a=fixture(1,kickoff=NOW-timedelta(days=30));self.insert(a);self.observe(a)
        with self.engine.begin() as c:set_schedule_evidence(c,1,expected_revision=1,evidence=dict(attestation(a),
            official_schedule=dict(status='NS',fixture_date=WHEN.isoformat())),now=NOW)
        b=fixture(2,away=12);self.insert(b)
        result=self.observe(b)
        self.assertTrue(any(set(x['fixture_ids'])=={1,2} for x in result['cases']))

    def test_missed_failed_and_successful_runs_independent_of_provider(self):
        self.assertEqual(missed_run([],now=NOW)['reason'],'MISSED_SCHEDULED_RUN')
        r=dict(run_id='test',scheduled_for=NOW.replace(hour=4,minute=20),started_at=NOW.replace(hour=4,minute=23),state='FAILED')
        self.assertFalse(missed_run([r],now=NOW)['passed'])
        r['state']='COMPLETED';self.assertTrue(missed_run([r],now=NOW)['passed'])

    def test_failed_receipt_survives_fixture_transaction_rollback(self):
        a=fixture();self.insert(a);receipt=RunReceipt(self.engine,now=NOW)
        receipt.request('/fixtures',dict(league=45,season=2026))
        receipt.request('/fixtures',{},failed=True)
        with self.assertRaises(RuntimeError):
            with self.engine.begin() as c:
                c.execute(self.fixtures.update().values(status='PST'))
                raise RuntimeError('fixture transaction failed')
        receipt.finish({},error='TEST_FAILURE')
        with self.engine.connect() as c:
            r=c.execute(select(RUNS)).mappings().one()
            self.assertEqual(r['state'],'FAILED');self.assertEqual(r['requests_attempted'],1);self.assertEqual(r['requests_completed'],0)
            self.assertEqual(c.execute(select(self.fixtures.c.status)).scalar_one(),'NS')

    def test_client_receipt_counts_exact_scope_without_network(self):
        a=fixture();self.insert(a);receipt=RunReceipt(self.engine,now=NOW)
        response=Mock();response.status_code=200;response.headers={'x-ratelimit-requests-remaining':'900','x-ratelimit-remaining':'50'}
        response.json.return_value=dict(response=[payload(a)],results=1,paging=dict(current=1,total=1))
        with tempfile.TemporaryDirectory() as d:
            client=ApiFootballClient('synthetic',Path(d),min_request_interval=0)
            token=CURRENT_RUN.set(receipt)
            try:
                with patch.object(client.session,'get',return_value=response):client.fixtures_between(45,2026,'2026-11-03','2026-12-11')
            finally:CURRENT_RUN.reset(token)
        result=receipt.finish(dict(execution_success=True,commit_confirmed=True,complete=True))
        self.assertEqual(result['state'],'COMPLETED')
        with self.engine.connect() as c:
            r=c.execute(select(RUNS)).mappings().one()
            self.assertEqual(r['requests_attempted'],1);self.assertEqual(r['requests_completed'],1)
            self.assertEqual(r['receipt']['requests'][0]['scopes'],{'45:2026':1})
            self.assertEqual(r['receipt']['accounting']['unaccounted_missing_ids'],[])


@unittest.skipUnless(os.getenv('MATCHGOER_LOCAL_POSTGRES_TEST')=='TRUE','Explicit loopback-only test opt-in')
class PostgresIntegrityTests(IntegrityTests):
    def setUp(self):
        self.admin=create_engine('postgresql+psycopg2://fixture_test@127.0.0.1:55439/postgres',connect_args={'options':'-c statement_timeout=20000'})
        self.schema='integrity_'+uuid.uuid4().hex
        with self.admin.begin() as c:c.exec_driver_sql('CREATE SCHEMA '+self.schema)
        self.engine=create_engine('postgresql+psycopg2://fixture_test@127.0.0.1:55439/postgres',connect_args={'options':'-c search_path='+self.schema+' -c statement_timeout=20000'})
        local=database();old=MetaData();old.reflect(local);new=MetaData()
        for t in old.sorted_tables:
            if t.name in META.tables:
                continue
            clone=t.to_metadata(new)
            for col in clone.c:
                if isinstance(col.type,DateTime):col.type=DateTime(timezone=True)
        new.create_all(self.engine)
        # Run the exact proposed production migration, only in a disposable local schema.
        sql=(Path(__file__).resolve().parents[2]/'backend/migrations/20261110_fixture_integrity.sql').read_text()
        with self.engine.connect() as c:
            with c.connection.driver_connection.cursor() as cursor:cursor.execute(sql)
        local.dispose();self.seed()

    def tearDown(self):
        self.engine.dispose()
        with self.admin.begin() as c:c.exec_driver_sql('DROP SCHEMA '+self.schema+' CASCADE')
        self.admin.dispose()

    def test_database_guard_rejects_other_writers_reverting_USL(self):
        self.test_USL_verified_override_raw_provider_retained_and_idempotent()
        from sqlalchemy.exc import IntegrityError
        with self.assertRaises(IntegrityError):
            with self.engine.begin() as c:c.execute(self.fixtures.update().where(self.fixtures.c.fixture_id==1649529).values(venue_id=22805))

    def test_migration_rollback_refuses_active_protections(self):
        self.test_USL_verified_override_raw_provider_retained_and_idempotent()
        from sqlalchemy.exc import DBAPIError
        sql=(Path(__file__).resolve().parents[2]/'backend/migrations/20261110_fixture_integrity_rollback.sql').read_text()
        with self.assertRaises(DBAPIError):
            with self.engine.connect() as c:
                c.exec_driver_sql(sql)

    def test_exact_migration_rollback_without_active_protections(self):
        sql=(Path(__file__).resolve().parents[2]/'backend/migrations/20261110_fixture_integrity_rollback.sql').read_text()
        with self.engine.connect() as c:c.exec_driver_sql(sql)
        from sqlalchemy import inspect
        self.assertNotIn('fixture_integrity_runs',inspect(self.engine).get_table_names())
        with self.engine.connect() as c:self.assertEqual(c.exec_driver_sql('SELECT count(*) FROM fixtures').scalar_one(),0)


if __name__=='__main__':unittest.main()
