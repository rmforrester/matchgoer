"""Latest applicable seasons; synthetic owned history, never hosted data."""
import copy
import os
import unittest
from datetime import date, datetime, timezone
from types import SimpleNamespace as Row
from unittest.mock import patch

from football_footprint import attended_competitions, latest_attended_seasons, build_footprint


def attendance(key=1, league=489, season=2026, when='2026-10-24', venue=11):
    return Row(visit_id=key, venue_id=venue, visit_date=date.fromisoformat(when),
               fixture=Row(fixture_id=key, fixture_date=datetime.fromisoformat(when).replace(tzinfo=timezone.utc),
                           league_id=league, league_name='USL League One' if league == 489 else 'League',
                           season=season, country='USA' if league == 489 else 'England'))


class ApplicableSeasonTests(unittest.TestCase):
    def test_usl_retained_in_november_and_after_final_and_across_new_year(self):
        owned=[attendance()]
        for today in [date(2026,11,7),date(2026,12,31),date(2027,1,1),date(2027,3,1)]:
            rows=attended_competitions(owned,[],today)
            self.assertEqual(rows[0]['grounds'][0]['season_visit_ids'],[1])
            self.assertIsNone(rows[0].get('verified_ground_total'))

    def test_next_begun_season_replaces_current_but_keeps_historical_group(self):
        owned=[attendance()];current=latest_attended_seasons(owned,date(2027,3,8),{489:2027})
        rows=attended_competitions(owned,[],date(2027,3,8),current)
        self.assertEqual(rows[0]['season'],2026)
        self.assertEqual(rows[0]['grounds'][0]['visit_ids'],[1])
        self.assertEqual(rows[0]['grounds'][0]['season_visit_ids'],[])

    def test_cross_year_label_and_membership_survive_december_january(self):
        owned=[attendance(league=39,when='2026-09-01')]
        scope=dict(competition_id=39,season=2026,start='2026-08-21',end='2027-05-30',tier=1)
        for today in [date(2026,12,31),date(2027,1,1),date(2027,7,1)]:
            rows=attended_competitions(owned,[],today,scopes=[scope])
            self.assertEqual(rows[0]['season_label'],'2026/27')
            self.assertEqual(rows[0]['grounds'][0]['season_visit_ids'],[1])

    def test_future_published_catalogue_does_not_advance_season(self):
        owned=[attendance()]
        future=dict(competition_id=489,season=2027,start='2027-03-01',end='2027-11-01')
        rows=attended_competitions(owned,[],date(2026,11,7),scopes=[future])
        self.assertEqual(rows[0]['grounds'][0]['season_visit_ids'],[1])

    def test_unknown_boundaries_latest_attended_season_per_competition(self):
        owned=[attendance(1,777,2025,'2025-10-01'),attendance(2,777,2026),attendance(3,888,2024,'2024-06-01')]
        rows=attended_competitions(owned,[],date(2026,11,7))
        self.assertEqual(sorted(i for row in rows for g in row['grounds'] for i in g['season_visit_ids']),[2,3])
        self.assertEqual(sorted(i for row in rows for g in row['grounds'] for i in g['visit_ids']),[1,2,3])

    def test_unique_ground_repeated_visits_historical_and_inputs_preserved(self):
        owned=[attendance(),attendance(2),attendance(3,season=2025,when='2025-10-01')]
        before=copy.deepcopy(owned);rows=attended_competitions(owned,[],date(2026,11,7))
        current=next(r for r in rows if r['season']==2026)
        self.assertEqual(len(current['grounds']),1)
        self.assertEqual(current['grounds'][0]['season_visit_ids'],[1,2])
        self.assertEqual([vars(v) for v in owned],[vars(v) for v in before])

    def test_undated_future_and_missing_season_not_invented(self):
        owned=[attendance(),attendance(2,season=2027,when='2027-03-01')]
        owned[0].visit_date=None
        self.assertEqual(latest_attended_seasons(owned,date(2026,11,7)),{})
        owned[0].visit_date=date(2026,10,24);owned[0].fixture.season=None
        self.assertEqual(latest_attended_seasons(owned,date(2026,11,7)),{})


