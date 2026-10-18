"""Real local PostgreSQL integration; no hosted access and no private fixtures."""
import os
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine, text, event
from sqlalchemy.exc import IntegrityError, DBAPIError
from sqlalchemy.orm import Session
from models import Venue, VenueVisit, VenueName, VenueProviderRef, Fixture, User, AwayDayReview, Team
from venue_resolution import VenueResolution, resolution, resolve_venue
import main


class VenueEquivalenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        url = os.environ.get('DATABASE_URL', '')
        if not url.startswith('postgresql://') or '@127.0.0.1:' not in url:
            raise unittest.SkipTest('Isolated local PostgreSQL required')
        cls.engine = create_engine(url)

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, 'engine'): cls.engine.dispose()

    def setUp(self):
        self.connection = self.engine.connect()
        self.transaction = self.connection.begin()
        self.db = Session(bind=self.connection, join_transaction_mode='create_savepoint')
        self.root, self.alias, self.other = 710001, 710002, 710003
        self.db.add_all([Venue(venue_id=self.root, name='Hayes Lane', country='England', city='Bromley', latitude=51, longitude=0),
                         Venue(venue_id=self.alias, name='RELOC8', country='England', city='Bromley'),
                         Venue(venue_id=self.other, name='Hayes Lane', country='England', city='Elsewhere')])
        self.db.add_all([User(user_id=710001), User(user_id=710002)])
        self.db.flush()
        self.db.execute(text('UPDATE venues SET canonical_venue_id=:root, equivalence_source=:source WHERE venue_id=:alias'),
                        dict(root=self.root, alias=self.alias, source='Synthetic reviewed physical identity'))
        self.db.commit()
        self.identity = SimpleNamespace(user_id=710001)
        self.patch = patch.object(main, 'SessionLocal', side_effect=lambda: Session(bind=self.connection, join_transaction_mode='create_savepoint'))
        self.patch.start()

    def tearDown(self):
        self.patch.stop(); self.db.close(); self.transaction.rollback(); self.connection.close()

    def fixture(self, key=710001, venue=None):
        row = Fixture(fixture_id=key, venue_id=venue or self.alias, fixture_date=datetime(2026, 10, 1, 19, tzinfo=timezone.utc),
                      home_team='Bromley', away_team='Synthetic away', league_id=41, season=2026, league_name='League One')
        self.db.add(row); self.db.commit(); return row

    def visit(self, venue, when=None, fixture=None, user=710001):
        row = VenueVisit(user_id=user, venue_id=venue, visit_date=when, fixture_id=fixture, source='manual')
        self.db.add(row); self.db.commit(); return row

    def test_explicit_resolution_not_name_inference(self):
        identity = resolution(self.db)
        self.assertEqual(identity.canonical(self.alias), self.root)
        self.assertEqual(identity.canonical(self.root), self.root)
        self.assertEqual(identity.canonical(self.other), self.other)
        self.assertEqual(identity.equivalents(self.root), {self.root, self.alias})

    def test_missing_venue_is_404(self):
        with self.assertRaises(HTTPException) as caught: resolve_venue(self.db, -1)
        self.assertEqual(caught.exception.status_code, 404)

    def test_invalid_graph_fails_closed(self):
        for links in [{1:1}, {1:2, 2:1}, {1:2, 2:3}, [(1,2),(1,3)], {True:2}]:
            with self.assertRaises(HTTPException): VenueResolution(links)

    def assert_database_rejects(self, sql, **params):
        with self.assertRaises(DBAPIError):
            with self.db.begin_nested(): self.db.execute(text(sql), params)

    def test_self_link_rejected(self):
        self.assert_database_rejects('UPDATE venues SET canonical_venue_id=venue_id, equivalence_source=\'review\' WHERE venue_id=:id', id=self.other)

    def test_missing_target_rejected(self):
        self.assert_database_rejects('UPDATE venues SET canonical_venue_id=-1,equivalence_source=\'review\' WHERE venue_id=:id', id=self.other)

    def test_missing_evidence_rejected(self):
        self.assert_database_rejects('UPDATE venues SET canonical_venue_id=:root WHERE venue_id=:id', id=self.other, root=self.root)

    def test_chain_and_cycle_rejected(self):
        self.assert_database_rejects('UPDATE venues SET canonical_venue_id=:alias,equivalence_source=\'review\' WHERE venue_id=:id', id=self.other, alias=self.alias)
        self.assert_database_rejects('UPDATE venues SET canonical_venue_id=:other,equivalence_source=\'review\' WHERE venue_id=:id', id=self.root, other=self.other)

    def test_reassignment_rejected(self):
        self.assert_database_rejects('UPDATE venues SET canonical_venue_id=:other WHERE venue_id=:id', id=self.alias, other=self.other)

    def test_target_cannot_be_deleted(self):
        self.assert_database_rejects('DELETE FROM venues WHERE venue_id=:id', id=self.root)

    def test_manual_new_visit_stores_root_and_preserves_date(self):
        row = main._ensure_venue_visit(self.db, user_id=710001, venue_id=self.alias, fixture_id=None, visit_date=date(2026, 9, 1), source='manual')
        self.assertEqual((row.venue_id, row.visit_date), (self.root, date(2026, 9, 1)))
        self.db.commit()
        again = main._ensure_venue_visit(self.db, user_id=710001, venue_id=self.root, fixture_id=None, visit_date=date(2026, 9, 1), source='manual')
        self.assertEqual(row.visit_id, again.visit_id)

    def test_historical_alias_visit_returned_without_rewrite(self):
        old = self.visit(self.alias)
        row = main._ensure_venue_visit(self.db, user_id=710001, venue_id=self.root, fixture_id=None, visit_date=None, source='manual')
        self.assertEqual((row.visit_id, row.venue_id), (old.visit_id, self.alias))

    def test_repeat_matchdays_and_owner_isolation(self):
        self.visit(self.alias, date(2026, 9, 1))
        self.visit(self.alias, date(2026, 9, 2), user=710002)
        row = main._ensure_venue_visit(self.db, user_id=710001, venue_id=self.root, fixture_id=None, visit_date=date(2026, 9, 2), source='manual')
        self.assertEqual(row.venue_id, self.root)
        self.assertEqual(self.db.query(VenueVisit).filter(VenueVisit.user_id==710001).count(), 2)

    def test_fixture_confirmation_preserves_fixture_and_raw_fixture(self):
        fixture = self.fixture()
        row = main._ensure_venue_visit(self.db, user_id=710001, venue_id=self.root, fixture_id=fixture.fixture_id, visit_date=None, source='fixture_confirmation')
        self.db.commit()
        again = main._ensure_venue_visit(self.db, user_id=710001, venue_id=self.alias, fixture_id=fixture.fixture_id, visit_date=None, source='fixture_confirmation')
        self.assertEqual(row.visit_id, again.visit_id)
        self.assertEqual(row.venue_id, self.root)
        self.assertEqual(self.db.get(Fixture, fixture.fixture_id).venue_id, self.alias)

    def test_fixture_at_unrelated_ground_rejected(self):
        fixture = self.fixture(venue=self.other)
        with self.assertRaises(HTTPException):
            main._ensure_venue_visit(self.db, user_id=710001, venue_id=self.root, fixture_id=fixture.fixture_id, visit_date=None, source='fixture_confirmation')

    def test_footprint_groups_raw_history_preserving_all_matchdays(self):
        from football_footprint import build_footprint
        from backend.tests.test_football_footprint import member,scope
        first = self.visit(self.alias, date(2026, 9, 1)); second = self.visit(self.root)
        self.visit(self.other, user=710002)
        self.db.add(Team(team_id=710001,team_name='Reviewed club',venue_id=self.root));self.db.commit()
        reviewed=scope([member(710001,self.root)])
        with patch('football_footprint.membership_catalogue',return_value={'reviewed_on':'2026-10-18','scopes':[reviewed]}):
            payload = main.get_my_grounds(self.identity, footprint=True)
        data=payload['grounds']
        self.assertEqual(len(data), 1)
        self.assertEqual((data[0]['venue_id'], data[0]['visit_count'], data[0]['has_undated_visit']), (self.root, 2, True))
        self.assertEqual({v['visit_id'] for v in data[0]['visits']}, {first.visit_id, second.visit_id})
        self.db.expire_all(); self.assertEqual(self.db.get(VenueVisit, first.visit_id).venue_id, self.alias)
        artifact=os.environ.get('MATCHGOER_EQUIVALENCE_TEST_ARTIFACT')
        if artifact:
            import json
            Path(artifact).write_text(json.dumps(payload,default=str,indent=2)+'\n',encoding='utf-8')

    def test_alias_search_and_saved_navigation_return_root(self):
        found = main.search_venues('RELOC8', limit=20)
        self.assertEqual([x['venue_id'] for x in found], [self.root])
        self.assertEqual(main.get_venue(self.alias).venue_id, self.root)

    def test_existing_physical_guide_fact_is_not_lost_under_alias(self):
        from models import VenueGuideFact
        fact=VenueGuideFact(venue_id=self.alias,section='at_ground',topic='Access',content='Synthetic retained fact',
            source_type='official',source_url='https://example.test/ground',reviewed_at=date.today(),confidence='high',status='current')
        self.db.add(fact);self.db.commit()
        guide=main.get_venue_guide(self.root)
        self.assertEqual(guide['venue_id'],self.root)
        self.assertTrue(any(row['content']=='Synthetic retained fact' for section in guide['sections'] for row in section['facts']))
        self.db.expire_all();self.assertEqual(self.db.get(VenueGuideFact,fact.fact_id).venue_id,self.alias)

    def test_legacy_review_is_editable_without_changing_identity(self):
        from schemas import AwayDayReviewUpdate
        review = AwayDayReview(user_id=710001, venue_id=self.alias)
        self.db.add(review); self.db.commit()
        main.update_away_day_review(self.root, AwayDayReviewUpdate(recommend=True, atmosphere_score=8, pubs_score=7, getting_there_score=6, facilities_score=9), self.identity)
        self.db.expire_all(); self.assertEqual(self.db.get(AwayDayReview, review.review_id).venue_id, self.alias)

    def test_conflicting_personal_reviews_fail_closed_and_remain_intact(self):
        from schemas import AwayDayReviewUpdate
        self.db.add_all([AwayDayReview(user_id=710001,venue_id=self.alias), AwayDayReview(user_id=710001,venue_id=self.root)])
        self.db.commit()
        with self.assertRaises(HTTPException) as caught:
            main.update_away_day_review(self.root, AwayDayReviewUpdate(recommend=True), self.identity)
        self.assertEqual(caught.exception.status_code,409)
        self.assertEqual(self.db.query(AwayDayReview).filter(AwayDayReview.user_id==710001).count(),2)

    def test_community_excludes_ambiguous_owner_not_arbitrary_winner(self):
        self.db.add_all([AwayDayReview(user_id=710001,venue_id=self.alias,overall_score=1), AwayDayReview(user_id=710001,venue_id=self.root,overall_score=9), AwayDayReview(user_id=710002,venue_id=self.alias,overall_score=8)])
        self.db.commit()
        score=main.get_away_day_score(self.root)
        self.assertEqual(score['review_count'],1)
        self.assertEqual(score['away_day_score'],8)

    def test_forward_migration_is_idempotent_and_no_auto_activation(self):
        script=(Path(__file__).parents[1]/'migrations/20261018_venue_equivalence.sql').read_text(encoding='utf-8')
        # Run on an independent connection only in the migration-specific harness;
        # inspect the unmapped unrelated venue here to verify no implicit matching.
        self.assertIsNone(self.db.get(Venue,self.other).canonical_venue_id)
        self.assertNotIn('20413',script)

    def test_migration_rehearsal_preserves_rows_and_refuses_active_reversal(self):
        # Release this test's outer synthetic graph lock before the independent DDL connection.
        self.db.close(); self.transaction.rollback(); self.transaction = self.connection.begin()
        import psycopg2
        from uuid import uuid4
        schema='equivalence_test_'+uuid4().hex
        connection=psycopg2.connect(os.environ['DATABASE_URL'], options='-c statement_timeout=15000'); connection.autocommit=True
        cursor=connection.cursor()
        try:
            cursor.execute('CREATE SCHEMA '+schema)
            cursor.execute('SET search_path TO '+schema)
            cursor.execute('CREATE TABLE venues(venue_id integer PRIMARY KEY, name text); CREATE TABLE venue_visits(visit_id integer,user_id integer,venue_id integer,fixture_id integer); CREATE TABLE saved_visit(id integer PRIMARY KEY,venue_id integer REFERENCES venues); INSERT INTO venues VALUES(511,\'Hayes Lane\'),(20413,\'RELOC8\'); INSERT INTO saved_visit VALUES(1,20413)')
            folder=Path(__file__).parents[1]/'migrations'
            forward=(folder/'20261018_venue_equivalence.sql').read_text(encoding='utf-8')
            reverse=(folder/'20261018_venue_equivalence_rollback.sql').read_text(encoding='utf-8')
            cursor.execute(forward); cursor.execute(forward)
            cursor.execute('SELECT count(*) FROM venues WHERE canonical_venue_id IS NOT NULL'); self.assertEqual(cursor.fetchone()[0],0)
            cursor.execute(reverse)
            cursor.execute('SELECT venue_id FROM saved_visit WHERE id=1'); self.assertEqual(cursor.fetchone()[0],20413)
            cursor.execute(forward)
            cursor.execute("CREATE TABLE fixtures(fixture_id integer PRIMARY KEY,venue_id integer); CREATE TABLE terrace_photos(photo_id integer,status text,fixture_id integer,venue_id integer); INSERT INTO fixtures VALUES(1,20413); INSERT INTO terrace_photos VALUES(1,'APPROVED',1,511)")
            with self.assertRaises(psycopg2.Error): cursor.execute(reverse)
            cursor.execute('ROLLBACK')
            cursor.execute('DELETE FROM terrace_photos')
            cursor.execute("UPDATE venues SET canonical_venue_id=511,equivalence_source='Synthetic reviewed Bromley example' WHERE venue_id=20413")
            with self.assertRaises(psycopg2.Error): cursor.execute(reverse)
            cursor.execute('ROLLBACK')
            cursor.execute('SELECT canonical_venue_id FROM venues WHERE venue_id=20413'); self.assertEqual(cursor.fetchone()[0],511)
            cursor.execute('SELECT venue_id FROM saved_visit WHERE id=1'); self.assertEqual(cursor.fetchone()[0],20413)
        finally:
            cursor.execute('ROLLBACK'); cursor.execute('SET search_path TO public')
            cursor.execute('DROP SCHEMA '+schema+' CASCADE'); connection.close()

    def test_one_bulk_link_query_not_per_venue(self):
        statements=[]
        def record(*args):
            if args[2].lstrip().upper().startswith('SELECT'): statements.append(args[2])
        self.db.info.clear(); event.listen(self.connection,'before_cursor_execute',record)
        try:
            for _ in range(1000): self.assertEqual(resolution(self.db).canonical(self.alias), self.root)
        finally: event.remove(self.connection,'before_cursor_execute',record)
        self.assertEqual(len(statements),1)

    def test_new_rating_cannot_duplicate_legacy_alias_rating(self):
        from schemas import AwayDayReviewCreate
        self.db.add(AwayDayReview(user_id=710001,venue_id=self.alias)); self.db.commit()
        with self.assertRaises(HTTPException) as caught:
            main.create_away_day_review(self.root, AwayDayReviewCreate(venue_id=self.root), self.identity)
        self.assertEqual(caught.exception.status_code,409)

    def test_rating_body_and_saved_alias_url_must_match_physical_identity(self):
        from schemas import AwayDayReviewCreate
        row=main.create_away_day_review(self.alias,AwayDayReviewCreate(venue_id=self.root),self.identity)
        self.assertEqual(row.venue_id,self.root)
        with self.assertRaises(HTTPException) as caught:
            main.create_away_day_review(self.alias,AwayDayReviewCreate(venue_id=self.other),self.identity)
        self.assertEqual(caught.exception.status_code,400)

    def test_review_owner_cannot_edit_another_owners_alias(self):
        from schemas import AwayDayReviewUpdate
        self.db.add(AwayDayReview(user_id=710002,venue_id=self.alias)); self.db.commit()
        with self.assertRaises(HTTPException) as caught:
            main.update_away_day_review(self.root,AwayDayReviewUpdate(recommend=True),self.identity)
        self.assertEqual(caught.exception.status_code,404)

    def test_provider_refs_resolve_without_rewriting_provider_provenance(self):
        from ingestion.pipeline import TerraceTalkImporter
        self.db.add_all([VenueProviderRef(venue_id=self.alias,provider='api_football',provider_venue_id=20413,is_primary=True),
                         VenueProviderRef(venue_id=self.root,provider='api_football',provider_venue_id=511,is_primary=True)])
        self.db.commit()
        importer=TerraceTalkImporter.__new__(TerraceTalkImporter)
        importer.venues=Venue.__table__; importer.venue_provider_refs=VenueProviderRef.__table__
        mapped=importer._provider_mapping(self.connection,{20413,511})
        self.assertEqual(mapped,{20413:self.root,511:self.root})
        self.assertEqual(self.db.query(VenueProviderRef).filter_by(provider='api_football',provider_venue_id=20413).one().venue_id,self.alias)

    def test_shared_ground_can_credit_two_clubs_but_not_two_physical_grounds(self):
        from football_footprint import build_footprint
        from backend.tests.test_football_footprint import member,scope
        self.db.add_all([Team(team_id=710001,team_name='Club one',venue_id=self.root),Team(team_id=710002,team_name='Club two',venue_id=self.alias)])
        self.db.commit(); old=self.visit(self.alias,date(2026,9,1))
        reviewed=scope([member(710001,self.root),member(710002,self.alias)])
        with patch('football_footprint.membership_catalogue',return_value={'reviewed_on':'2026-10-18','scopes':[reviewed]}):
            result=build_footprint(self.db,[old],date(2026,10,18))
        competition=result['competitions'][0]
        self.assertEqual((competition['lifetime_clubs'],competition['total_clubs']),(2,2))
        self.assertEqual(len(competition['grounds']),1)

    def test_equivalent_team_home_update_is_not_unrelated_mapping_drift(self):
        from football_footprint import build_footprint
        from backend.tests.test_football_footprint import member,scope
        self.db.add(Team(team_id=710001,team_name='Reviewed club',venue_id=self.root));self.db.commit()
        old=self.visit(self.alias,date(2026,9,1))
        reviewed=scope([member(710001,self.alias)])
        with patch('football_footprint.membership_catalogue',return_value={'reviewed_on':'2026-10-18','scopes':[reviewed]}):
            result=build_footprint(self.db,[old],date(2026,10,18))
        self.assertEqual(result['competitions'][0]['lifetime_clubs'],1)
        self.db.get(Team,710001).venue_id=self.other;self.db.flush()
        with patch('football_footprint.membership_catalogue',return_value={'reviewed_on':'2026-10-18','scopes':[reviewed]}):
            result=build_footprint(self.db,[old],date(2026,10,18))
        self.assertEqual(result['competitions'][0]['coverage'],'incomplete')

    def test_equivalent_fixture_listing_and_navigation_preserve_raw_storage(self):
        fixture=self.fixture()
        listing=main.get_venue_fixtures(self.root, days=3)
        self.assertEqual([row['fixture_id'] for row in listing],[fixture.fixture_id])
        self.assertEqual(self.db.get(Fixture,fixture.fixture_id).venue_id,self.alias)

    def test_league_credit_resolves_history_once_without_away_credit(self):
        from football_footprint import build_footprint
        from backend.tests.test_football_footprint import member, scope
        self.db.add(Team(team_id=710001,team_name='Reviewed home',venue_id=self.root)); self.db.commit()
        one=self.visit(self.alias,date(2026,9,1)); two=self.visit(self.root,date(2026,9,2))
        self.visit(self.other,user=710002)
        reviewed=scope([member(710001,self.root)])
        with patch('football_footprint.membership_catalogue',return_value={'reviewed_on':'2026-10-18','scopes':[reviewed]}):
            result=build_footprint(self.db,[one,two],date(2026,10,18))
        competition=result['competitions'][0]
        self.assertEqual((competition['lifetime_clubs'],competition['season_clubs'],competition['total_clubs']),(1,1,1))
        self.assertEqual(competition['grounds'][0]['venue_id'],self.root)
        self.assertEqual(set(result['season_visit_ids']),{one.visit_id,two.visit_id})


