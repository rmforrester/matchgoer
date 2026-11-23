"""Read-only Discover coverage, retained in the existing reconciliation receipt.

Coverage describes stored fixtures, not completeness against a provider schedule.
It never releases holds or changes reconciliation/alert outcomes.
"""
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
import json, math

VERSION = 'discover-full-season-stored-v2'
WINDOWS = (7, 14, 30, 90)
PERIODS = ('FULL_SEASON', *WINDOWS)
BRITISH_IRISH = {'England', 'Scotland', 'Wales', 'Northern-Ireland', 'Ireland'}


def stamp(value):
    result = value if isinstance(value, datetime) else datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('COVERAGE_REQUIRES_UTC_OFFSET')
    return result


def valid_coordinates(ground):
    try:
        a, b = float(ground['latitude']), float(ground['longitude'])
        return math.isfinite(a) and math.isfinite(b) and -90 <= a <= 90 and -180 <= b <= 180 and (a, b) != (0, 0)
    except (TypeError, ValueError, KeyError):
        return False


def definitions(registry=None):
    from config.leagues import COVERAGE_PROFILES, NEW_FIXTURE_DISCOVERY_SCOPES
    if registry is None:
        registry = json.loads((Path(__file__).resolve().parents[1] / 'config/global_fixture_discovery.json').read_text(encoding='utf-8'))
    result = {}
    for profile in [*COVERAGE_PROFILES.values(), NEW_FIXTURE_DISCOVERY_SCOPES]:
        for scope in profile:
            if scope.league_id is not None:
                result[(scope.league_id, scope.provider_season)] = dict(country=scope.country, competition=scope.display_name, display_season=scope.display_season)
    for scope in registry['scopes']:
        key = scope['league_id'], scope['provider_season']
        if scope.get('review_status') == 'REVIEWED' or key in result:
            result[key] = {**result.get(key, {}), 'country':scope['country'], 'competition':scope['display_name']}
    return result


def fixture_rows(snapshot):
    """SQL serving predicates plus the actual geographic-query/projection checks."""
    from backend.fixture_integrity import ACTIVE, venue_geography
    venues = {r['venue_id']: r for r in snapshot['venues']}
    schedules = {r['fixture_id']: r for r in snapshot['schedule']}
    policies = {r['fixture_id']: r for r in snapshot['policies']}
    sql_ids = set(snapshot['actual_api_sql_eligible_ids'])
    out = []
    for fixture in snapshot['fixtures']:
        fid = fixture['fixture_id']; side = schedules.get(fid, {}); policy = policies.get(fid)
        kickoff = stamp(side.get('effective_kickoff') or fixture['fixture_date'])
        status = side.get('effective_status') or fixture['status']
        excluded = status not in ACTIVE or side.get('superseded_by') is not None
        assigned = venues.get(fixture['venue_id'])
        root = venues.get(assigned.get('canonical_venue_id') or assigned['venue_id']) if assigned else None
        geo = venue_geography(fixture, root, verification=policy)
        # /nearby filters the assigned row before projecting its canonical root.
        original_queryable = bool(assigned and assigned['latitude'] is not None and assigned['longitude'] is not None
                                  and -90 <= float(assigned['latitude']) <= 90 and -180 <= float(assigned['longitude']) <= 180)
        visible = not excluded and fid in sql_ids and original_queryable and valid_coordinates(root) and not geo['hold']
        reason = None
        if not visible:
            if excluded: reason = 'STATUS_OR_SUPERSESSION_EXCLUDED'
            elif side.get('schedule_hold'): reason = 'SCHEDULE_INTEGRITY_HOLD'
            elif geo['hold']: reason = 'GEOGRAPHIC_INTEGRITY_HOLD'
            elif policy and policy['state'] in ('DISPUTED', 'UNRESOLVED'): reason = 'VENUE_POLICY_HOLD'
            elif not assigned: reason = 'CANONICAL_GROUND_UNRESOLVED'
            elif not original_queryable or not valid_coordinates(root): reason = 'MISSING_OR_INVALID_COORDINATES'
            else: reason = 'OTHER_DISCOVER_RESTRICTION'
        out.append(dict(fixture_id=fid, country=fixture['country'], league_id=fixture['league_id'], season=fixture['season'],
                        competition=fixture['league_name'], kickoff=kickoff.isoformat(), eligible=not excluded,
                        visible=visible, held=bool(side.get('schedule_hold')or(policy and policy['state']in ('DISPUTED','UNRESOLVED'))),
                        primary_reason=reason, ground_id=root['venue_id'] if root else None))
    return out


