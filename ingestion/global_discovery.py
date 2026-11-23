"""Bounded global stages in the existing nightly job; no new scheduler or tables."""
from dataclasses import dataclass
from datetime import date
import hashlib
import json
from pathlib import Path
from config.leagues import COVERAGE_PROFILES

from ingestion.pipeline import run_fixture_discovery

REGISTRY = Path(__file__).resolve().parents[1] / 'config/global_fixture_discovery.json'
CONFIGURED_PROFILE_SCOPES = frozenset((s.country,s.league_id,s.provider_season)
    for scopes in COVERAGE_PROFILES.values() for s in scopes if s.league_id is not None)


def configured_scope(item):
    # Existing ingestion profiles are an independent, explicit source of scope
    # authority. Do not confuse a catalogue review flag with unsupported coverage.
    return item.get('review_status')=='REVIEWED' or (item['country'],item['league_id'],item['provider_season']) in CONFIGURED_PROFILE_SCOPES


@dataclass(frozen=True)
class DiscoveryScope:
    country: str
    league_id: int
    display_name: str
    provider_season: int
    display_season: str
    venue_countries: tuple[str, ...] = ()
    venue_reviews: tuple[dict, ...] = ()
    team_reviews: tuple[dict, ...] = ()
    home_ground_reviews: tuple[dict, ...] = ()


def load_registry(path=REGISTRY):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if data.get('version') != 1 or len(data['scopes']) > 1000:
        raise ValueError('INVALID_DISCOVERY_REGISTRY')
    seen = set()
    for item in data['scopes']:
        key = (item['league_id'],item['provider_season'])
        if key in seen or type(key[0]) is not int or type(key[1]) is not int:
            raise ValueError('INVALID_DISCOVERY_SCOPE')
        seen.add(key)
        if (item['cadence'] not in {'daily','weekly','dormant'} or
                not item.get('approval_evidence') or not item.get('review_evidence') or
                date.fromisoformat(item['active_from']) > date.fromisoformat(item['active_until'])):
            raise ValueError('UNREVIEWED_DISCOVERY_SCOPE')
    return data


def scope_object(item, venue_reviews=None, team_reviews=None, home_ground_reviews=None):
    return DiscoveryScope(**{k:item[k] for k in ('country','league_id','display_name',
        'provider_season','display_season')},venue_countries=tuple(item.get('venue_countries',())),
        venue_reviews=tuple(item.get('venue_reviews',()) if venue_reviews is None else venue_reviews),
        team_reviews=tuple(item.get('team_reviews',()) if team_reviews is None else team_reviews),
        home_ground_reviews=tuple(item.get('home_ground_reviews',()) if home_ground_reviews is None else home_ground_reviews))


def event_proofs(data):
    result = {}
    for p in data.get('event_proofs',[]):
        key = (p['fixture_id'],p['league_id'],p['season'],p['home_team_id'],p['away_team_id'],p['kickoff'])
        if key in result or not p.get('source','').startswith('https://'):
            raise ValueError('INVALID_EVENT_PROOF')
        result[key] = p
    return result


