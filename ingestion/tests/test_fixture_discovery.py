"""Offline discovery contracts: isolated SQLite, synthetic transport, no hosted access."""
import copy
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

import requests
from sqlalchemy import create_engine, text

from ingestion.api_football import ApiFootballClient
from ingestion.pipeline import plan_fixture_discovery, run_fixture_discovery

DAY = date(2026, 11, 3)
START = datetime(2026, 10, 27, tzinfo=timezone.utc)
END = datetime(2026, 12, 4, tzinfo=timezone.utc)


def payload(fid=1647413):
    return dict(fixture=dict(id=fid, date="2026-11-02T01:00:00+00:00", status=dict(short="FT"),
                             venue=dict(id=None, name=None, city=None)),
                league=dict(id=489, season=2026, country="USA", round="Quarter-finals"),
                teams=dict(home=dict(id=27251, name="Boise"), away=dict(id=18905, name="One Knoxville")),
                goals=dict(home=2, away=0))


def database(url="sqlite://"):
    engine = create_engine(url)
    with engine.begin() as c:
        c.execute(text("CREATE TABLE fixtures (fixture_id INTEGER PRIMARY KEY, fixture_date DATETIME, venue_id INTEGER, venue_name TEXT, venue_city TEXT, league_id INTEGER, league_name TEXT, country TEXT, season INTEGER, round TEXT, status TEXT, home_team_id INTEGER, home_team TEXT, away_team_id INTEGER, away_team TEXT, home_goals INTEGER, away_goals INTEGER)"))
        c.execute(text("CREATE TABLE teams (team_id INTEGER PRIMARY KEY, team_name TEXT)"))
        c.execute(text("INSERT INTO teams VALUES (27251,'Boise'),(18905,'One Knoxville')"))
        c.execute(text("CREATE TABLE venues (venue_id INTEGER PRIMARY KEY, name TEXT, city TEXT, country TEXT, latitude FLOAT, longitude FLOAT, provider_venue_id INTEGER, canonical_venue_id INTEGER)"))
        c.execute(text("INSERT INTO venues VALUES (27774,'Athletic Club Boise Soccer Stadium','Garden City, Idaho','USA',43.650530,-116.271900,NULL,NULL)"))
        c.execute(text("CREATE TABLE venue_provider_refs (venue_id INTEGER, provider TEXT, provider_venue_id INTEGER, valid_to TEXT)"))
        c.execute(text("CREATE TABLE venue_names (venue_id INTEGER, name TEXT, valid_to TEXT)"))
        c.execute(text("CREATE TABLE team_identity_overrides (team_identity_override_id INTEGER PRIMARY KEY, provider TEXT, provider_team_id INTEGER, league_id INTEGER, season INTEGER, canonical_team_id INTEGER, expected_provider_name TEXT, review_status TEXT)"))
        for table in ("attendance", "supporter_intents", "photos", "editorial", "accounts"):
            c.execute(text(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY, content TEXT)"))
            c.execute(text(f"INSERT INTO {table} VALUES (1,'must remain unchanged')"))
        c.execute(text("INSERT INTO fixtures VALUES (42,'2026-12-01 19:00:00',NULL,'European ground',NULL,39,'Premier League','England',2026,NULL,'NS',10,'English Home',11,'English Away',NULL,NULL)"))
    return engine


class Client:
    def __init__(self, items=None):
        self.items = [payload()] if items is None else items
        self.requests_made = 0
        self.failures = []
        self.quota = dict(daily_remaining=1000, minute_remaining=200)
        self.fresh = True

    def quota_is_fresh(self):
        return self.fresh

    def highlights_quota_available(self):
        return self.quota is not None and self.quota["daily_remaining"] > 100 and self.quota["minute_remaining"] > 0

    def get(self, *args, **kwargs):
        self.requests_made += 1
        self.fresh = True
        return {}

    def fixtures_between(self, league, season, start, end):
        self.requests_made += 1
        return copy.deepcopy(self.items) if league == 489 else []


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.engine = database()
        self.addCleanup(self.engine.dispose)

    def plan(self, item=None, **kwargs):
        with self.engine.connect() as c:
            return plan_fixture_discovery(c, {(489, 2026): [payload() if item is None else item]}, START, END, **kwargs)

    def test_boise_event_specific_canonical_proof(self):
        plan = self.plan()
        self.assertEqual(plan["held"], [])
        self.assertEqual(plan["rows"][0]["venue_id"], 27774)
        self.assertEqual(plan["rows"][0]["status"], "FT")
        self.assertLess(plan["rows"][0]["fixture_date"], datetime.combine(DAY, datetime.min.time(), tzinfo=timezone.utc))

    def test_no_generic_home_venue_fallback(self):
        plan = self.plan(payload(1648321))
        self.assertEqual(plan['held'], [])
        self.assertIsNone(plan['rows'][0]['venue_id'])
        self.assertEqual(plan['location_outcomes'][1648321], 'UNRESOLVED_EVENT_VENUE')

    def test_missing_identity_is_not_a_material_contradiction(self):
        item=payload(1648321)
        item['fixture']['venue']=dict(id=999999,name='Unmapped event ground',city='Unmapped city')
        self.assertIsNone(self.plan(item)['rows'][0]['venue_id'])
        item=payload();item['fixture']['venue']=dict(id=999999,name='Contradictory ground',city=None)
        self.assertEqual(self.plan(item)['held'][0]['reason'],'REVIEWED_EVENT_VENUE_CONFLICT')

    def test_insert_and_second_run_idempotent(self):
        first = run_fixture_discovery(self.engine, Client(), DAY, write=True)
        second = run_fixture_discovery(self.engine, Client(), DAY, write=True)
        self.assertEqual((first["passed"], first["inserted"], second["inserted"], second["existing"]), (True, 1, 0, 1))

    def test_dry_run_no_mutations(self):
        report = run_fixture_discovery(self.engine, Client(), DAY)
        self.assertEqual((report["passed"], report["candidates"], report["inserted"]), (True, 1, 0))
        with self.engine.connect() as c:
            self.assertEqual(c.execute(text("SELECT count(*) FROM fixtures")).scalar(), 1)

    def test_reviewed_manifest_guard(self):
        plan=run_fixture_discovery(self.engine, Client(), DAY)
        changed=copy.deepcopy(plan['rows']);changed[0]['venue_id']=999
        refused=run_fixture_discovery(self.engine, Client(), DAY, write=True, expected_rows=changed)
        self.assertFalse(refused['passed']);self.assertEqual(refused['inserted'],0)
        accepted=run_fixture_discovery(self.engine, Client(), DAY, write=True, expected_rows=plan['rows'])
        self.assertTrue(accepted['passed']);self.assertEqual(accepted['inserted'],1)

    def test_protected_data_and_european_fixture_preserved(self):
        with self.engine.connect() as c:
            before = {t: list(c.execute(text(f"SELECT * FROM {t}"))) for t in ("fixtures", "teams", "venues", "attendance", "supporter_intents", "photos", "editorial", "accounts")}
        self.assertTrue(run_fixture_discovery(self.engine, Client(), DAY, write=True)["passed"])
        with self.engine.connect() as c:
            for t, rows in before.items():
                query = "SELECT * FROM fixtures WHERE fixture_id=42" if t == "fixtures" else f"SELECT * FROM {t}"
                self.assertEqual(list(c.execute(text(query))), rows)

    def test_conflicting_team_name_unknown_team_and_self_match(self):
        for field, value in (("name", "Different Boise"), ("id", 99999), ("id", 18905)):
            item = payload(); item["teams"]["home"][field] = value
            self.assertEqual(self.plan(item)["rows"], [])

    def test_scoped_canonical_team_override(self):
        with self.engine.begin() as c:
            c.execute(text("INSERT INTO teams VALUES (-1,'Canonical Boise')"))
            c.execute(text("INSERT INTO team_identity_overrides VALUES (1,'api_football',27251,489,2026,-1,'Boise','APPROVED')"))
        self.assertEqual(self.plan()["rows"][0]["home_team_id"], -1)

    def test_existing_identity_conflict_is_held_not_overwritten(self):
        self.assertTrue(run_fixture_discovery(self.engine, Client(), DAY, write=True)["passed"])
        with self.engine.begin() as c:
            c.execute(text("UPDATE fixtures SET league_id=255 WHERE fixture_id=1647413"))
        plan = self.plan()
        self.assertEqual(plan["held"][0]["reason"], "EXISTING_IDENTITY_CONFLICT")
        self.assertEqual(plan["rows"], [])

    def test_missing_invalid_coordinates_and_canonical_alias(self):
        for sql in ("latitude=NULL", "latitude=999", "latitude=0,longitude=0", "canonical_venue_id=999"):
            with self.engine.begin() as c:
                c.execute(text("UPDATE venues SET latitude=43.650530,longitude=-116.271900,canonical_venue_id=NULL"))
                c.execute(text("UPDATE venues SET " + sql))
            plan = self.plan()
            if sql == 'canonical_venue_id=999':
                self.assertEqual(plan['rows'], [])
            else:
                self.assertEqual(plan['rows'][0]['venue_id'], 27774 if sql == 'latitude=NULL' else None)

    def test_exact_event_name_and_direct_reference(self):
        item = payload(1648321)
        item["fixture"]["venue"] = dict(id=None, name="Athletic Club Boise Soccer Stadium", city="Garden City, Idaho")
        self.assertEqual(len(self.plan(item)["rows"]), 1)
        with self.engine.begin() as c:
            c.execute(text("INSERT INTO venue_provider_refs VALUES (27774,'api_football',123,NULL)"))
        item["fixture"]["venue"]["id"] = 123
        self.assertEqual(len(self.plan(item)["rows"]), 1)
        item["fixture"]["venue"]["name"] = "Wrong Stadium"
        self.assertEqual(self.plan(item)["rows"], [])

    def test_ambiguous_event_names(self):
        with self.engine.begin() as c:
            c.execute(text("INSERT INTO venues SELECT 999,name,city,country,latitude,longitude,NULL,NULL FROM venues WHERE venue_id=27774"))
        item = payload(1648321); item["fixture"]["venue"]["name"] = "Athletic Club Boise Soccer Stadium"
        self.assertEqual(self.plan(item)["held"][0]["reason"], "AMBIGUOUS_OR_UNKNOWN_VENUE")

    def test_conflicting_new_natural_ids_both_held(self):
        items = [payload(1647328), payload(1647332)]
        for item in items:
            item['fixture']['venue'] = dict(id=None, name='Athletic Club Boise Soccer Stadium', city='Garden City, Idaho')
        with self.engine.connect() as c:
            plan = plan_fixture_discovery(c, {(489, 2026): items}, START, END)
        self.assertEqual(plan['rows'], [])
        self.assertEqual({h['fixture_id'] for h in plan['held']}, {1647328, 1647332})

    def test_unknown_quota_minute_exhaustion_and_mid_batch_failure(self):
        for quota in (None, dict(daily_remaining=1000, minute_remaining=0)):
            client = Client(); client.quota = quota
            self.assertFalse(run_fixture_discovery(self.engine, client, DAY, write=True)['passed'])
            self.assertEqual(client.requests_made, 0)
        client = Client()
        original = client.fixtures_between
        def partial(league, *args):
            if league == 257: raise RuntimeError('failed fourth scope')
            return original(league, *args)
        client.fixtures_between = partial
        result = run_fixture_discovery(self.engine, client, DAY, write=True)
        self.assertEqual((result['passed'], result['inserted']), (False, 0))
        with self.engine.connect() as c:
            self.assertEqual(c.execute(text('SELECT count(*) FROM fixtures')).scalar(), 1)

    def test_unapproved_scope_and_wrong_payload_scope(self):
        with self.engine.connect() as c:
            self.assertEqual(plan_fixture_discovery(c, {(909, 2026): [payload()]}, START, END)["errors"], ["UNAPPROVED_SCOPE"])
        item = payload(); item["league"]["id"] = 909
        self.assertEqual(self.plan(item)["rows"], [])

    def test_overflow_not_truncated_and_no_write(self):
        items = [payload(i) for i in range(1000, 1051)]
        report = run_fixture_discovery(self.engine, Client(items), DAY, write=True)
        self.assertEqual((report["candidates"], report["overflow"], report["inserted"], report["passed"]), (51, True, 0, False))

    def test_deduplicates_identical_payload_and_rejects_contradiction(self):
        with self.engine.connect() as c:
            duplicate = payload(); duplicate["goals"]["home"] = 3
            for items, expected in (([payload(), payload()], 1), ([payload(), duplicate], 0)):
                plan = plan_fixture_discovery(c, {(489, 2026): items}, START, END)
                self.assertEqual((plan["candidates"], len(plan["rows"])), (1, expected))

    def test_utc_offsets_window_edges_and_naive_rejection(self):
        item = payload(); item["fixture"]["date"] = "2026-11-01T18:00:00-07:00"
        self.assertEqual(len(self.plan(item)["rows"]), 1)
        for stamp in ("2026-11-02T01:00:00", "2026-10-26T23:59:59+00:00", END.isoformat()):
            item["fixture"]["date"] = stamp
            self.assertEqual(self.plan(item)["rows"], [])

    def test_future_completed_and_missing_score_rejected(self):
        for change in ("future", "missing", "negative", "bool"):
            item = payload()
            if change == "future": item["fixture"]["date"] = "2026-11-05T01:00:00+00:00"
            else: item["goals"]["home"] = {"missing": None, "negative": -1, "bool": True}[change]
            self.assertEqual(self.plan(item)["rows"], [])

    def test_quota_budget_timeout_partial_and_no_retry(self):
        client = Client(); client.quota["daily_remaining"] = 100
        self.assertFalse(run_fixture_discovery(self.engine, client, DAY)["passed"])
        self.assertEqual(client.requests_made, 0)
        client = Client()
        self.assertFalse(run_fixture_discovery(self.engine, client, DAY, max_requests=4)["passed"])
        self.assertEqual(client.requests_made, 0)
        for error in (requests.Timeout(), RuntimeError("partial response")):
            client = Client(); client.fixtures_between = Mock(side_effect=error)
            self.assertFalse(run_fixture_discovery(self.engine, client, DAY, write=True)["passed"])
            self.assertEqual(client.fixtures_between.call_count, 1)

    def test_postseason_identifiers_resolve_actual_event_grounds(self):
        # Public identities from the retained postseason audit, not home defaults.
        for fid, league, vid, name, city, home, away, stamp in (
            (1647328, 255, 22800, 'Keyworth Stadium', 'Hamtramck, Michigan', (9043,'Detroit City'), (3995,'Hartford Athletic'), '2026-10-31T00:00:00+00:00'),
            (1647332, 255, 22795, 'Heart Health Park', 'Sacramento, California', (4015,'Sacramento Republic'), (4022,'FC Tulsa'), '2026-11-02T02:00:00+00:00'),
            (1648448, 255, 22795, 'Heart Health Park', 'Sacramento, California', (4015,'Sacramento Republic'), (3993,'El Paso Locomotive'), '2026-11-08T03:00:00+00:00'),
            (1648322, 489, 22805, 'American Legion Memorial Stadium', 'Charlotte, North Carolina', (3991,'Charlotte Independence'), (9025,'Forward Madison'), '2026-11-09T00:00:00+00:00'),
        ):
            with self.subTest(fixture_id=fid):
                item = payload(fid)
                item['league']['id'] = league
                item['fixture']['venue'] = dict(id=None, name=name, city=city)
                item['fixture']['status']['short'] = 'NS'
                item['fixture']['date'] = stamp
                item['goals'] = dict(home=None, away=None)
                item['teams'] = dict(home=dict(id=home[0],name=home[1]), away=dict(id=away[0],name=away[1]))
                with self.engine.begin() as c:
                    for tid, team_name in (home, away):
                        c.execute(text('INSERT OR IGNORE INTO teams VALUES (:id,:name)'), dict(id=tid,name=team_name))
                    c.execute(text('DELETE FROM venues WHERE venue_id=:id'), dict(id=vid))
                    c.execute(text('INSERT INTO venues VALUES (:id,:name,:city,\'USA\',40,-75,NULL,NULL)'), dict(id=vid,name=name,city=city))
                with self.engine.connect() as c:
                    plan = plan_fixture_discovery(c, {(league,2026): [item]}, START, END)
                self.assertEqual(plan['rows'][0]['venue_id'], vid)

    def test_stale_quota_bootstrap_and_exact_request_budget(self):
        client = Client(); client.fresh = False
        report = run_fixture_discovery(self.engine, client, DAY, max_requests=6)
        self.assertEqual((report["passed"], report["provider_requests"]), (True, 6))

    def test_concurrent_insertion_revalidated(self):
        import ingestion.pipeline as pipeline
        original = pipeline.plan_fixture_discovery
        calls = 0
        def race(connection, *args, **kwargs):
            nonlocal calls
            calls += 1
            result = original(connection, *args, **kwargs)
            if calls == 1:
                # Another writer commits the same identity between initial plan and lock.
                row = result["rows"][0]
                from sqlalchemy import MetaData, Table
                with self.engine.begin() as other:
                    table = Table("fixtures", MetaData(), autoload_with=other)
                    other.execute(table.insert().values(**row))
            return result
        with patch.object(pipeline, "plan_fixture_discovery", side_effect=race):
            report = run_fixture_discovery(self.engine, Client(), DAY, write=True)
        self.assertEqual((report["passed"], report["inserted"]), (True, 0))

    def test_real_transport_rejects_partial_date_inventory(self):
        for results, paging in ((2, dict(current=1, total=1)), (1, dict(current=1, total=2)), (None, {})):
            with tempfile.TemporaryDirectory() as tmp:
                client = ApiFootballClient("synthetic-not-a-key", Path(tmp), min_request_interval=0)
                response = Mock(); response.status_code = 200; response.headers = {}
                response.json.return_value = dict(response=[payload()], results=results, paging=paging)
                client.session.get = Mock(return_value=response)
                with self.assertRaises(RuntimeError): client.fixtures_between(489, 2026, "2026-10-27", "2026-12-03")
                self.assertEqual(client.requests_made, 1)

    def test_actual_concurrent_writers_cannot_duplicate(self):
        from concurrent.futures import ThreadPoolExecutor
        with tempfile.TemporaryDirectory() as tmp:
            url = 'sqlite:///' + str(Path(tmp) / 'concurrent.db')
            first, second = database(url), create_engine(url)
            try:
                with ThreadPoolExecutor(max_workers=2) as pool:
                    results = list(pool.map(lambda engine: run_fixture_discovery(engine, Client(), DAY, write=True), [first, second]))
                self.assertEqual(sum(r['inserted'] for r in results), 1)
                self.assertTrue(any(r['passed'] for r in results))
                with first.connect() as c:
                    self.assertEqual(c.execute(text('SELECT count(*) FROM fixtures WHERE fixture_id=1647413')).scalar(), 1)
            finally:
                first.dispose(); second.dispose()

    def test_flag_default_disabled_and_bad_flag_rejected(self):
        import refresh_fixture_states as refresh
        with patch.dict("os.environ", {}, clear=True): self.assertFalse(refresh.fixture_discovery_enabled())
        with patch.dict("os.environ", {"ENABLE_NEW_FIXTURE_DISCOVERY": "maybe"}):
            with self.assertRaises(SystemExit): refresh.fixture_discovery_enabled()


if __name__ == "__main__":
    unittest.main()