def summarize(snapshot, scope_definitions, previous=None):
    now = stamp(snapshot['snapshot_utc']); rows = fixture_rows(snapshot)
    scopes = dict(scope_definitions)
    for row in rows:
        scopes.setdefault((row['league_id'], row['season']), dict(country=row['country'], competition=row['competition']))
    prior = {(r['league_id'], r['season'], r['window_days']): r for r in (previous or {}).get('leagues', [])}
    comparable = bool(previous and previous.get('status') == 'CHECKED' and previous.get('version') == VERSION
                      and stamp(previous['snapshot_utc']) < now)
    leagues = []
    grouped = defaultdict(list)
    for row in rows: grouped[(row['league_id'], row['season'])].append(row)
    for key, scope in sorted(scopes.items()):
        for days in PERIODS:
            selected = [r for r in grouped[key] if now <= stamp(r['kickoff']) and (days=='FULL_SEASON'or stamp(r['kickoff']) < now + timedelta(days=days))]
            eligible = [r for r in selected if r['eligible']]
            visible = sum(r['visible'] for r in eligible); den = len(eligible)
            reasons = dict(Counter(r['primary_reason'] for r in eligible if not r['visible']))
            assert sum(reasons.values()) == den - visible
            percent = round(visible * 100 / den, 4) if den else None
            old = prior.get((*key, days)) if comparable else None
            delta = round(percent - old['coverage_percent'], 4) if old and percent is not None and old['coverage_percent'] is not None else None
            leagues.append(dict(league_id=key[0], season=key[1], country=scope['country'], competition=scope['competition'],
                                window_days=days, stored=len(selected), eligible=den, visible=visible, missing=den-visible,
                                held=sum(r['held']for r in eligible), display_season=scope.get('display_season'),
                                scheduled_season_end_utc=scope.get('scheduled_season_end_utc'),
                                season_end_evidence_status='VERIFIED'if scope.get('scheduled_season_end_utc')else'NOT_VERIFIED_ALL_STORED_FUTURE_INCLUDED',
                                last_stored_kickoff=max((r['kickoff']for r in selected),default=None),
                                ingestion_completeness_status='NOT_VERIFIED',
                                excluded=len(selected)-den, coverage_percent=percent, primary_reasons=reasons,
                                below_95_percent=bool(den and visible/den < .95),
                                coverage_change_pp=delta, inventory_change=den-old['eligible'] if old else None,
                                comparison='ROLLING_WINDOWS_SAME_ELIGIBILITY_VERSION' if old else 'BASELINE_UNAVAILABLE',
                                status='NO CURRENT INVENTORY' if not den else 'CHECKED'))
    totals = {}
    for label in ['Worldwide', 'British & Irish', *sorted({r['country']for r in leagues})]:
        totals[label] = {}
        for days in PERIODS:
            selected = [r for r in leagues if r['window_days']==days and (label=='Worldwide' or (r['country'] in BRITISH_IRISH if label=='British & Irish'else r['country']==label))]
            den=sum(r['eligible']for r in selected); vis=sum(r['visible']for r in selected)
            old=(previous or {}).get('totals',{}).get(label,{}).get(str(days)) if comparable else None
            percent=round(100*vis/den,4)if den else None
            totals[label][str(days)] = dict(stored=sum(r['stored']for r in selected),eligible=den, visible=vis, missing=den-vis,
                held=sum(r['held']for r in selected),excluded=sum(r['excluded']for r in selected),coverage_percent=percent,
                coverage_change_pp=round(percent-old['coverage_percent'],4)if old and percent is not None and old.get('coverage_percent')is not None else None,
                inventory_change=den-old['eligible']if old else None)
    return dict(status='CHECKED', version=VERSION, snapshot_utc=now.isoformat(), primary_period='FULL_SEASON',windows_days=list(WINDOWS), leagues=leagues, totals=totals,
                previous_snapshot_utc=previous['snapshot_utc']if comparable else None,
                comparison_note='Full-season counts retain competition-season identity and all stored future dates. Changes include inventory effects; secondary rolling windows also include boundary effects. Not proof of official schedule completeness or a causal publication measurement.',
                stored_inventory_only=True, alert_conditions_changed=False)