def due_scopes(data, day, country=None):
    """Stable weekly buckets; independent daily/week rotation prevents fixed-prefix starvation."""
    daily,weekly = [],[]
    for item in data['scopes']:
        if not configured_scope(item) or item['league_id'] in {253,255,489,257,1095}:
            continue
        if country is not None and item['country'] != country:
            continue
        # Fixture-derived readiness dates do not prove a configured season is
        # finished. Retry the same reviewed season weekly, including late draws,
        # playoffs and future announcements. Never add an unreviewed ID/season.
        if item['cadence']=='dormant' or not item['active_from'] <= day.isoformat() <= item['active_until']:
            item=dict(item,cadence='weekly',configured_cadence=item['cadence'],readiness_retry=True)
        if item['cadence']=='daily': daily.append(item)
        elif item['cadence']=='weekly':
            identity=f"{item['league_id']}:{item['provider_season']}".encode()
            bucket=int(hashlib.sha256(identity).hexdigest(),16)%7
            if bucket==day.toordinal()%7: weekly.append(item)
    def rotate(items,offset):
        items=sorted(items,key=lambda x:(x['league_id'],x['provider_season']))
        if not items:return []
        shift=offset%len(items)
        return items[shift:]+items[:shift]
    daily=rotate(daily,day.toordinal()//2)
    week=day.toordinal()//7
    # Alternate halves on successive visits to a weekly bucket. Small budget
    # overflows move into the next prefix, rather than waiting behind it for weeks.
    # Each parity subsequence still advances one place, including a one-slot budget.
    weekly=rotate(weekly,week//2+(week%2)*(len(weekly)//2))
    # Alternate classes so weekly work still progresses when daily demand exceeds budget.
    ordered=[]
    classes=(daily,weekly) if day.toordinal()%2==0 else (weekly,daily)
    while daily or weekly:
        for items in classes:
            if items:ordered.append(items.pop(0))
    return ordered


def run_global_discovery(engine,client,day,*,write=False,max_requests=750,
                         discovery_started_at=None,country=None,registry=None):
    """USA runs first in the unchanged stage; this stage shares its 100-request allowance."""
    max_requests=min(max_requests,750)
    data=load_registry() if registry is None else registry
    due=due_scopes(data,day,country)
    stage_initial=client.requests_made
    initial=client.requests_made if discovery_started_at is None else discovery_started_at
    # Leave the existing two-request highlights allowance available.
    ceiling=min(max_requests-2,initial+100)
    capacity=max(0,ceiling-client.requests_made-int(not client.quota_is_fresh()))
    if capacity>1:
        daily=[x for x in due if x['cadence']=='daily']
        weekly=[x for x in due if x['cadence']=='weekly']
        if len(daily)<capacity:
            # Normal operation: every active daily scope precedes weekly overflow.
            due=daily+weekly
        elif weekly:
            # Under exceptional pressure give both classes progress, never a fixed prefix.
            due=daily[:capacity-1]+weekly[:1]+daily[capacity-1:]+weekly[1:]
    report=dict(enabled=True,passed=True,groups=[],deferred_scopes=[],
                shared_request_budget=max_requests,discovery_request_limit=100,
                candidate_limit_per_group=50,inserted=0,held_count=0)
    report['ineligible_scopes']=[]
    for item in data['scopes']:
        if item['league_id'] in {253,255,489,257,1095} or (country is not None and item['country']!=country):
            continue
        reason=None
        if not configured_scope(item):reason='PENDING_SCOPE_OR_SEASON_REVIEW'
        # Reviewed IDs/seasons remain eligible for bounded weekly readiness
        # retries; a date or dormant cadence alone must not lose late fixtures.
        if reason:
            report['ineligible_scopes'].append(dict(league_id=item['league_id'],season=item['provider_season'],
                reason=reason,coverage_attention=False))
            # Catalogue-only, unconfigured candidates are informational. They
            # must not make supported-scope coverage permanently INCOMPLETE.
    report['readiness_retries']=[dict(league_id=x['league_id'],season=x['provider_season'])
        for x in due if x.get('readiness_retry')]
    report['existing_profile_authority']=[dict(league_id=x['league_id'],season=x['provider_season'])
        for x in due if x.get('review_status')!='REVIEWED']
    proofs=event_proofs(data)
    for index,item in enumerate(due):
        needed=1+int(not client.quota_is_fresh())
        if client.requests_made+needed>ceiling or client.failures:
            reason='PRIOR_PROVIDER_FAILURE' if client.failures else 'REQUEST_BUDGET_DEFERRED'
            report['deferred_scopes'].extend(dict(league_id=x['league_id'],season=x['provider_season'],
                reason=reason) for x in due[index:])
            break
        # A single reviewed competition/season is a bounded scope group; never truncate candidates.
        group=run_fixture_discovery(engine,client,day,write=write,max_requests=ceiling,
            approved_scopes=(scope_object(item,data.get('venue_reviews',()),data.get('team_reviews',()),data.get('home_ground_reviews',())),),event_proofs=proofs)
        group.update(league_id=item['league_id'],season=item['provider_season'])
        report['groups'].append(group)
        report['inserted']+=group['inserted']
        report['held_count']+=group.get('held_count',0)
        report['passed'] = report['passed'] and group['passed']
    report['provider_requests']=client.requests_made-stage_initial
    report['shared_discovery_requests_including_usa']=client.requests_made-initial
    report['coverage_complete']=bool(report['passed'] and not report['deferred_scopes'] and
        not any(x['coverage_attention'] for x in report['ineligible_scopes']) and
        all(g['coverage_complete'] for g in report['groups']))
    return report
