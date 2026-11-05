"""Fresh final preflight evidence only. Read-only SQL and provider GETs; no writer calls."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from dotenv import dotenv_values
from sqlalchemy import create_engine,text
from ingestion.api_football import ApiFootballClient


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--evidence',type=Path,required=True)
    parser.add_argument('--env-file',type=Path,required=True);args=parser.parse_args()
    out=args.evidence.resolve();env=dotenv_values(args.env_file)
    old=json.loads((out/'all-missing-provider-fixtures.json').read_text(encoding='utf-8'))
    old={f['fixture']['id']:f for f in old if f['fixture']['date']>='2026-11-04'}
    ids=sorted(old)
    client=ApiFootballClient(env.get('API_FOOTBALL_KEY') or env['API_SPORTS_KEY'],out/'final-provider-cache')
    fresh={};duplicate=[]
    for i in range(0,len(ids),20):
        if client.requests_made and not client.highlights_quota_available():raise RuntimeError('QUOTA_STOP')
        rows=client.fixtures_by_ids(ids[i:i+20])
        for f in rows:
            fid=f['fixture']['id']
            if fid in fresh:duplicate.append(fid)
            fresh[fid]=f
    def sports(f):
        return {k:f[k] for k in ('fixture','league','teams','goals','score') if k in f}
    changed=[fid for fid in ids if fid in fresh and sports(fresh[fid])!=sports(old[fid])]
    engine=create_engine(env['DATABASE_URL'],connect_args={'connect_timeout':15,'sslmode':'require',
        'options':'-c default_transaction_read_only=on -c statement_timeout=30000'})
    with engine.connect() as c:
        assert c.exec_driver_sql('SHOW transaction_read_only').scalar()=='on'
        present=list(c.execute(text('SELECT fixture_id FROM fixtures WHERE fixture_id=ANY(:ids)'),{'ids':ids}).scalars())
        venue=dict(c.execute(text('SELECT * FROM venues WHERE venue_id=21325')).mappings().one())
        relationships=[dict(r) for r in c.execute(text('SELECT team_id,venue_id,relationship_type,status FROM club_venues WHERE team_id=7711')).mappings()]
        teams=[dict(r) for r in c.execute(text('SELECT team_id,team_name,venue_id FROM teams WHERE team_id IN (7711,4686)')).mappings()]
    engine.dispose()
    result=dict(at=datetime.now(timezone.utc).isoformat(),hosted_read_only=True,hosted_writes=0,
        provider_requests=client.requests_made,quota=client.quota,expected_ids=len(ids),
        provider_returned=len(fresh),missing_provider_ids=sorted(set(ids)-set(fresh)),
        unexpected_provider_ids=sorted(set(fresh)-set(ids)),duplicate_provider_ids=duplicate,
        changed_provider_payload_ids=changed,already_hosted_ids=present,
        cray_canonical_venue=venue,cray_relationships=relationships,cray_teams=teams)
    (out/'final-provider-revalidation.json').write_text(json.dumps(list(fresh.values()),indent=2),encoding='utf-8')
    (out/'final-readonly-revalidation.json').write_text(json.dumps(result,indent=2,default=str),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if not k.startswith('cray_')},indent=2))
    return int(bool(changed or present or duplicate or set(ids)!=set(fresh)))


if __name__=='__main__':
    raise SystemExit(main())
