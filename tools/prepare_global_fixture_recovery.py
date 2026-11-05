"""Read-only provider/hosted evidence capture. No ingestion or hosted writer import."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dotenv import dotenv_values
from sqlalchemy import create_engine, text
from ingestion.api_football import ApiFootballClient


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, default=str), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--env-file', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    env = dotenv_values(args.env_file)
    engine = create_engine(env['DATABASE_URL'], connect_args={
        'connect_timeout': 15, 'sslmode': 'require',
        'options': '-c default_transaction_read_only=on -c statement_timeout=30000'},
        isolation_level='REPEATABLE READ')
    snapshot = out / 'public-canonical-snapshot.json'
    if not snapshot.exists():
        with engine.connect() as c:
            assert c.exec_driver_sql('SHOW transaction_read_only').scalar() == 'on'
            data = {name: [dict(r) for r in c.execute(text('SELECT * FROM ' + name)).mappings()]
                    for name in ('fixtures', 'teams', 'venues', 'venue_provider_refs',
                                 'venue_names', 'team_identity_overrides', 'club_venues')}
            save(snapshot, data)
            save(out / 'snapshot-receipt.json', dict(read_only=True,
                at=datetime.now(timezone.utc).isoformat(),
                sha256=hashlib.sha256(snapshot.read_bytes()).hexdigest(),
                tables={k: len(v) for k, v in data.items()}, hosted_writes=0))
    else:
        data = json.loads(snapshot.read_text(encoding='utf-8'))
    inventory = {}
    for f in data['fixtures']:
        if f['country'] == 'USA' and f['league_id'] not in {253,255,256,257,489,1095}:
            continue
        key = f['league_id']
        if key not in inventory or f['season'] > inventory[key]['season']:
            inventory[key] = {k: f[k] for k in ('league_id','league_name','country','season')}
    client = ApiFootballClient(env.get('API_FOOTBALL_KEY') or env['API_SPORTS_KEY'], out / 'provider-cache')
    ledger_path = out / 'provider-ledger.json'
    ledger = json.loads(ledger_path.read_text()) if ledger_path.exists() else []
    def fetch(endpoint, filename, **params):
        path = out / filename
        if path.exists():
            return json.loads(path.read_text(encoding='utf-8'))
        if client.requests_made >= 600:
            raise RuntimeError('INVESTIGATION_REQUEST_CAP')
        if client.requests_made and not client.highlights_quota_available():
            raise RuntimeError('QUOTA_UNAVAILABLE')
        rows = client.get(endpoint, use_cache=False, **params)
        if client.quota is None or client.quota['daily_remaining'] < 1000:
            raise RuntimeError('INVESTIGATION_RESERVE')
        save(path, rows)
        ledger.append(dict(endpoint=endpoint, params=params, results=len(rows),
            at=datetime.now(timezone.utc).isoformat(), quota=client.quota,
            sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
        save(ledger_path, ledger)
        return rows
    metadata = {}
    for season in (2026,2027):
        for league in fetch('/leagues', f'leagues-{season}.json', season=season):
            for se in league['seasons']:
                if se['year'] == season:
                    metadata[(league['league']['id'],season)] = dict(
                        country=league['country']['name'], name=league['league']['name'],
                        type=league['league']['type'], **se)
    existing = {f['fixture_id'] for f in data['fixtures']}
    matrix = []
    # FA Cup first; full current cup seasons retain historical recovery IDs.
    for lid, inv in sorted(inventory.items(), key=lambda pair: (pair[0] != 45, pair[1]['country'],pair[0])):
        season = inv['season'] if inv['season'] >= 2026 else 2026
        meta = metadata.get((lid,season), {})
        full = meta.get('type') == 'Cup'
        params = dict(league=lid,season=season)
        if not full:
            params.update({'from':'2026-10-28','to':'2026-12-04'})
        rows = fetch('/fixtures', f'fixtures-{lid}-{season}.json', **params)
        if any((f['league']['id'],f['league']['season']) != (lid,season) for f in rows):
            raise RuntimeError('PROVIDER_SCOPE_MISMATCH')
        if len({f['fixture']['id'] for f in rows}) != len(rows):
            raise RuntimeError('DUPLICATE_PROVIDER_IDS')
        missing = [f for f in rows if f['fixture']['id'] not in existing]
        matrix.append(dict(**inv, provider_season=season, full_season=full,
            metadata=meta, provider_count=len(rows), missing_ids=[f['fixture']['id'] for f in missing],
            upcoming_ids=[f['fixture']['id'] for f in missing if f['fixture']['date'] >= '2026-11-04']))
        save(out / 'coverage-matrix.json', matrix)
        print(json.dumps(dict(done=len(matrix),league_id=lid,provider=len(rows),missing=len(missing))),flush=True)
    save(out / 'capture-complete.json', dict(scopes=len(matrix), requests_this_execution=client.requests_made,
        total_requests=len(ledger),quota=client.quota,hosted_writes=0))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('STOP', type(error).__name__, flush=True)
        sys.exit(1)