class PhotoEquivalenceTests(unittest.TestCase):
    # Existing synthetic sanitised variants and fake private storage only.
    from backend.tests.test_terraces_b1 import PhotoB1Tests
    setUp=PhotoB1Tests.setUp
    tearDown=PhotoB1Tests.tearDown
    submit=PhotoB1Tests.submit

    def test_new_canonical_attendance_can_submit_for_legacy_alias_fixture(self):
        from models import TerracePhoto
        import terraces_service as service
        root=Venue(name='Synthetic physical root',country='Test');self.db.add(root);self.db.flush()
        raw=self.venue.venue_id
        self.db.execute(text("UPDATE venues SET canonical_venue_id=:root,equivalence_source='synthetic review' WHERE venue_id=:source"),dict(root=root.venue_id,source=raw))
        fixture=Fixture(venue_id=raw,fixture_date=datetime(2026,10,1,tzinfo=timezone.utc),home_team='Home',away_team='Away')
        self.db.add(fixture);self.db.flush();self.db.info.clear()
        self.visit=main._ensure_venue_visit(self.db,user_id=self.owner.user_id,venue_id=raw,fixture_id=fixture.fixture_id,visit_date=None,source='fixture_confirmation')
        self.db.flush()
        self.assertEqual(self.visit.venue_id,root.venue_id)
        identifier=self.submit(label='fixture-canonical-root')['photo_id']
        service.approve(self.db,'Bearer synthetic',identifier)
        photo=self.db.get(TerracePhoto,identifier)
        self.assertEqual(photo.venue_id,root.venue_id)
        self.assertEqual(self.db.get(Fixture,fixture.fixture_id).venue_id,raw)
        self.assertEqual(service.public_page(self.db,self.storage,venue_id=raw)['photos'][0]['photo_id'],identifier)

    def test_existing_photos_keep_raw_identity_but_galleries_resolve(self):
        import terraces_service as service
        from models import TerracePhoto
        old=self.submit(label='legacy')['photo_id']
        service.approve(self.db,'Bearer synthetic',old)
        pending=self.submit(label='private-pending')['photo_id']
        root=Venue(name='Reviewed root',country='Test'); self.db.add(root);self.db.flush()
        raw=self.venue.venue_id
        self.db.execute(text('UPDATE venues SET canonical_venue_id=:root,equivalence_source=\'synthetic review\' WHERE venue_id=:source'),{'root':root.venue_id,'source':raw})
        self.db.info.clear()
        canonical=service.public_page(self.db,self.storage,venue_id=root.venue_id)
        alias=service.public_page(self.db,self.storage,venue_id=raw)
        self.assertEqual([p['photo_id'] for p in canonical['photos']],[old])
        self.assertEqual(canonical,alias)
        self.assertEqual(canonical['photos'][0]['venue_id'],root.venue_id)
        self.assertEqual(self.db.get(TerracePhoto,old).venue_id,raw)
        self.assertNotIn(pending,[p['photo_id'] for p in canonical['photos']])
        self.assertEqual(service.public_page(self.db,self.storage,selection='discover')['photos'][0]['photo_id'],old)
        service.remove(self.db,self.storage,'Bearer synthetic',old)
        self.assertEqual(service.public_page(self.db,self.storage,venue_id=root.venue_id)['photos'],[])


class EquivalentWriteConcurrencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        url=os.environ.get('DATABASE_URL','')
        if not url.startswith('postgresql://') or '@127.0.0.1:' not in url:
            raise unittest.SkipTest('Isolated local PostgreSQL required')
        cls.engine=create_engine(url)

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls,'engine'):cls.engine.dispose()

    def setUp(self):
        self.root,self.alias,self.owner=720001,720002,720001
        with Session(self.engine) as db:
            db.add_all([Venue(venue_id=self.root,name='Synthetic root'),Venue(venue_id=self.alias,name='Synthetic alias'),User(user_id=self.owner)])
            db.flush()
            db.execute(text("UPDATE venues SET canonical_venue_id=:root,equivalence_source='synthetic concurrency' WHERE venue_id=:alias"),dict(root=self.root,alias=self.alias))
            db.add(Fixture(fixture_id=720001,venue_id=self.alias,fixture_date=datetime(2026,10,1,tzinfo=timezone.utc),home_team='Synthetic home',away_team='Synthetic away'))
            db.commit()

    def tearDown(self):
        with self.engine.begin() as connection:
            connection.execute(text('DELETE FROM venues WHERE venue_id IN (720003,720004) AND canonical_venue_id IS NOT NULL'))
            connection.execute(text('DELETE FROM venues WHERE venue_id IN (720003,720004)'))
            for table,condition in [('away_day_reviews','user_id=720001'),('venue_visits','user_id=720001'),('fixtures','fixture_id=720001'),('users','user_id=720001'),('venues','venue_id=720002'),('venues','venue_id=720001')]:
                connection.execute(text('DELETE FROM '+table+' WHERE '+condition))

    def parallel_visits(self,fixture):
        from concurrent.futures import ThreadPoolExecutor
        def attempt(index):
            with Session(self.engine) as db:
                row=main._ensure_venue_visit(db,user_id=self.owner,venue_id=self.root if index%2 else self.alias,
                    fixture_id=720001 if fixture else None,visit_date=date(2026,10,1),source='fixture_confirmation' if fixture else 'manual')
                key=row.visit_id; db.commit(); return key
        with ThreadPoolExecutor(max_workers=4) as workers:keys=list(workers.map(attempt,range(4)))
        self.assertEqual(len(set(keys)),1)
        with Session(self.engine) as db:
            rows=db.query(VenueVisit).filter_by(user_id=self.owner).all()
            self.assertEqual(len(rows),1); self.assertEqual(rows[0].venue_id,self.root)

    def test_parallel_manual_alias_and_root_have_one_identity(self):self.parallel_visits(False)
    def test_parallel_fixture_alias_and_root_have_one_confirmation(self):self.parallel_visits(True)

    def test_parallel_ratings_cannot_create_equivalent_duplicates(self):
        from concurrent.futures import ThreadPoolExecutor
        from schemas import AwayDayReviewCreate
        def attempt(index):
            venue=self.root if index%2 else self.alias
            try:
                main.create_away_day_review(venue,AwayDayReviewCreate(venue_id=venue),SimpleNamespace(user_id=self.owner))
                return 'created'
            except HTTPException as error:
                self.assertEqual(error.status_code,409); return 'existing'
        with patch.object(main,'SessionLocal',lambda:Session(self.engine)),ThreadPoolExecutor(max_workers=4) as workers:
            results=list(workers.map(attempt,range(4)))
        self.assertEqual(results.count('created'),1)
        with Session(self.engine) as db:self.assertEqual(db.query(AwayDayReview).filter_by(user_id=self.owner).count(),1)

    def test_parallel_graph_edits_cannot_create_cycle(self):
        from concurrent.futures import ThreadPoolExecutor
        with Session(self.engine) as db:
            db.add_all([Venue(venue_id=720003,name='Physical A'),Venue(venue_id=720004,name='Physical B')]);db.commit()
        def attempt(pair):
            with Session(self.engine) as db:
                try:
                    db.execute(text("UPDATE venues SET canonical_venue_id=:target,equivalence_source='synthetic race' WHERE venue_id=:source"),dict(source=pair[0],target=pair[1]))
                    db.commit();return 'linked'
                except DBAPIError:db.rollback();return 'rejected'
        with ThreadPoolExecutor(max_workers=2) as workers:results=list(workers.map(attempt,[(720003,720004),(720004,720003)]))
        self.assertEqual(sorted(results),['linked','rejected'])