@unittest.skipUnless(os.getenv('MATCHGOER_LOCAL_POSTGRES_TEST')=='TRUE','Explicit localhost PostgreSQL opt-in')
class ApplicableSeasonPostgresTests(unittest.TestCase):
    def setUp(self):
        from backend.tests import test_build12_history as history
        history.Build12HistoryTests.setUp(self)
        from models import Fixture,VenueVisit,AwayDayReview
        with self.sessions.begin() as db:
            fixture=db.get(Fixture,10)
            fixture.league_id=489;fixture.league_name='USL League One';fixture.season=2026;fixture.country='USA'
            fixture.fixture_date=datetime(2026,10,24,19,tzinfo=timezone.utc)
            fixture.home_team='NY Cosmos';fixture.away_team='Chattanooga Red Wolves'
            db.add_all([VenueVisit(user_id=1,venue_id=1,fixture_id=10,visit_date=date(2026,10,24),source='fixture'),
                        VenueVisit(user_id=2,venue_id=2,visit_date=date(2026,10,24),source='manual')])
        self.addCleanup(self.sessions.close_all)

    def projection(self,today):
        from models import VenueVisit
        from sqlalchemy.orm import joinedload
        with self.sessions() as db:
            visits=db.query(VenueVisit).options(joinedload(VenueVisit.fixture)).filter(VenueVisit.user_id==1).all()
            with patch('football_footprint.membership_catalogue',return_value=dict(reviewed_on='2026-10-17',scopes=[])):
                return build_footprint(db,visits,today)

    def test_api_projection_outside_catalogue_then_actual_rollover_no_mutations(self):
        from models import Fixture
        import main
        from sqlalchemy import text
        def snapshot():
            with self.engine.connect() as c:
                return {t:c.exec_driver_sql('SELECT row_to_json(t)::text FROM '+t+' t ORDER BY 1').scalars().all()
                        for t in ['users','venue_visits','fixtures','venues','away_day_reviews']}
        before=snapshot();old=main.get_my_grounds(self.owner)
        first=self.projection(date(2026,11,7));self.assertEqual(len(first['season_visit_ids']),1)
        self.assertEqual(first['attendance_competitions'][0]['name'],'USL League One')
        self.assertEqual(snapshot(),before);self.assertEqual(main.get_my_grounds(self.owner),old)
        with self.sessions.begin() as db:
            db.add(Fixture(fixture_id=4892027,venue_id=1,home_team='Home',away_team='Away',league_id=489,
                           league_name='USL League One',season=2027,status='NS',fixture_date=datetime(2027,3,8,tzinfo=timezone.utc)))
        for today in [date(2026,11,7),date(2027,3,9)]:
            self.assertEqual(self.projection(today)['season_visit_ids'],first['season_visit_ids'])
        with self.sessions.begin() as db:db.get(Fixture,4892027).status='FT'
        self.assertEqual(self.projection(date(2027,3,7))['season_visit_ids'],first['season_visit_ids'])
        self.assertEqual(self.projection(date(2027,3,8))['season_visit_ids'],[])
        row=self.projection(date(2027,3,8))['attendance_competitions'][0]
        self.assertEqual(row['season'],2026);self.assertEqual(len(row['grounds'][0]['visit_ids']),1)
        self.assertEqual(main.get_my_grounds(self.owner),old)

    def test_postponed_cancelled_awarded_not_start_evidence(self):
        from models import Fixture
        for status in ['TBD','NS','PST','CANC','WO','AWD']:
            with self.sessions.begin() as db:
                row=db.get(Fixture,20);row.league_id=489;row.league_name='USL League One';row.season=2027
                row.status=status;row.fixture_date=datetime(2027,3,8,tzinfo=timezone.utc)
            self.assertEqual(len(self.projection(date(2027,3,9))['season_visit_ids']),1,status)

    def test_actual_api_ratings_totals_and_browser_contract(self):
        import json
        from pathlib import Path
        import main
        from models import Fixture,Venue,VenueVisit,AwayDayReview
        from schemas import MyGroundFootprintResponse
        with self.sessions.begin() as db:
            venue=db.get(Venue,1);venue.name='Hinchliffe Stadium';venue.city='Paterson';venue.country='USA'
            # Synthetic plot coordinates, not a proposed canonical correction.
            venue.latitude=0;venue.longitude=0
            db.add(AwayDayReview(user_id=1,venue_id=1,overall_score=9,recommend=True))
            db.add(Fixture(fixture_id=4892025,venue_id=1,home_team='NY Cosmos',away_team='Historical visitors',league_id=489,
                           league_name='USL League One',country='USA',season=2025,status='FT',fixture_date=datetime(2025,10,24,tzinfo=timezone.utc)))
            db.flush();db.add(VenueVisit(user_id=1,venue_id=1,fixture_id=4892025,visit_date=date(2025,10,24),source='fixture'))
        def api(today):
            with patch('football_footprint.build_footprint',side_effect=lambda db,visits,_today:build_footprint(db,visits,today)),patch('football_footprint.membership_catalogue',return_value=dict(reviewed_on='2026-10-17',scopes=[])):
                result=main.get_my_grounds(self.owner,footprint=True)
            MyGroundFootprintResponse.model_validate(result)
            return result
        lifetime=main.get_my_grounds(self.owner)
        current=api(date(2026,11,7));self.assertEqual(current['grounds'],lifetime)
        self.assertEqual(len(current['footprint']['season_visit_ids']),1)
        self.assertEqual(current['grounds'][0]['visit_count'],2)
        self.assertEqual(current['grounds'][0]['review']['overall_score'],9)
        with self.sessions.begin() as db:
            db.add(Fixture(fixture_id=4892027,venue_id=1,home_team='NY Cosmos',away_team='Next visitors',league_id=489,
                           league_name='USL League One',country='USA',season=2027,status='FT',fixture_date=datetime(2027,3,8,tzinfo=timezone.utc)))
        rolled=api(date(2027,3,8));self.assertEqual(rolled['footprint']['season_visit_ids'],[])
        self.assertEqual(main.get_my_grounds(self.owner),lifetime)
        with self.sessions.begin() as db:db.add(VenueVisit(user_id=1,venue_id=1,fixture_id=4892027,visit_date=date(2027,3,8),source='fixture'))
        attended=api(date(2027,3,8));self.assertEqual(len(attended['footprint']['season_visit_ids']),1)
        self.assertEqual(attended['grounds'][0]['visit_count'],3)
        self.assertEqual(attended['grounds'][0]['review'],current['grounds'][0]['review'])
        target=os.getenv('MATCHGOER_SEASON_BROWSER_FIXTURE_PATH')
        if target:
            Path(target).write_text(json.dumps(dict(current=current,rolled=rolled,next_attended=attended,synthetic=True),default=lambda v:v.isoformat(),indent=2),encoding='utf-8')

    def test_no_historical_fixture_leaks_through_current_home_window(self):
        from backend.tests.test_football_footprint import scope,member
        from models import VenueVisit
        from sqlalchemy.orm import joinedload
        s=scope([member(1,1)]);s.update(competition_id=489,season=2027,start='2027-03-01',end='2027-11-01')
        # The recorded 2026 attendance date is moved into the new window for this
        # regression; canonical fixture season must still control its group.
        with self.sessions.begin() as db:
            row=db.query(VenueVisit).filter_by(user_id=1).one();row.visit_date=date(2027,3,9)
        with self.sessions() as db:
            visits=db.query(VenueVisit).options(joinedload(VenueVisit.fixture)).filter_by(user_id=1).all()
            with patch('football_footprint.membership_catalogue',return_value=dict(reviewed_on='2026-10-17',scopes=[s])),patch('football_footprint.begun_fixture_seasons',return_value={489:2027}):
                r=build_footprint(db,visits,date(2027,3,10))
        self.assertEqual(r['season_visit_ids'],[])
