import copy
from datetime import date
from types import SimpleNamespace as Row
import unittest
from unittest.mock import patch

from football_footprint import competition_sort_key, membership_catalogue, project_footprint

TODAY = date(2026, 10, 17)


def member(team, venue):
    return dict(team_id=team, name=f'Club {team}', venue_id=venue,
                expected_team_venue_id=venue, expected_relationships=[], context_venue_ids=[venue])


def scope(members=None, **changes):
    members = members or [member(1, 11), member(2, 12)]
    return dict(competition_id=39, season=2026, name='League', country='England',
                start='2026-08-01', end='2027-05-31', complete=True, total=len(members), members=members, **changes)


def visit(key, venue, when=None, league=None, season=2026):
    return Row(visit_id=key, venue_id=venue, visit_date=date.fromisoformat(when) if when else None,
               fixture=Row(league_id=league, season=season) if league else None)


def project(visits, scopes=None, teams=None, **kwargs):
    scopes = scopes or [scope()]
    if teams is None:
        teams = {m['team_id']: Row(venue_id=m['expected_team_venue_id']) for s in scopes for m in s['members']}
    return project_footprint(visits, scopes, teams, {11, 12, 13, 14}, {}, kwargs.get('today', TODAY))


class FootprintTests(unittest.TestCase):
    def test_reviewed_catalogue_is_bounded_and_has_exact_rosters(self):
        data = membership_catalogue()
        self.assertEqual(len(data['scopes']), 274)
        self.assertEqual(sum(s['complete'] for s in data['scopes']), 114)
        self.assertNotIn(1022, {s['competition_id'] for s in data['scopes']})
        self.assertNotIn(1095, {s['competition_id'] for s in data['scopes']})

    def test_pyramid_ordering_uses_explicit_tier_not_name_or_provider_id(self):
        def item(name, tier, key):
            return dict(name=name, tier=tier, competition_id=key, season_label='2026/27')
        items = [item('A league with unknown tier', None, 1), item('League One', 3, 41),
                 item('National League South', 6, 51), item('Premier League', 1, 39),
                 item('National League North', 6, 50), item('Championship', 2, 40)]
        self.assertEqual([x['name'] for x in sorted(items, key=competition_sort_key)],
                         ['Premier League', 'Championship', 'League One', 'National League North',
                          'National League South', 'A league with unknown tier'])

    def test_unknown_tiers_stay_visible_and_have_deterministic_ties(self):
        items = [dict(name=name, competition_id=key, season_label='2026')
                 for name, key in [('Zulu', 1), ('alpha', 3), ('Alpha', 2)]]
        self.assertEqual([x['competition_id'] for x in sorted(items, key=competition_sort_key)], [2, 3, 1])

    def test_output_carries_safe_optional_tier_and_preserves_progress(self):
        low = scope(); low.update(competition_id=41, name='League One', tier=3)
        high = scope(); high.update(name='Premier League', tier=1)
        r = project([visit(1, 11, '2026-09-01')], [low, high])
        self.assertEqual([x['competition_id'] for x in r['competitions']], [39, 41])
        self.assertEqual([x['tier'] for x in r['competitions']], [1, 3])
        self.assertTrue(all(x['season_clubs'] == 1 and x['total_clubs'] == 2 for x in r['competitions']))

    def test_reviewed_priority_mappings_and_remaining_canonical_holds(self):
        data = membership_catalogue()
        by_id = {s['competition_id']: s for s in data['scopes']}
        self.assertEqual(sum('tier' in s for s in data['scopes']), 24)
        self.assertEqual(by_id[253]['tier'], 1)
        self.assertEqual(by_id[255]['tier'], 2)
        self.assertEqual(by_id[489]['tier'], 3)
        norra = by_id[563]
        self.assertTrue(norra['complete'])
        self.assertEqual(norra['total'], 16)
        self.assertEqual(next(m for m in norra['members'] if m['team_id'] == 12585)['venue_id'], 22861)
        self.assertFalse(by_id[593]['complete'])
        self.assertEqual(next(m for m in by_id[593]['members'] if m['team_id'] == 11663)['venue_id'], 27752)
        self.assertTrue(by_id[41]['complete'])
        self.assertEqual(by_id[41]['total'], 24)
        self.assertEqual(next(m for m in by_id[41]['members'] if m['team_id'] == 1832)['venue_id'], 511)
        for lid, team in [(114, 2171)]:
            self.assertFalse(by_id[lid]['complete'])
            self.assertIsNone(next(m for m in by_id[lid]['members'] if m['team_id'] == team)['venue_id'])

    def test_reviewed_current_home_can_differ_from_stale_team_reference_without_rewriting_it(self):
        home = member(1, 12)
        home.update(expected_team_venue_id=11, context_venue_ids=[11, 12])
        visits = [visit(1, 11, '2026-09-01'), visit(2, 12, '2026-09-02')]
        teams = {1: Row(venue_id=11)}
        result = project(visits, [scope([home])], teams=teams)
        self.assertEqual(result['season_visit_ids'], [2])
        self.assertEqual(result['competitions'][0]['season_clubs'], 1)
        self.assertEqual(teams[1].venue_id, 11)
        self.assertEqual([g['clubs'] for g in result['competitions'][0]['grounds']], [[], ['Club 1']])

    def test_lifetime_includes_undated_and_historical_repeat_visits(self):
        result = project([visit(1, 11), visit(2, 11, '1999-01-01'), visit(3, 11, '2026-09-01')])
        c = result['competitions'][0]
        self.assertEqual((c['lifetime_clubs'], c['season_clubs']), (1, 1))
        self.assertEqual(result['season_visit_ids'], [3])

    def test_cup_manual_and_unlinked_visits_at_home_qualify(self):
        result = project([visit(1, 11, '2026-09-01', 999), visit(2, 12, '2026-09-02')])
        self.assertEqual(result['season_visit_ids'], [1, 2])
        self.assertEqual(result['competitions'][0]['season_clubs'], 2)

    def test_neutral_fixture_establishes_season_but_never_home_credit(self):
        result = project([visit(1, 13, '2026-09-01', 39)])
        self.assertEqual(result['season_visit_ids'], [1])
        self.assertEqual(result['competitions'][0]['season_clubs'], 0)
        self.assertEqual(result['competitions'][0]['grounds'][0]['clubs'], [])

    def test_unassociated_date_is_not_guessed(self):
        result = project([visit(1, 13, '2026-09-01'), visit(2, 14)])
        self.assertEqual(result['season_visit_ids'], [])
        self.assertEqual(result['competitions'], [])

    def test_shared_ground_credits_two_clubs_not_two_grounds(self):
        result = project([visit(1, 11, '2026-09-01')], [scope([member(1, 11), member(2, 11)])])
        c = result['competitions'][0]
        self.assertEqual((c['season_clubs'], c['total_clubs'], len(c['grounds'])), (2, 2, 1))

    def test_calendar_year_and_split_year_apply_own_dates(self):
        england = scope()
        sweden = dict(scope(), competition_id=113, start='2026-04-01', end='2026-11-30')
        result = project([visit(1, 11, '2026-05-01'), visit(2, 11, '2026-09-01')], [england, sweden])
        self.assertEqual(result['season_visit_ids'], [1, 2])
        by_id = {c['competition_id']: c for c in result['competitions']}
        self.assertEqual(by_id[39]['grounds'][0]['season_visit_ids'], [2])
        self.assertEqual(by_id[113]['grounds'][0]['season_visit_ids'], [1, 2])
        self.assertEqual(by_id[39]['season_label'], '2026/27')
        self.assertEqual(by_id[113]['season_label'], '2026')

    def test_boundaries_inclusive_future_and_unknown_dates_excluded(self):
        r = project([visit(1, 11, '2026-08-01'), visit(2, 11, '2026-07-31'),
                     visit(3, 11, '2026-10-18'), visit(4, 11)])
        self.assertEqual(r['season_visit_ids'], [1])

    def test_expired_season_not_relabelled_as_current(self):
        self.assertEqual(project([visit(1, 11)], today=date(2027, 6, 1))['competitions'], [])

    def test_missing_or_changed_mapping_withholds_fraction_and_credit(self):
        r = project([visit(1, 11, '2026-09-01')], teams={1: Row(venue_id=99), 2: Row(venue_id=12)})
        self.assertEqual(r['competitions'][0]['coverage'], 'incomplete')
        self.assertIsNone(r['competitions'][0]['season_clubs'])
        self.assertEqual(r['season_visit_ids'], [])

    def test_incomplete_competition_remains_relevant(self):
        s = scope(); s['complete'] = False
        r = project([visit(1, 11)], [s])
        self.assertEqual(len(r['competitions']), 1)
        self.assertIsNone(r['competitions'][0]['lifetime_clubs'])

    def test_new_explicit_relationship_fails_closed(self):
        s = scope()
        r = project_footprint([visit(1, 11, '2026-09-01')], [s], {1: Row(venue_id=11), 2: Row(venue_id=12)},
                              {11, 12}, {1: [Row(venue_id=13, relationship_type='HOME', valid_from=None, valid_until=None)]}, TODAY)
        self.assertEqual(r['season_visit_ids'], [])
        self.assertEqual(r['competitions'][0]['coverage'], 'incomplete')

    def test_club_movement_does_not_transfer_old_ground_credit(self):
        m = member(1, 12)
        r = project([visit(1, 11, '2026-09-01'), visit(2, 12, '1999-01-01')], [scope([m])])
        self.assertEqual(r['competitions'][0]['lifetime_clubs'], 1)
        self.assertEqual(r['competitions'][0]['season_clubs'], 0)

    def test_old_fixture_season_does_not_classify_unknown_ground(self):
        self.assertEqual(project([visit(1, 13, '2026-09-01', 39, 2025)])['season_visit_ids'], [])

    def test_does_not_mutate_attendance_or_expose_membership_ids(self):
        visits = [visit(1, 11, '2026-09-01')]; before = copy.deepcopy(visits)
        r = project(visits)
        self.assertEqual(vars(visits[0]), vars(before[0]))
        self.assertNotIn('team_id', str(r))
        self.assertNotIn('expected_', str(r))
        self.assertNotIn('Club 2', str(r))