def collect(connection, now, previous=None):
    """Caller supplies one read-only repeatable-read connection; no writes/provider I/O."""
    from sqlalchemy import text, Table, MetaData, select
    from sqlalchemy.orm import registry
    from backend.fixture_integrity import eligibility_query
    def q(sql, **params): return [dict(r)for r in connection.execute(text(sql), params).mappings()]
    fixtures = q('''SELECT f.* FROM fixtures f LEFT JOIN fixture_schedule_integrity s USING(fixture_id)
                    WHERE coalesce(s.effective_kickoff,f.fixture_date)>=:start''', start=now)
    ids=[r['fixture_id']for r in fixtures]
    snapshot=dict(snapshot_utc=now.isoformat(), fixtures=fixtures,
                  schedule=q('SELECT * FROM fixture_schedule_integrity WHERE fixture_id=ANY(:ids)',ids=ids),
                  policies=q('SELECT * FROM fixture_venue_verifications WHERE fixture_id=ANY(:ids)',ids=ids),
                  venues=q('SELECT * FROM venues'))
    table=Table('fixtures',MetaData(),autoload_with=connection)
    class Fixture: pass
    mapper=registry();mapper.map_imperatively(Fixture,table)
    try:
        query,kickoff=eligibility_query(select(Fixture.fixture_id),SimpleNamespace(connection=lambda:connection),Fixture)
        snapshot['actual_api_sql_eligible_ids']=list(connection.execute(query.where(kickoff>=now)).scalars())
        return summarize(snapshot,definitions(),previous)
    finally:mapper.dispose()


def email_lines(coverage):
    if not coverage or coverage.get('status')!='CHECKED' or coverage.get('version')!=VERSION:
        return ['Full-season Discover coverage: unavailable or legacy window-only evidence; no full-season coverage pass claimed.']
    lines=[]
    for scope in ['Worldwide','British & Irish']:
        values=[]
        for days in PERIODS:
            r=coverage['totals'][scope][str(days)];percent=r['coverage_percent'];delta=r['coverage_change_pp']
            period='Full season'if days=='FULL_SEASON'else f'{days}d'
            values.append(f"{period} {r['visible']}/{r['eligible']} ({percent:.2f}%, {delta:+.2f}pp)"if percent is not None and delta is not None else f"{period} {r['visible']}/{r['eligible']} ({percent:.2f}%)"if percent is not None else f'{period} NO CURRENT INVENTORY')
        lines.append(scope+' Discover: '+ '; '.join(values))
    gaps=[r for r in coverage['leagues']if r['window_days']=='FULL_SEASON' and r['below_95_percent']]
    ranked=sorted(gaps,key=lambda r:(-r['missing'],r['league_id']))
    for row in ranked[:3]: lines.append(f"Below 95% (full season): {row['country']} / {row['competition']}: {row['visible']}/{row['eligible']} ({row['coverage_percent']:.2f}%).")
    declines=sorted([r for r in coverage['leagues']if r['window_days']=='FULL_SEASON' and r['coverage_change_pp'] is not None and r['coverage_change_pp']<0],key=lambda r:r['coverage_change_pp'])
    for row in declines[:3]:lines.append(f"Largest decline (full season): {row['competition']}: {row['coverage_change_pp']:+.2f}pp; eligible inventory change {row['inventory_change']:+d}.")
    lines.append(f"{len(gaps)} competition-season(s) below 95% over the full stored season; {max(0,len(gaps)-3)} omitted here. Every league/season/window and missing reason remains in receipt.league_coverage.")
    lines.append('Ingestion completeness is separate: stored-fixture visibility is not proof that the officially published schedule has been fully ingested. Unverified season-end dates are not invented; all stored future fixtures in each season remain counted.')
    if not coverage['previous_snapshot_utc']:lines.append('Coverage change: BASELINE_UNAVAILABLE until a previous completed receipt contains this metric.')
    lines.append(coverage['comparison_note'])
    return lines
