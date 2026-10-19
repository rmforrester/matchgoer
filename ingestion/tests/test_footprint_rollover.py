import copy
from datetime import date
import unittest

from ingestion.footprint_rollover import propose, digest, encoded


class RolloverTests(unittest.TestCase):
    def setUp(self):
        self.today = date(2026, 10, 19)
        self.member = dict(team_id=1, name='Senior club', venue_id=10,
                           expected_team_venue_id=10, expected_relationships=[],
                           context_venue_ids=[], evidence='https://official.test/home')
        self.old = dict(competition_id=1, season=2025, name='League', country='Country',
                        start='2025-07-01', end='2026-05-31', total=1,
                        complete=True, source='https://official.test/league', members=[self.member])
        self.catalogue = dict(version=1, reviewed_on='2026-10-19', scopes=[self.old])
        self.snapshot = dict(teams=[dict(team_id=1, name='Senior club', venue_id=10),
                                    dict(team_id=2, name='Senior club', venue_id=10)],
                             venues=[dict(venue_id=10, canonical_venue_id=None)], relationships=[])
        scope = {k: copy.deepcopy(v) for k, v in self.old.items() if k not in ('members', 'complete')}
        scope.update(season=2026, start='2026-07-01', end='2027-05-31')
        self.request = dict(competition_id=1, season=2026, scope=scope,
                            membership_verified=True, domestic_league=True,
                            roster=dict(competition_id=1, season=2026, results=1, errors=[],
                                        paging=dict(current=1, total=1), teams=[dict(team=dict(id=1))]))

    def run_plan(self, catalogue=None, requests=None):
        plan = dict(version=1, snapshot_as_of=self.today.isoformat(),
                    snapshot_sha256=digest(self.snapshot), scopes=requests or [self.request])
        return propose(catalogue or self.catalogue, self.snapshot, plan, self.today)

    def test_repeatability_and_idempotency_preserve_history(self):
        original = copy.deepcopy(self.catalogue)
        first = self.run_plan();second = self.run_plan()
        self.assertEqual(encoded(first), encoded(second))
        self.assertEqual(self.catalogue, original)
        self.assertEqual(first['candidate']['scopes'][0], self.old)
        replay = self.run_plan(catalogue=first['candidate'])
        self.assertEqual(replay['candidate'], first['candidate'])
        self.assertEqual(replay['changes'], [])

    def test_calendars_and_expiry(self):
        self.assertEqual(self.run_plan()['summary']['ready_after'], 1)
        self.today = date(2027, 6, 1)
        self.assertEqual(self.run_plan()['summary']['ready_after'], 0)

    def test_promotion_reuses_identity_not_name(self):
        self.request['competition_id'] = self.request['scope']['competition_id'] = 2
        self.request['roster']['competition_id'] = 2
        self.assertTrue(self.run_plan()['candidate']['scopes'][-1]['complete'])
        self.request['roster']['teams'][0]['team']['id'] = 2
        result = self.run_plan()
        self.assertFalse(result['candidate']['scopes'][-1]['complete'])
        self.assertIsNone(result['candidate']['scopes'][-1]['members'][0]['venue_id'])

    def test_participant_changes(self):
        self.request['roster']['teams'][0]['team']['id'] = 2
        result = self.run_plan()
        self.assertEqual(result['changes'][0]['added_participants'], [2])
        self.assertEqual(result['changes'][0]['removed_participants'], [1])

    def test_stale_team_mapping_fails_closed(self):
        self.snapshot['teams'][0]['venue_id'] = 11
        self.assertTrue(self.run_plan()['summary']['review_required'])
        self.assertFalse(self.run_plan()['candidate']['scopes'][-1]['complete'])

    def test_expiring_temporary_home_not_reused_for_whole_season(self):
        rel = dict(venue_id=10, relationship_type='TEMPORARY_HOME', valid_from='2026-01-01', valid_until='2026-12-31')
        self.member['expected_relationships'] = [rel]
        self.snapshot['relationships'] = [dict(team_id=1, status='CURRENT', **rel)]
        self.assertFalse(self.run_plan()['candidate']['scopes'][-1]['complete'])

    def test_changed_role_fingerprint_not_refreshed(self):
        self.snapshot['relationships'] = [dict(team_id=1, status='CURRENT', venue_id=10,
                                              relationship_type='HOME', valid_from=None, valid_until=None)]
        result = self.run_plan()
        self.assertEqual(result['candidate']['scopes'][-1]['members'][0]['expected_relationships'], [])
        self.assertFalse(result['candidate']['scopes'][-1]['complete'])

    def test_approved_equivalence_only(self):
        self.snapshot['venues'].append(dict(venue_id=11, canonical_venue_id=10))
        self.snapshot['teams'][0]['venue_id'] = 11
        self.assertTrue(self.run_plan()['candidate']['scopes'][-1]['complete'])
        self.snapshot['venues'][-1]['canonical_venue_id'] = None
        self.assertFalse(self.run_plan()['candidate']['scopes'][-1]['complete'])

    def test_bad_roster_and_cups_do_not_append(self):
        for field, value in [('membership_verified', False), ('domestic_league', False)]:
            request = copy.deepcopy(self.request);request[field] = value
            self.assertEqual(self.run_plan(requests=[request])['candidate'], self.catalogue)
        self.request['roster']['paging']['total'] = 2
        self.assertEqual(self.run_plan()['candidate'], self.catalogue)

    def test_duplicate_participant_denominator_fails_closed(self):
        self.request['scope']['total'] = self.request['roster']['results'] = 2
        self.request['roster']['teams'] *= 2
        self.assertEqual(self.run_plan()['candidate'], self.catalogue)

    def test_existing_season_never_overwritten(self):
        self.request['season'] = self.request['scope']['season'] = self.request['roster']['season'] = 2025
        result = self.run_plan()
        self.assertEqual(result['candidate'], self.catalogue)
        self.assertEqual(result['exceptions'][0]['reason'], 'existing_season_immutable')

    def test_capacity_is_reported_without_pruning(self):
        for i in range(2, 1001):
            s = copy.deepcopy(self.old);s['competition_id'] = i
            self.catalogue['scopes'].append(s)
        result = self.run_plan()
        self.assertEqual(len(result['candidate']['scopes']), 1001)
        self.assertFalse(result['summary']['runtime_capacity_ok'])
        self.assertTrue(result['summary']['review_required'])

    def test_snapshot_drift_rejected(self):
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            propose(self.catalogue, self.snapshot, dict(version=1, snapshot_sha256='wrong'), self.today)

    def test_proposed_catalogue_byte_limit_fails_closed(self):
        self.request['scope']['name'] = 'x'*(8*1024*1024)
        result = self.run_plan()
        self.assertFalse(result['summary']['runtime_capacity_ok'])
        self.assertIn('runtime_catalogue_byte_limit_exceeded', [e['reason'] for e in result['exceptions']])

    def test_overlapping_seasons_not_appended(self):
        self.request['scope']['start'] = '2026-05-01'
        self.assertEqual(self.run_plan()['candidate'], self.catalogue)

    def test_gap_between_temporary_roles_rejected(self):
        rels = [dict(venue_id=10, relationship_type='TEMPORARY_HOME', valid_from=a, valid_until=b)
                for a,b in [('2026-01-01','2026-11-01'), ('2027-01-01','2027-06-01')]]
        self.member['expected_relationships'] = rels
        self.snapshot['relationships'] = [dict(team_id=1, status='CURRENT', **r) for r in rels]
        self.assertFalse(self.run_plan()['candidate']['scopes'][-1]['complete'])

    def test_shared_ground_preserves_two_clubs_one_physical_home(self):
        other = copy.deepcopy(self.member);other.update(team_id=2, name='Reserve team')
        self.old['members'].append(other);self.old['total'] = 2
        self.request['scope']['total'] = self.request['roster']['results'] = 2
        self.request['roster']['teams'].append(dict(team=dict(id=2)))
        members = self.run_plan()['candidate']['scopes'][-1]['members']
        self.assertEqual(len(members), 2)
        self.assertEqual({m['venue_id'] for m in members}, {10})

    def test_explicit_review_for_incoming_reserve(self):
        self.request['roster']['teams'][0]['team']['id'] = 2
        incoming = copy.deepcopy(self.member);incoming.update(team_id=2, name='Reserve team')
        self.request['reviewed_members'] = [incoming]
        self.assertTrue(self.run_plan()['candidate']['scopes'][-1]['complete'])

    def test_unknown_or_malformed_snapshot_rejected(self):
        self.snapshot['teams'].append(copy.deepcopy(self.snapshot['teams'][0]))
        with self.assertRaisesRegex(ValueError, 'Ambiguous'):
            self.run_plan()

    def test_stale_snapshot_date_rejected(self):
        with self.assertRaisesRegex(ValueError, 'review date'):
            propose(self.catalogue, self.snapshot, dict(version=1, snapshot_sha256=digest(self.snapshot),
                    snapshot_as_of='2026-10-18', scopes=[]), self.today)

    def test_season_boundary_days_inclusive(self):
        for day, count in [('2026-06-30',0), ('2026-07-01',1),
                           ('2027-05-31',1), ('2027-06-01',0)]:
            self.today = date.fromisoformat(day)
            self.assertEqual(self.run_plan()['summary']['ready_after'], count)

    def test_distinct_calendars_do_not_extend_each_other(self):
        calendar = copy.deepcopy(self.request)
        calendar['competition_id'] = calendar['scope']['competition_id'] = calendar['roster']['competition_id'] = 2
        calendar['scope'].update(start='2026-01-01', end='2026-10-18')
        result = self.run_plan(requests=[calendar, self.request])
        self.assertEqual(result['summary']['ready_added'], [[1,2026]])

    def test_existing_active_stale_mapping_is_reported(self):
        self.old.update(start='2026-01-01', end='2026-12-31')
        self.snapshot['teams'][0]['venue_id'] = 11
        result = self.run_plan()
        self.assertIn('existing_active_mapping_stale', [e['reason'] for e in result['exceptions']])
        self.assertEqual(result['summary']['ready_before'], 0)

    def test_cli_refuses_output_over_input(self):
        from ingestion.footprint_rollover import main
        from unittest.mock import patch
        from contextlib import redirect_stderr
        import io
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as folder:
            original = Path(folder)/'candidate.json';original.write_text('private-input-sentinel')
            argv = ['rollover', '--catalogue', str(original), '--snapshot', str(Path(folder)/'snapshot.json'),
                    '--plan', str(Path(folder)/'plan.json'), '--as-of', '2026-10-19', '--output', folder]
            with patch('sys.argv', argv), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                main()
            self.assertEqual(original.read_text(), 'private-input-sentinel')


if __name__ == '__main__':
    unittest.main()
