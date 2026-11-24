"""CI adapter for existing canonical regression suites; synthetic data only."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

SOURCE = Path('/source')
OUTPUT = Path('/output')
PROFILES = Path('/tmp/canonical-profiles')


def stage():
    manifest = json.loads((SOURCE / 'ops/production_sources.json').read_text())['services']
    results = {}
    for service, profile in manifest.items():
        for target, item in profile['files'].items():
            data = (SOURCE / item['source']).read_bytes()
            assert hashlib.sha256(data).hexdigest() == item['sha256'], (service, target)
            path = PROFILES / service / target
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        results[service] = len(profile['files'])
    (OUTPUT / 'source-profiles.json').write_text(json.dumps(results, indent=2))


def suite(name, root, modules):
    environment = dict(os.environ)
    environment['PYTHONPATH'] = ':'.join(map(str, [root / 'backend', root, root / 'ingestion/tests', root / 'tests']))
    code = '''import json,unittest,sys
suite=unittest.defaultTestLoader.loadTestsFromNames(sys.argv[2:])
result=unittest.TextTestRunner(verbosity=2).run(suite)
summary=dict(tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),skipped=len(result.skipped),passed=result.wasSuccessful())
open('/output/'+sys.argv[1]+'.json','w').write(json.dumps(summary,indent=2))
sys.exit(0 if result.wasSuccessful() else 1)
'''
    return subprocess.run([sys.executable, '-c', code, name, *modules], cwd=root, env=environment).returncode


def coverage():
    sys.path[:0] = [str(SOURCE), str(SOURCE / 'backend')]
    from backend import fixture_coverage as m
    from unittest.mock import patch
    now = '2026-11-24T12:00:00+00:00'
    row = dict(fixture_id=1, country='England', league_id=39, season=2026,
               competition='Premier League', kickoff='2027-05-01T15:00:00+00:00',
               eligible=True, visible=True, held=False, primary_reason=None, ground_id=508)
    with patch.object(m, 'fixture_rows', return_value=[row]):
        a = m.summarize({'snapshot_utc': now}, {})
        b = m.summarize({'snapshot_utc': '2026-11-24T12:00:01+00:00'}, {}, a)
    full = next(r for r in a['leagues'] if r['window_days'] == 'FULL_SEASON')
    assert (full['visible'], full['eligible']) == (1, 1)
    short = next(r for r in a['leagues'] if r['window_days'] == 90)
    assert short['eligible'] == 0 and short['coverage_percent'] is None
    comparable = next(r for r in b['leagues'] if r['window_days'] == 'FULL_SEASON')
    assert comparable['coverage_change_pp'] == 0
    assert 'Full season 1/1' in '\n'.join(m.email_lines(b))
    (OUTPUT / 'full-season-coverage.json').write_text(json.dumps(dict(tests=3, failures=0, errors=0, skipped=0, passed=True)))


if __name__ == '__main__':
    OUTPUT.mkdir(exist_ok=True)
    stage()
    writer = ['test_automatic_venue_reconciliation', 'test_fixture_discovery',
              'test_fixture_integrity', 'test_fixture_refresh_safety',
              'test_global_fixture_discovery', 'test_integrity_writer_integration',
              'test_locality_diagnostic', 'test_stale_venue_locality']
    results = [suite('writer', SOURCE, writer),
               suite('canonical-controls', SOURCE, ['test_monitor_semantics', 'test_production_controls', 'test_production_source']),
               suite('api', PROFILES / 'api', ['backend.tests.test_identity.ClaimProviderVerificationTests',
                     'backend.tests.test_identity.JwksCacheTests', 'backend.tests.test_fixture_integrity_api']),
               suite('photo', PROFILES / 'photo-cleanup', ['backend.tests.test_terraces_cleanup', 'backend.tests.test_terraces_storage'])]
    coverage()
    sys.exit(1 if any(results) else 0)
