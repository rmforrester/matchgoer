"""Recheck automatic venue-policy holds using approved existing catalogue facts.

Same transaction and same hook for both writers. No provider I/O, fixture writes,
home-ground inference, official verification creation, or release of reviewed holds.
"""
from datetime import datetime,timedelta,timezone
from pathlib import Path
from collections import Counter,defaultdict
from types import SimpleNamespace
import hashlib,json
from sqlalchemy import Table,MetaData,select,inspect,update,func

COUNTRIES=('England','Scotland','Wales','Northern-Ireland','Ireland')
AUTOMATIC=('AUTOMATED_CANONICAL_CONFLICT','AUTOMATED_GEOGRAPHIC_CONFLICT')

def reevaluate(connection, *, now=None, items=(), manifest=None, registry=None):
    from backend.fixture_integrity import VENUES,SCHEDULE,RUNS,CURRENT_RUN,identity,utc,serial,venue_geography
    from ingestion.discovery_venues import resolve_event_venue
    from ingestion.venue_identity import normalize_identity
    now=now or datetime.now(timezone.utc);counts=Counter()
    required={'fixtures','venues','venue_names','venue_provider_refs','fixture_venue_verifications','fixture_schedule_integrity','fixture_integrity_runs'}
    if not required<=set(inspect(connection).get_table_names()):
        return dict(status='UNAVAILABLE',released=0,reason='CATALOGUE_TABLES_UNAVAILABLE')
    ft=Table('fixtures',MetaData(),autoload_with=connection)
    candidates=[dict(r)for r in connection.execute(select(ft).join(VENUES,VENUES.c.fixture_id==ft.c.fixture_id)
        .where(ft.c.country.in_(COUNTRIES),ft.c.fixture_date>now,ft.c.status=='NS',
               VENUES.c.state.in_(['DISPUTED','UNRESOLVED']),VENUES.c.actor.in_(AUTOMATIC))).mappings()]
    if not candidates:return dict(status='CHECKED',reviewed=0,released=0,skipped={})
    if registry is None:
        registry=json.loads((Path(__file__).resolve().parents[1]/'config/global_fixture_discovery.json').read_text(encoding='utf-8'))
    reviews={r['venue_id']:r for r in registry.get('venue_reviews',[])}
    scopes={(s['league_id'],s['provider_season']):s for s in registry.get('scopes',[])}
    holdfile=Path(__file__).resolve().parents[1]/'config/fixture_reconciliation_holds.json'
    explicit={r['fixture_id']for r in json.loads(holdfile.read_text(encoding='utf-8'))['holds']}if holdfile.exists()else set()
    ids={r['fixture_id']for r in candidates}
    policies={r['fixture_id']:dict(r)for r in connection.execute(select(VENUES).where(VENUES.c.fixture_id.in_(ids)).with_for_update()).mappings()}
    schedules={r['fixture_id']:dict(r)for r in connection.execute(select(SCHEDULE).where(SCHEDULE.c.fixture_id.in_(ids))).mappings()}
    def read(name):return[dict(r)for r in connection.execute(select(Table(name,MetaData(),autoload_with=connection))).mappings()]
    venues={r['venue_id']:r for r in read('venues')};aliases=read('venue_names');refs=read('venue_provider_refs')
    # Rejected newer observations must veto older accepted sidecars.
    newer={}
    for run in connection.execute(select(RUNS.c.receipt,RUNS.c.started_at,RUNS.c.completed_at)
            .where(func.coalesce(RUNS.c.completed_at,RUNS.c.started_at)>=now-timedelta(days=7)).order_by(func.coalesce(RUNS.c.completed_at,RUNS.c.started_at).desc())).mappings():
        at=utc(run['completed_at']or run['started_at'])
        for d in (run['receipt']or{}).get('lifecycle_decisions',[]):
            fid=d.get('fixture_id')
            if fid in ids and fid not in newer:newer[fid]=(at,d)
    if 'fixture_event_snapshots'in set(inspect(connection).get_table_names()):
        events=Table('fixture_event_snapshots',MetaData(),autoload_with=connection)
        event_times={r['fixture_id']:utc(r['fetched_at'])for r in connection.execute(select(events.c.fixture_id,events.c.fetched_at).where(events.c.fixture_id.in_(ids))).mappings()}
    else:event_times={}
    blocked={r['fixture_id']for r in manifest or[]if r.get('classification')not in {'NO_CHANGE','PROVIDER_STILL_UNRESOLVED','WOULD_UPDATE_TO_FINAL','WOULD_UPDATE_RESCHEDULED','WOULD_UPDATE_OTHER_ALLOWED_STATE'}}
    current=defaultdict(list)
    run=CURRENT_RUN.get()
    if run:
        for fid,values in run.observations.items():
            if fid in ids:current[fid].extend(values)
    from backend.fixture_integrity import observation
    for item in items:
        try:r=observation(item)
        except (KeyError,TypeError,ValueError):continue
        if r['fixture_id']in ids and r not in current[r['fixture_id']]:current[r['fixture_id']].append(r)
    cache={};released=[]
    for f in candidates:
        fid=f['fixture_id'];p=policies[fid];s=schedules.get(fid);cfg=scopes.get((f['league_id'],f['season']))
        if fid in explicit or fid in blocked:counts['EXPLICIT_OR_REJECTED_OBSERVATION_HOLD']+=1;continue
        if p.get('source_url')or p.get('evidence_sha256')or p.get('identity')!=identity(f):counts['REVIEWED_OR_POLICY_IDENTITY_HOLD']+=1;continue
        if any(h.get('source_url')or h.get('evidence_sha256')or h.get('state')=='OFFICIAL_VERIFIED'or(h.get('actor')and not h['actor'].startswith('AUTOMATED_'))for h in p.get('history')or[]):counts['REVIEWED_POLICY_HISTORY']+=1;continue
        if not s or s['schedule_hold']or s['superseded_by']or s['conflicts']or s['identity']!=identity(f):counts['SCHEDULE_HOLD_OR_IDENTITY']+=1;continue
        raw=s['provider_observation'];at=utc(s['observed_at'])
        if fid in newer and newer[fid][0]>=at:
            at,d=newer[fid]
            if not d.get('raw_provider_identity')or 'raw_provider_venue'not in d:
                counts['NEWER_UNUSABLE_OBSERVATION']+=1;continue
            raw={**d['raw_provider_identity'],'fixture_date':d.get('provider_fixture_date'),'venue':d['raw_provider_venue'],'status':d.get('provider_status')}
        if fid in current:
            if len(current[fid])!=1:counts['CONTRADICTORY_CURRENT_OBSERVATIONS']+=1;continue
            raw=current[fid][0];at=now
        if event_times.get(fid,at)>at:counts['NEWER_EVENT_EVIDENCE_REQUIRES_REVIEW']+=1;continue
        if not(timedelta(0)<=now-at<timedelta(days=7)):counts['STALE_EVIDENCE']+=1;continue
        if not cfg or cfg['country']!=f['country']:counts['UNKNOWN_SCOPE']+=1;continue
        try:
            consistent=isinstance(raw,dict)and all(raw.get(k)==f[k]for k in identity(f))and bool(raw.get('fixture_date'))and utc(raw['fixture_date'])==utc(f['fixture_date'])and utc(s['effective_kickoff'])==utc(f['fixture_date'])and s['effective_status']=='NS'and raw.get('status')=='NS'
        except (TypeError,ValueError,OverflowError):consistent=False
        if not consistent:
            counts['FIXTURE_IDENTITY_OR_DATE_CONFLICT']+=1;continue
        venue=raw.get('venue')or{}
        if not isinstance(venue,dict)or not venue.get('name')or not venue.get('city'):counts['MISSING_EXPLICIT_VENUE_EVIDENCE']+=1;continue
        key=(f['country'],tuple(cfg.get('venue_countries',())),json.dumps(venue,sort_keys=True))
        if key not in cache:
            scope=SimpleNamespace(country=f['country'],venue_countries=cfg.get('venue_countries',()),venue_reviews=registry.get('venue_reviews',[]))
            try:cache[key]=resolve_event_venue(venue,scope,venues,refs,aliases)
            except ValueError:cache[key]=(None,'CONFLICT')
        target,method=cache[key]
        if method!='MAP_READY'or target is None:counts['UNRESOLVED_OR_CONFLICTING_VENUE']+=1;continue
        assigned=venues.get(f['venue_id']);root=(assigned.get('canonical_venue_id')or assigned['venue_id'])if assigned else None
        if root!=target:counts['BINDING_CHANGE_REQUIRES_VERIFIED_PUBLICATION']+=1;continue
        review=reviews.get(target);approved=bool(review and review.get('source','').startswith('https://'))
        approved_aliases=[a for a in aliases if a['venue_id']==target and a.get('valid_to')is None and normalize_identity(a['name'])==normalize_identity(venue['name'])and str(a.get('source')or'').startswith('https://')]
        if not approved and not approved_aliases:counts['NO_APPROVED_CATALOGUE_PROVENANCE']+=1;continue
        if venue_geography(f,venues[target])['hold']:counts['GEOGRAPHIC_HOLD']+=1;continue
        evidence=dict(review=review,aliases=approved_aliases,canonical_ground=venues[target])
        fact_hash=hashlib.sha256(json.dumps(serial(evidence),sort_keys=True).encode()).hexdigest()
        history=list(p.get('history')or[])+[{**serial({k:v for k,v in p.items()if k!='history'}),'reason':'VERIFIED_CATALOGUE_REEVALUATION','catalogue_evidence_sha256':fact_hash,'observed_at':at.isoformat()}]
        changed=connection.execute(update(VENUES).where(VENUES.c.fixture_id==fid,VENUES.c.revision==p['revision'],VENUES.c.state==p['state'])
            .values(state='PROVIDER_ASSIGNED',venue_id=target,provider_venue=serial(venue),actor='AUTOMATED_VERIFIED_CATALOGUE_REEVALUATION',revision=p['revision']+1,history=history))
        if changed.rowcount!=1:raise RuntimeError('CATALOGUE_REEVALUATION_PREIMAGE_CHANGED')
        released.append(fid)
    return dict(status='CHECKED',reviewed=len(candidates),released=len(released),released_fixture_ids=sorted(released),skipped=dict(counts),fixture_rows_changed=0,provider_requests=0)
