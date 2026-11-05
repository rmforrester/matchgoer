"""Local only: registry proposal and replayed bounded manifests. Never hosted writes."""
import argparse
from collections import Counter
from datetime import datetime, timezone, timedelta
import hashlib
import json
import re
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from config.leagues import COVERAGE_PROFILES
from ingestion.global_discovery import scope_object,event_proofs
from ingestion.pipeline import plan_fixture_discovery
from ingestion.recovery_preflight import snapshot_database


def save(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,indent=2,default=str),encoding='utf-8')


def build(out):
    matrix=json.loads((out/'coverage-matrix.json').read_text(encoding='utf-8'))
    snapshot=json.loads((out/'public-canonical-snapshot.json').read_text(encoding='utf-8'))
    profiles={(s.league_id,s.provider_season) for scopes in COVERAGE_PROFILES.values() for s in scopes if s.league_id}
    footprint=json.loads((ROOT/'backend/footprint_membership.json').read_text(encoding='utf-8'))
    membership={(s['competition_id'],s['season']) for s in footprint['scopes']}
    membership_starts={(s['competition_id'],s['season']):s['start'] for s in footprint['scopes']}
    membership_ends={(s['competition_id'],s['season']):s['end'] for s in footprint['scopes']}
    reviewed_gap_ids={707,708,709,220,420,147,314,174,212,321,347,121,45,47,48,657,244,66,69,672,81,273,815,357,358,359,384,137,891,892,547,664,1195,761,721,756,393,674,723,90,559,104,105,108,96,97,237,652,404,729,179,181,182,185,732,680,375,143,735,592,593,594,595,596,597,1053,209,1044,206,335,112}
    scopes=[]
    venue_reviews=json.loads((ROOT/'config/discovery_venue_reviews.json').read_text(encoding='utf-8'))
    team_reviews=json.loads((ROOT/'config/discovery_team_reviews.json').read_text(encoding='utf-8'))
    countries=sorted({v['country'] for v in snapshot['venues'] if v.get('country')})
    missing=[]
    for row in matrix:
        lid,season=row['league_id'],row['provider_season'];meta=row['metadata']
        evidence=[]
        if (lid,season) in profiles:evidence.append('config/leagues.py:COVERAGE_PROFILES')
        if (lid,season) in membership:evidence.append('backend/footprint_membership.json:reviewed release catalogue')
        if lid in reviewed_gap_ids:evidence.append('Founder global recovery request 2026-11-04: approved audit gap cohort')
        if lid in {253,255,489,257,1095}:evidence.append('config/leagues.py:NEW_FIXTURE_DISCOVERY_SCOPES (preserved)')
        if lid in {2,3,5,848}:evidence.append('Founder global European knockout discovery request 2026-11-04')
        payload=json.loads((out/f'fixtures-{lid}-{season}.json').read_text(encoding='utf-8'))
        published=row['provider_count']>0
        terminal={'FT','AET','PEN','CANC','ABD','AWD','WO'}
        completed_final=any(re.fullmatch(r'finals?',str(f['league'].get('round','')),re.I) and f['fixture']['status']['short'] in terminal for f in payload) and all(f['fixture']['status']['short'] in terminal for f in payload)
        season_boundary=membership_ends.get((lid,season),
            '2027-06-30' if row['full_season'] else '2026-12-31')
        # Reviewed expiry is deliberately independent of the last published round's metadata end.
        active=published and not completed_final and (row['full_season'] or meta.get('end','')>='2026-11-04' or lid==271)
        cadence='daily' if row['full_season'] or row['missing_ids'] or 'play' in row['league_name'].lower() else 'weekly'
        if not active:cadence='dormant'
        item=dict(country=row['country'],league_id=lid,display_name=row['league_name'],
            provider_season=season,display_season=str(season),venue_countries=countries if row['country']=='World' else [row['country']],
            cadence=cadence,active_from=membership_starts.get((lid,season),'2026-11-04'),active_until=season_boundary,
            review_status='REVIEWED' if evidence and published else 'PENDING_SCOPE_OR_SEASON_REVIEW',
            approval_evidence=evidence or ['No independent approval proof: activation withheld'],
            review_evidence=['coverage-matrix.json','provider-ledger.json'],
            provider_metadata_end=meta.get('end'),completed_final=completed_final,season_readiness_required=row['season']!=season)
        if row['country']=='England':item['venue_countries']=['England','Wales']
        if lid in {61,62,66}:item['venue_countries']=['France','Monaco']
        if row['country']=='Switzerland':item['venue_countries']=['Switzerland','Liechtenstein']
        if lid==253:item['venue_countries']=['USA','Canada']
        scopes.append(item)
        payload=json.loads((out/f'fixtures-{lid}-{season}.json').read_text(encoding='utf-8'))
        missing.extend(f for f in payload if f['fixture']['id'] in set(row['missing_ids']))
    proof=dict(fixture_id=1646909,league_id=45,season=2026,home_team_id=7711,away_team_id=4686,
        kickoff='2026-11-08T14:15:00+00:00',venue_id=21325,venue_name='Flamingo Park',city='London',
        source='https://www.cray-wanderers.com/fa-cup-1st-round-cray-wanderers-vs-stockport-county-sunday-8th-november-2-15-pm/',
        corroboration='https://www.stockportcounty.com/news/2026/october/22/fa-cup-tie-to-be-televised/')
    registry=dict(version=1,reviewed_on='2026-11-04',activation='DISABLED_PENDING_APPROVAL',scopes=scopes,venue_reviews=venue_reviews,team_reviews=team_reviews,event_proofs=[proof])
    save(ROOT/'config/global_fixture_discovery.json',registry)
    save(out/'proposed-recurring-registry.json',registry)
    save(out/'all-missing-provider-fixtures.json',missing)
    save(out/'historical-missing-provider-fixtures.json',[f for f in missing if f['fixture']['date']<'2026-11-04'])
    # Exact existing canonical ground: a coordinate correction is a separate explicit dependency.
    cray_venue=next(v for v in snapshot['venues'] if v['venue_id']==21325)
    save(out/'cray-coordinate-correction-proposal.json',dict(status='PROPOSED_ONLY_NOT_EXECUTED',
        venue_id=21325,preimage=cray_venue,fields=dict(latitude='51.429584',longitude='0.081368'),
        source='https://ksfa.org.uk/venues/cray-wanderers-fc/',
        source_map='https://www.google.com/maps/place/Cray+Wanderers+FC/@51.4295839,0.0787935,17z/data=!3m1!4b1!4m6!3m5!1s0x47d8ab00629b0c01:0x5addfdd0ba3a6268!8m2!3d51.4295839!4d0.0813684',
        reason='Existing point is outside the independently confirmed Flamingo Park site; preserve canonical ID and all supporter links.'))
    engine=snapshot_database(snapshot)
    available={s['league_id']:s for s in scopes}
    # All raw absent candidates are retained, including held rows. Each publication group <=50.
    upcoming=sorted((f for f in missing if f['fixture']['date']>='2026-11-04'),
        key=lambda f:(f['league']['id']!=45,f['fixture']['date'],f['fixture']['id']))
    manifests=[];held=[];locations={};planned=[]
    for n in range(0,len(upcoming),50):
        batch=upcoming[n:n+50];payloads={}
        for f in batch:payloads.setdefault((f['league']['id'],f['league']['season']),[]).append(f)
        allowed=tuple(scope_object(available[k[0]],venue_reviews,team_reviews) for k in payloads if available[k[0]]['review_status']=='REVIEWED')
        start=datetime(2026,11,4,tzinfo=timezone.utc)
        end=max(datetime.fromisoformat(f['fixture']['date']) for f in batch)+timedelta(days=31)
        with engine.connect() as c:
            plan=plan_fixture_discovery(c,payloads,start,end,approved_scopes=allowed,event_proofs=event_proofs(registry))
        for row in plan['rows']:row['fixture_date']=row['fixture_date'].isoformat()
        manifest=dict(window_start=start.isoformat(),window_end_exclusive=end.isoformat(),status='PROPOSED_ONLY_NOT_AUTHORIZED_FOR_HOSTED_WRITE',group=n//50+1,
            snapshot_sha256=hashlib.sha256((out/'public-canonical-snapshot.json').read_bytes()).hexdigest(),
            provider_fixture_ids=[f['fixture']['id'] for f in batch],scope_keys=list(payloads),
            provider_payloads=batch,plan=plan,expected_inserts=plan['rows'],expected_updates=0,expected_deletes=0,
            required_dependencies=['cray-coordinate-correction-proposal.json'] if any(f['fixture']['id']==1646909 for f in batch) else [])
        path=out/'manifests'/f'upcoming-{n//50+1:03}.json';save(path,manifest)
        manifests.append(dict(file=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            candidates=plan['candidates'],inserts=len(plan['rows']),held=len(plan['held']),errors=plan['errors']))
        held.extend(plan['held']);locations.update(plan['location_outcomes']);planned.extend(plan['rows'])
        print(json.dumps(manifests[-1]),flush=True)
    natural=[(r['fixture_date'],r['home_team_id'],r['away_team_id']) for r in planned]
    if len(set(natural)) != len(natural):raise RuntimeError('CROSS_MANIFEST_NATURAL_IDENTITY_CONFLICT')
    save(out/'held-fixtures.json',held)
    save(out/'upcoming-proposed-inserts.json',planned)
    save(out/'recovery-summary.json',dict(missing=len(missing),upcoming=len(upcoming),historical=len(missing)-len(upcoming),
        competitions=len({f['league']['id'] for f in missing}),proposed_inserts=len(planned),held=len(held),
        locations=dict(Counter(locations.values())),manifests=manifests,
        registry_counts=dict(Counter(s['review_status']+':'+s['cadence'] for s in scopes)),hosted_writes=0))
    engine.dispose()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--evidence',type=Path,required=True)
    build(p.parse_args().evidence.resolve())