class OwnedFootprintContractTests(unittest.TestCase):
    """Uses the existing isolated PostgreSQL test harness, never a hosted DB."""
    def test_large_history_uses_constant_query_count_and_owner_projection(self):
        import json
        import time
        from database import engine
        from sqlalchemy import event
        from sqlalchemy.orm import Session
        from models import User, Venue, VenueVisit, Team
        from identity import ResolvedIdentity
        from main import get_my_grounds
        db = Session(engine)
        user = User(is_anonymous=False, account_status='registered')
        venue = Venue(name='Synthetic performance ground', country='England')
        team = None
        statements = []
        def count_queries(conn, cursor, statement, parameters, context, many):
            statements.append(statement.split()[0])
        try:
            db.add_all([user, venue]); db.flush()
            team = Team(team_name='Synthetic performance club', venue_id=venue.venue_id)
            db.add(team); db.flush()
            db.add_all([VenueVisit(user_id=user.user_id, venue_id=venue.venue_id, visit_date=TODAY, source='manual') for _ in range(1000)])
            db.commit()
            identity = ResolvedIdentity(user.user_id, 'registered', True, 'bearer')
            reviewed_scope = scope([member(team.team_id, venue.venue_id)])
            # Keep this deterministic when the suite runs after this season.
            reviewed_scope.update(start='2000-01-01', end='2099-12-31')
            event.listen(engine, 'before_cursor_execute', count_queries)
            start = time.perf_counter()
            with patch('football_footprint.membership_catalogue', return_value={'reviewed_on': '2026-10-17', 'scopes': [reviewed_scope]}):
                result = get_my_grounds(identity=identity, footprint=True)
            elapsed = (time.perf_counter() - start) * 1000
            event.remove(engine, 'before_cursor_execute', count_queries)
            self.assertEqual(len(result['grounds']), 1)
            self.assertEqual(result['grounds'][0]['visit_count'], 1000)
            self.assertEqual(len(result['footprint']['season_visit_ids']), 1000)
            self.assertEqual(statements, ['SELECT'] * 8)  # one bulk identity map + root metadata, independent of visits
            print('FOOTPRINT_PERFORMANCE ' + json.dumps({'visits': 1000, 'queries': len(statements), 'elapsed_ms': round(elapsed, 2), 'response_bytes': len(json.dumps(result, default=str))}))
        finally:
            if event.contains(engine, 'before_cursor_execute', count_queries):
                event.remove(engine, 'before_cursor_execute', count_queries)
            db.rollback()
            if user.user_id:
                db.query(VenueVisit).filter_by(user_id=user.user_id).delete()
                db.query(User).filter_by(user_id=user.user_id).delete()
            if team is not None:
                db.query(Team).filter_by(team_id=team.team_id).delete()
            if venue.venue_id:
                db.query(Venue).filter_by(venue_id=venue.venue_id).delete()
            db.commit(); db.close()

    def test_default_contract_and_opt_in_both_remain_owner_scoped(self):
        from database import engine
        from sqlalchemy.orm import Session
        from models import User, Venue, VenueVisit
        from identity import ResolvedIdentity
        from main import get_my_grounds
        from schemas import MyGroundFootprintResponse
        db = Session(engine)
        users, venues = [], []
        try:
            users = [User(is_anonymous=False, account_status='registered') for _ in range(2)]
            venues = [Venue(name=f'Private synthetic {i}', country='England') for i in range(2)]
            db.add_all(users + venues); db.flush()
            for user, venue in zip(users, venues):
                db.add(VenueVisit(user_id=user.user_id, venue_id=venue.venue_id, visit_date=TODAY, source='manual'))
            db.commit()
            with patch('football_footprint.membership_catalogue', return_value={'reviewed_on': '2026-10-17', 'scopes': []}):
                for user, venue in zip(users, venues):
                    identity = ResolvedIdentity(user.user_id, 'registered', True, 'bearer')
                    ordinary = get_my_grounds(identity=identity)
                    self.assertIsInstance(ordinary, list)
                    self.assertEqual([g['venue_id'] for g in ordinary], [venue.venue_id])
                    enriched = get_my_grounds(identity=identity, footprint=True)
                    self.assertEqual(enriched['grounds'], ordinary)
                    parsed = MyGroundFootprintResponse.model_validate(enriched)
                    self.assertEqual(len(parsed.grounds), 1)
                    self.assertEqual(parsed.footprint.season_visit_ids, [])
                    self.assertNotIn('user_id', parsed.model_dump_json())
        finally:
            db.rollback()
            for user in users:
                db.query(VenueVisit).filter_by(user_id=user.user_id).delete()
                db.query(User).filter_by(user_id=user.user_id).delete()
            for venue in venues:
                db.query(Venue).filter_by(venue_id=venue.venue_id).delete()
            db.commit(); db.close()


if __name__ == '__main__':
    unittest.main()
