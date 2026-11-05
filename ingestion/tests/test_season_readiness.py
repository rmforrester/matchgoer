import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from sqlalchemy import create_engine, text

from config.leagues import NEW_FIXTURE_DISCOVERY_SCOPES, SEASON_READINESS_WATCHLIST, SeasonWatch
from ingestion.api_football import ApiFootballClient
from ingestion.season_readiness import InventoryError, assess, fresh, report, snapshot, summary


WATCH = SEASON_READINESS_WATCHLIST[0]


def fixture(fid=10, year=2027, when="2027-03-01T19:00:00Z", venue=100):
    return dict(fixture=dict(id=fid, date=when, venue=dict(id=venue, name="Ground", city="City")),
                league=dict(id=253, season=year),
                teams=dict(home=dict(id=1), away=dict(id=2)))


def stored():
    return dict(teams=[dict(team_id=1, team_name="One"), dict(team_id=2, team_name="Two")],
        venues=[dict(venue_id=5, provider_venue_id=100, name="Ground", city="City", latitude=40, longitude=-73, canonical_venue_id=None)],
        venue_provider_refs=[], venue_names=[], team_identity_overrides=[],
        fixtures=[dict(fixture_id=9, league_id=253, season=2026, home_team_id=1, away_team_id=2, venue_id=5)])


ROSTER = [dict(team=dict(id=1, name="One")), dict(team=dict(id=2, name="Two"))]


def database():
    e = create_engine("sqlite://")
    with e.begin() as c:
        for statement in (
            'CREATE TABLE fixtures(fixture_id INTEGER PRIMARY KEY, league_id INTEGER, season INTEGER, home_team_id INTEGER, away_team_id INTEGER, venue_id INTEGER)',
            'CREATE TABLE teams(team_id INTEGER PRIMARY KEY, team_name TEXT)',
            'CREATE TABLE venues(venue_id INTEGER PRIMARY KEY, provider_venue_id INTEGER, name TEXT, city TEXT, latitude REAL, longitude REAL, canonical_venue_id INTEGER)',
            'CREATE TABLE venue_provider_refs(venue_id INTEGER, provider TEXT, provider_venue_id INTEGER, valid_to TEXT)',
            'CREATE TABLE venue_names(venue_id INTEGER, name TEXT)',
            'CREATE TABLE team_identity_overrides(provider TEXT,provider_team_id INTEGER,league_id INTEGER,season INTEGER,canonical_team_id INTEGER,expected_provider_name TEXT,review_status TEXT)',
            'CREATE TABLE supporter_history(id INTEGER PRIMARY KEY, private_note TEXT)',
            "INSERT INTO supporter_history VALUES(1,'unchanged')",
            'INSERT INTO fixtures VALUES(9,253,2026,1,2,5)',
            "INSERT INTO teams VALUES(1,'One'),(2,'Two')",
            "INSERT INTO venues VALUES(5,100,'Ground','City',40,-73,NULL)",
        ):
            c.exec_driver_sql(statement)
    return e


class SeasonReadinessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.client = ApiFootballClient("test-only", Path(self.tmp.name), min_request_interval=0)
        self.client.session.get = Mock()

    def respond(self, rows, **extra):
        response = Mock(status_code=200, headers={"x-ratelimit-requests-remaining":"500", "x-ratelimit-remaining":"50"})
        response.json.return_value = dict(response=rows, results=len(rows), errors=[], paging=dict(current=1,total=1), **extra)
        return response

    def metadata(self, *years):
        return [dict(league=dict(id=253),seasons=[dict(year=y) for y in years])]

    def test_unavailable_season_one_request_and_no_activation(self):
        active = copy.deepcopy(NEW_FIXTURE_DISCOVERY_SCOPES)
        self.client.session.get.return_value = self.respond(self.metadata(2026))
        e=database();self.addCleanup(e.dispose)
        result=report(self.client,e,[WATCH])
        self.assertEqual(result['requests'],1)
        self.assertEqual(result['competitions'][0]['status'],'PROVIDER_NEXT_SEASON_ABSENT')
        self.assertEqual(active,NEW_FIXTURE_DISCOVERY_SCOPES)
        self.assertIn('read-only',summary(result))

    def test_advertised_empty_does_not_fetch_roster(self):
        self.client.session.get.side_effect=[self.respond(self.metadata(2026,2027)),self.respond([])]
        e=database();self.addCleanup(e.dispose)
        result=report(self.client,e,[WATCH])
        self.assertEqual(result['requests'],2)
        self.assertEqual(result['competitions'][0]['seasons'][0]['status'],'ADVERTISED_NO_FIXTURES')

    def test_new_fixtures_mapping_discovery_alert_and_preservation(self):
        self.client.session.get.side_effect=[self.respond(self.metadata(2026,2027)),self.respond([fixture()]),self.respond(ROSTER)]
        e=database();self.addCleanup(e.dispose)
        before=snapshot(e,[WATCH]);result=report(self.client,e,[WATCH]);after=snapshot(e,[WATCH])
        self.assertEqual(before,after)
        with e.connect() as c:
            self.assertEqual(c.execute(text('SELECT private_note FROM supporter_history')).scalar(),'unchanged')
            with self.assertRaises(Exception):c.exec_driver_sql("UPDATE supporter_history SET private_note='bad'")
        row=result['competitions'][0]
        self.assertTrue(row['discovery_alert'])
        self.assertEqual(row['seasons'][0]['missing_fixture_ids'],[10])
        self.assertEqual(row['seasons'][0]['fixtures'][0]['venue_readiness'],'GEOGRAPHICALLY_READY')

    def test_mls_shared_key_both_phases_one_fetch(self):
        self.client.session.get.side_effect=[self.respond(self.metadata(2027)),self.respond([
            fixture(),fixture(11,when='2028-05-02T20:00:00Z')]),self.respond(ROSTER)]
        e=database();self.addCleanup(e.dispose)
        r=report(self.client,e,[WATCH]);self.assertEqual(r['requests'],3)
        self.assertEqual([p['provider_keys_observed'] for p in r['competitions'][0]['phases']],[[2027],[2027]])

    def test_mls_distinct_keys_no_assumed_year_mapping(self):
        self.client.session.get.side_effect=[self.respond(self.metadata(2027,2028)),self.respond([fixture()]),self.respond(ROSTER),self.respond([fixture(11,2028,'2027-08-01T20:00:00Z')]),self.respond(ROSTER)]
        e=database();self.addCleanup(e.dispose)
        r=report(self.client,e,[WATCH]);self.assertEqual(r['requests'],5)
        self.assertEqual([p['provider_keys_observed'] for p in r['competitions'][0]['phases']],[[2027],[2028]])

    def test_provider_reuses_previous_key_with_extended_dates(self):
        meta=self.metadata(2026);meta[0]['seasons'][0].update(start='2026-02-01',end='2028-05-31')
        self.client.session.get.side_effect=[self.respond(meta),self.respond([fixture(year=2026)]),self.respond(ROSTER)]
        e=database();self.addCleanup(e.dispose)
        r=report(self.client,e,[WATCH])
        self.assertEqual(r['competitions'][0]['phases'][0]['provider_keys_observed'],[2026])
        self.assertFalse(r['competitions'][0]['seasons'][0]['newly_available'])

    def test_missing_metadata_not_interpreted_as_season_absence(self):
        self.client.session.get.return_value=self.respond([])
        e=database();self.addCleanup(e.dispose)
        r=report(self.client,e,[WATCH]);self.assertEqual(len(r['errors']),1)
        self.assertNotEqual(r['competitions'][0]['status'],'PROVIDER_NEXT_SEASON_ABSENT')

    def test_payload_errors_and_rate_limit_never_claim_empty(self):
        import requests
        for rate_limit in (False,True):
            with self.subTest(rate_limit=rate_limit):
                if rate_limit:
                    response=self.respond([]);response.raise_for_status.side_effect=requests.HTTPError('synthetic429')
                else:
                    response=self.respond([]);response.json.return_value['errors']={'requests':'synthetic quota exhausted'}
                self.client.session.get.return_value=response
                with self.assertRaises(RuntimeError):fresh(self.client,'/leagues',13,country='USA')

    def test_existing_fixture_cannot_be_reassigned_to_new_season(self):
        with self.assertRaisesRegex(InventoryError,'EXISTING_FIXTURE_IDENTITY'):
            assess(WATCH,2027,[fixture(fid=9)],ROSTER,stored())

    def test_name_change_requires_review_not_automatic_rebrand(self):
        roster=copy.deepcopy(ROSTER);roster[1]['team']['name']='Unrelated Successor'
        r=assess(WATCH,2027,[fixture()],roster,stored())
        self.assertEqual(r['clubs'][1]['mapping'],'NEEDS_IDENTITY_REVIEW')
        self.assertEqual(r['fixtures'][0]['missing_team_mappings'],[2])

    def test_stale_empty_cache_bypassed(self):
        path=self.client._cache_path('/fixtures',dict(league=253,season=2027));path.write_text(json.dumps(dict(response=[])))
        self.client.session.get.return_value=self.respond([fixture()])
        self.assertEqual(len(fresh(self.client,'/fixtures',13,league=253,season=2027)),1)
        self.assertEqual(self.client.cache_hits,0)

    def test_partial_inventory_rejected(self):
        r=self.respond([fixture()]);r.json.return_value['paging']['total']=2
        self.client.session.get.return_value=r
        with self.assertRaisesRegex(InventoryError,'INCOMPLETE'):fresh(self.client,'/fixtures',13,league=253,season=2027)

    def test_count_mismatch_rejected(self):
        r=self.respond([fixture()]);r.json.return_value['results']=2;self.client.session.get.return_value=r
        with self.assertRaises(InventoryError):fresh(self.client,'/fixtures',13,league=253,season=2027)

    def test_timeout_is_unverified_not_absence(self):
        import requests
        self.client.session.get.side_effect=requests.Timeout('synthetic')
        e=database();self.addCleanup(e.dispose)
        r=report(self.client,e,[WATCH]);self.assertEqual(len(r['errors']),1)
        self.assertEqual(r['competitions'][0]['status'],'UNVERIFIED_PROVIDER_OR_IDENTITY_ERROR')

    def test_quota_and_budget_stop_before_extra_requests(self):
        self.client.session.get.return_value=self.respond(self.metadata(2027))
        e=database();self.addCleanup(e.dispose)
        r=report(self.client,e,[WATCH],max_requests=1)
        self.assertEqual(r['requests'],1);self.assertEqual(r['errors'][0]['category'],'REQUEST_BUDGET_EXHAUSTED')
        self.client.quota['daily_remaining']=100
        with self.assertRaisesRegex(InventoryError,'QUOTA'):fresh(self.client,'/fixtures',13,league=253,season=2027)

    def test_missing_coordinates_and_venue_never_substitute_home(self):
        s=stored();s['venues'][0]['latitude']=None
        r=assess(WATCH,2027,[fixture()],ROSTER,s)
        self.assertEqual(r['fixtures'][0]['venue_readiness'],'KNOWN_VENUE_MISSING_COORDINATES')
        r=assess(WATCH,2027,[fixture(venue=None)],ROSTER,s)
        self.assertIsNone(r['fixtures'][0]['canonical_venue_id'])

    def test_event_venue_conflict_and_ambiguous_mapping(self):
        f=fixture();f['fixture']['venue']['name']='Etihad Park'
        r=assess(WATCH,2027,[f],ROSTER,stored())
        self.assertEqual(r['fixtures'][0]['venue_readiness'],'EVENT_VENUE_CONFLICT')
        s=stored();s['venue_provider_refs']=[dict(provider='api_football',provider_venue_id=100,venue_id=999,valid_to=None)]
        r=assess(WATCH,2027,[fixture()],ROSTER,s)
        self.assertEqual(r['fixtures'][0]['venue_readiness'],'AMBIGUOUS_EVENT_VENUE')

    def test_missing_participant_rejected(self):
        with self.assertRaisesRegex(InventoryError,'PARTICIPANT'):assess(WATCH,2027,[fixture()],ROSTER[:1],stored())

    def test_club_absence_is_not_closure_and_new_club_unmapped(self):
        roster=[ROSTER[0],dict(team=dict(id=3,name='New'))];f=fixture();f['teams']['away']['id']=3
        r=assess(WATCH,2027,[f],roster,stored())
        self.assertEqual(r['prior_clubs_missing_from_provider'],[2])
        self.assertEqual(r['clubs'][1]['continuity'],'NEW_OR_PROMOTED_CANDIDATE')
        self.assertIsNone(r['clubs'][1]['canonical_team_id'])

    def test_independent_continuity_evidence_required(self):
        evidence=dict(league_id=253,season=2027,canonical_team_id=2,classification='CONFIRMED_WITHDRAWN',reviewed=True,source='https://club.example/statement')
        r=assess(WATCH,2027,[fixture()],ROSTER,stored(),[evidence]);self.assertEqual(r['reviewed_continuity'],[evidence])
        evidence['source']=''
        with self.assertRaisesRegex(InventoryError,'UNSUPPORTED_CONTINUITY'):assess(WATCH,2027,[fixture()],ROSTER,stored(),[evidence])

    def test_identity_duplicates_and_timezone_conflicts(self):
        for rows in ([fixture(),fixture()], [fixture(year=2028)], [fixture(when='2027-03-01T19:00:00')]):
            with self.subTest(rows=rows),self.assertRaises(InventoryError):assess(WATCH,2027,rows,ROSTER,stored())

    def test_european_scope_reusable_and_calendar_boundary(self):
        watch=SeasonWatch('England',39,'Premier League',2026)
        f=fixture(year=2027,when='2028-01-01T00:30:00+01:00');f['league']['id']=39
        r=assess(watch,2027,[f],ROSTER,stored())
        self.assertEqual(r['fixtures'][0]['date'],'2027-12-31')


if __name__=='__main__':unittest.main()
