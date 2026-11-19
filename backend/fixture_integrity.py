"""Shared event integrity. No provider calls, canonical creation or personal-data writes."""
from __future__ import annotations

from collections import defaultdict
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
import hashlib
import json
import uuid
import math

from sqlalchemy import (MetaData, Table, Column, Integer, String, DateTime, Boolean,
                        JSON, select, inspect, or_, and_, func)

UTC = timezone.utc
ACTIVE = frozenset({'NS', 'TBD', '1H', 'HT', '2H', 'ET', 'BT', 'P'})
FINISHED = frozenset({'FT', 'AET', 'PEN'})
INACTIVE = frozenset({'PST', 'CANC', 'SUSP', 'INT', 'ABD', 'AWD', 'WO'})
STATES = frozenset({'CONFIRMED_ACTIVE', 'CONFIRMED_POSTPONED', 'CONFIRMED_RESCHEDULED',
                    'SUSPECTED_CONFLICT', 'RESOLVED_CONFLICT'})
META = MetaData()
VENUES = Table('fixture_venue_verifications', META,
    Column('fixture_id', Integer, primary_key=True), Column('venue_id', Integer),
    Column('identity', JSON, nullable=False), Column('state', String, nullable=False),
    Column('source_url', String), Column('evidence_sha256', String), Column('actor', String),
    Column('verified_at', DateTime(timezone=True)), Column('provider_venue', JSON),
    Column('previous_provider_venue', JSON),
    Column('history', JSON, nullable=False, default=list),
    Column('revision', Integer, nullable=False, default=1))
SCHEDULE = Table('fixture_schedule_integrity', META,
    Column('fixture_id', Integer, primary_key=True), Column('identity', JSON, nullable=False),
    Column('state', String, nullable=False), Column('provider_observation', JSON, nullable=False),
    Column('observed_at', DateTime(timezone=True), nullable=False),
    Column('effective_kickoff', DateTime(timezone=True), nullable=False),
    Column('effective_status', String, nullable=False), Column('schedule_hold', Boolean, nullable=False, default=False),
    Column('superseded_by', Integer), Column('evidence', JSON, nullable=False, default=dict),
    Column('conflicts', JSON, nullable=False, default=list), Column('history', JSON, nullable=False, default=list),
    Column('revision', Integer, nullable=False, default=1))
RUNS = Table('fixture_integrity_runs', META,
    Column('run_id', String, primary_key=True), Column('scheduled_for', DateTime(timezone=True), nullable=False),
    Column('started_at', DateTime(timezone=True), nullable=False), Column('completed_at', DateTime(timezone=True)),
    Column('state', String, nullable=False), Column('source_sha', String),
    Column('requests_attempted', Integer, nullable=False, default=0),
    Column('requests_completed', Integer, nullable=False, default=0),
    Column('receipt', JSON, nullable=False, default=dict))
CURRENT_RUN = ContextVar('fixture_integrity_run', default=None)

# Deliberately loose envelope, not a border/pitch geocoder. Includes mainland,
# Balearics, Canaries, Ceuta/Melilla and generous boundary tolerance. IGN reference:
# https://www.ign.es/resources/ane/Informacion_Geografica_Destacada/IGN_INFOGEO_LOCALIZACION.html
# Unknown countries/overseas territories are not assigned guessed envelopes.
COUNTRY_ENVELOPES = {'Spain': (24.0, 47.0, -22.0, 8.0)}


def venue_geography(fixture, venue, *, club_countries=(), home_grounds=(),
                    allowed_countries=(), verification=None):
    """Offline plausibility evidence, never a replacement-ground inference.

    Label/anchor disagreements are review candidates, not automatic rejections:
    foreign domestic clubs, neutral finals and international events are legitimate.
    A ground whose own Spain label contradicts its coordinates is independently
    invalid even when the event is international or its binding is verified.
    """
    if not venue:
        return dict(state='UNKNOWN', hold=False, reasons=[])
    reasons=[];hold=False
    country=fixture.get('country');actual=venue.get('country')
    allowed={c for c in (country,*club_countries,*allowed_countries) if c}
    if verification and verification.get('state')=='OFFICIAL_VERIFIED':
        if verification.get('venue_id')!=venue.get('venue_id'):
            reasons.append('VERIFIED_FIXTURE_VENUE_CONFLICT');hold=True
        else:
            allowed.add(actual)
    bounds=COUNTRY_ENVELOPES.get(actual)
    try:
        lat,lon=float(venue['latitude']),float(venue['longitude'])
        valid=math.isfinite(lat) and math.isfinite(lon) and -90<=lat<=90 and -180<=lon<=180 and (lat,lon)!=(0,0)
    except (KeyError,TypeError,ValueError):
        lat=lon=None;valid=False
    if lat is not None and not valid:
        reasons.append('INVALID_VENUE_COORDINATES');hold=True
    elif bounds and valid and not (bounds[0]<=lat<=bounds[1] and bounds[2]<=lon<=bounds[3]):
        reasons.append('VENUE_COORDINATE_COUNTRY_CONFLICT');hold=True
    if country not in (None,'World','Europe','International') and actual and actual not in allowed:
        # A canonical current home in a different country is useful exception
        # context, not evidence that this event is necessarily at that home.
        if not any(g.get('country')==actual for g in home_grounds):
            reasons.append('DOMESTIC_VENUE_COUNTRY_REVIEW')
    distances=[]
    for ground in home_grounds:
        if not valid or ground.get('venue_id')==venue.get('venue_id'):
            continue  # never corroborate a bad pin with itself
        try:
            a,b=float(ground['latitude']),float(ground['longitude'])
            if not (-90<=a<=90 and -180<=b<=180):continue
            p1,p2=math.radians(lat),math.radians(a)
            h=math.sin((p1-p2)/2)**2+math.cos(p1)*math.cos(p2)*math.sin(math.radians(lon-b)/2)**2
            distances.append(round(6371*2*math.asin(min(1,math.sqrt(max(0,h)))),1))
        except (KeyError,TypeError,ValueError):continue
    if distances and min(distances)>3000 and country not in (None,'World','Europe','International'):
        reasons.append('EXTREME_DISTANCE_FROM_KNOWN_HOMES_REVIEW')
    return dict(state='CONFLICT' if hold else 'REVIEW' if reasons else 'NO_CONFLICT_DETECTED',hold=hold,
                reasons=reasons,competition_country=country,venue_country=actual,
                club_countries=list(club_countries),home_distances_km=distances,
                coordinates_checked=valid,coordinate_envelope_available=bool(bounds))


def geography_holds_sql(connection, fixture):
    venues=Table('venues',MetaData(),autoload_with=connection).alias('geography_venue')
    original=venues.original.alias('geography_assigned')
    canonical=select(func.coalesce(original.c.canonical_venue_id,original.c.venue_id)).where(original.c.venue_id==fixture.venue_id).correlate(fixture).scalar_subquery() if 'canonical_venue_id' in original.c else fixture.venue_id
    clauses=[and_(venues.c.latitude.is_not(None),venues.c.longitude.is_not(None),
        or_(venues.c.latitude < -90,venues.c.latitude > 90,venues.c.longitude < -180,venues.c.longitude > 180,
            and_(venues.c.latitude==0,venues.c.longitude==0)))]
    for country,(south,north,west,east) in COUNTRY_ENVELOPES.items():
        clauses.append(and_(venues.c.country==country,venues.c.latitude.is_not(None),venues.c.longitude.is_not(None),
            or_(venues.c.latitude<south,venues.c.latitude>north,venues.c.longitude<west,venues.c.longitude>east)))
    return select(venues.c.venue_id).where(venues.c.venue_id==canonical,or_(*clauses)).exists()


def utc(value):
    d = value if isinstance(value, datetime) else datetime.fromisoformat(value.replace('Z', '+00:00'))
    return d.replace(tzinfo=UTC) if d.tzinfo is None else d.astimezone(UTC)


def serial(value):
    return json.loads(json.dumps(value, default=lambda x: x.isoformat() if hasattr(x, 'isoformat') else str(x)))


def identity(row):
    return {k: row[k] for k in ('fixture_id', 'league_id', 'season', 'home_team_id', 'away_team_id')}


def observation(item):
    f, l, t = item['fixture'], item['league'], item['teams']
    parsed = datetime.fromisoformat(f['date'].replace('Z','+00:00'))
    if parsed.tzinfo is None or any(type(v) is not int or v<=0 for v in
            (f['id'],l['id'],l['season'],t['home']['id'],t['away']['id'])):
        raise ValueError('INVALID_PROVIDER_OBSERVATION')
    return dict(fixture_id=f['id'], league_id=l['id'], season=l['season'],
                home_team_id=t['home']['id'], away_team_id=t['away']['id'],
                home_team=t['home'].get('name'), away_team=t['away'].get('name'),
                fixture_date=f['date'], status=f['status']['short'],
                provider_timestamp=f.get('timestamp'), venue=f.get('venue') or {}, round=l.get('round'))


def available(connection):
    names = set(inspect(connection).get_table_names())
    return set(META.tables).issubset(names)


def venue_decisions(connection):
    if not available(connection):
        return {}
    return {r['fixture_id']: dict(r) for r in connection.execute(select(VENUES)).mappings()}


def verified_venue(row, decision):
    if decision is None:
        return None
    if decision['identity'] != identity(row):
        raise ValueError('VENUE_VERIFICATION_IDENTITY_CONFLICT')
    return decision['venue_id'] if decision['state'] == 'OFFICIAL_VERIFIED' else None


def set_verified_venue(connection, fixture_id, venue_id, *, source_url, evidence_sha256, actor,
                       provider_venue, expected_revision=0, now=None):
    """Reviewed operator write primitive, not an unauthenticated API or research automation."""
    if not source_url.startswith('https://') or not actor.strip() or len(evidence_sha256) != 64:
        raise ValueError('VERIFICATION_PROVENANCE_REQUIRED')
    int(evidence_sha256, 16)
    fixtures = Table('fixtures', MetaData(), autoload_with=connection)
    grounds = Table('venues', MetaData(), autoload_with=connection)
    row = dict(connection.execute(select(fixtures).where(fixtures.c.fixture_id == fixture_id).with_for_update()).mappings().one())
    ground = dict(connection.execute(select(grounds).where(grounds.c.venue_id == venue_id)).mappings().one())
    if ground.get('canonical_venue_id') not in (None, venue_id):
        raise ValueError('CANONICAL_GROUND_REQUIRED')
    old = connection.execute(select(VENUES).where(VENUES.c.fixture_id == fixture_id).with_for_update()).mappings().first()
    values = dict(venue_id=venue_id, identity=identity(row), state='OFFICIAL_VERIFIED', source_url=source_url,
                  evidence_sha256=evidence_sha256, actor=actor, provider_venue=serial(provider_venue),
                  previous_provider_venue=old['previous_provider_venue'] if old else serial(provider_venue))
    if old and all(old[k] == v for k, v in values.items()):
        return False
    if (old['revision'] if old else 0) != expected_revision:
        raise ValueError('VERIFICATION_REVISION_CHANGED')
    values['history'] = list(old['history']) if old else []
    if old:
        values['history'].append(serial({k:v for k,v in old.items() if k!='history'}))
    values.update(verified_at=now or datetime.now(UTC), revision=expected_revision + 1)
    connection.execute(VENUES.update().where(VENUES.c.fixture_id == fixture_id).values(**values) if old
                       else VENUES.insert().values(fixture_id=fixture_id, **values))
    fields = dict(venue_id=venue_id)
    # Provider labels remain raw; public serving reads the canonical linked ground.
    connection.execute(fixtures.update().where(fixtures.c.fixture_id == fixture_id).values(**fields))
    return True


def schedule_state(old, new):
    if new['status'] == 'PST':
        return 'CONFIRMED_POSTPONED'
    if old and utc(old['fixture_date']) != utc(new['fixture_date']):
        return 'CONFIRMED_RESCHEDULED'
    return 'CONFIRMED_ACTIVE'


def detect_conflicts(rows, evidence, *, now=None):
    """Same-day is only a candidate. Explicit senior/timing attestations gate holds."""
    now = now or datetime.now(UTC)
    by_team = defaultdict(list)
    for r in rows:
        if r.get('superseded_by') is not None or r['status'] not in ACTIVE or utc(r['fixture_date']) < now - timedelta(hours=3):
            continue
        for team in {r['home_team_id'], r['away_team_id']}:
            if team:
                by_team[team].append(r)
    cases = {}
    for team, matches in by_team.items():
        matches.sort(key=lambda r: (utc(r['fixture_date']), r['fixture_id']))
        for i, a in enumerate(matches):
            for b in matches[i + 1:]:
                ta, tb = utc(a['fixture_date']), utc(b['fixture_date'])
                if tb - ta > timedelta(days=2):
                    break
                if a['fixture_id'] == b['fixture_id']:
                    continue
                ea, eb = evidence.get(a['fixture_id'], {}), evidence.get(b['fixture_id'], {})
                # Adjacent UTC days cover unavailable local-zone metadata; never enough for a hold.
                overlap = tb < ta + timedelta(minutes=180)
                if abs((tb.date() - ta.date()).days) > 1 and not overlap:
                    continue
                attested = all(e.get('timing_verified') is True and team in e.get('senior_team_ids', [])
                               and e.get('source_url', '').startswith('https://') and e.get('actor')
                               and not e.get('provisional') and not e.get('friendly_or_split_squad') and not e.get('multi_match_event')
                               and e.get('review_after') and utc(e['review_after']) >= now
                               and e.get('timing_kickoff') and utc(e['timing_kickoff']) == utc(r['fixture_date'])
                               for e, r in ((ea, a), (eb, b)))
                # Permit evidence to specify ordinary 150-minute occupancy, otherwise 180 for knockouts.
                minutes = 180 if ea.get('extra_time_possible', True) else 150
                high = attested and tb < ta + timedelta(minutes=minutes)
                ids = sorted([a['fixture_id'], b['fixture_id']])
                key = f'{team}:{ids[0]}:{ids[1]}'
                cases[key] = dict(key=key, team_id=team, fixture_ids=ids,
                                  reason='OVERLAPPING_KICKOFFS' if overlap else 'SAME_OR_ADJACENT_DAY',
                                  high_confidence=bool(high), kickoff=min(ta, tb).isoformat())
                if len(cases) > 2000:
                    raise ValueError('CONFLICT_CASE_OVERFLOW')
    return sorted(cases.values(), key=lambda c: (not c['high_confidence'], c['kickoff'], c['key']))


def reconcile_observations(connection, observations, *, preimages=None, now=None):
    """Persist only accepted existing identities; history and conflict decisions share the transaction."""
    now = now or datetime.now(UTC)
    preimages = preimages or {}
    fixtures = Table('fixtures', MetaData(), autoload_with=connection)
    policies = venue_decisions(connection)
    observed, updates, identity_holds = {}, 0, []
    pending = []
    requested_ids = sorted(observations)
    existing_rows = {r['fixture_id']:dict(r) for r in connection.execute(select(fixtures).where(
        fixtures.c.fixture_id.in_(requested_ids)).order_by(fixtures.c.fixture_id).with_for_update()).mappings()}
    existing_states = {r['fixture_id']:dict(r) for r in connection.execute(select(SCHEDULE).where(
        SCHEDULE.c.fixture_id.in_(requested_ids)).order_by(SCHEDULE.c.fixture_id).with_for_update()).mappings()}
    for fid, items in observations.items():
        if len(items) != 1:
            identity_holds.append(dict(fixture_id=fid, reason='CONTRADICTORY_PROVIDER_DUPLICATE'))
            continue
        new = items[0]
        row = existing_rows.get(fid)
        if row is None:
            continue  # missing IDs remain accounted for by the discovery group receipt
        same_identity = identity(row) == identity(new)
        if not same_identity and all(row[k] == new[k] for k in ('fixture_id', 'league_id', 'season')):
            from ingestion.team_identity import ProviderTeamObservation, resolve_provider_team_batch
            requests = [ProviderTeamObservation('api_football', new[side+'_team_id'], new.get(side+'_team') or '',
                        new['league_id'], new['season'], row.get('country')) for side in ('home', 'away')]
            resolutions = resolve_provider_team_batch(connection, requests)
            same_identity = all(resolutions[r.key].canonical_team_id == row[side+'_team_id'] and
                resolutions[r.key].identity_resolution in {'IDENTITY_COMPATIBLE', 'REVIEWED_SCOPED_OVERRIDE'}
                for r, side in zip(requests, ('home', 'away')))
        if not same_identity:
            identity_holds.append(dict(fixture_id=fid, reason='INTEGRITY_IDENTITY_HOLD'))
            continue
        current = existing_states.get(fid)
        prior = current['provider_observation'] if current else preimages.get(fid)
        ev = dict(current['evidence']) if current else {}
        # A changed provider date/status is not permission to revert an official schedule decision.
        official = ev.get('official_schedule')
        released_official = None
        if (official and official['status']=='PST' and new['status'] in ACTIVE
                and utc(new['fixture_date']) != utc(official['fixture_date'])
                and prior and utc(new['fixture_date']) != utc(prior['fixture_date'])
                and utc(row['fixture_date']) == utc(new['fixture_date']) and row['status']==new['status']):
            # Postponement applies to the old slot, not an indefinitely unknown future date.
            released_official = ev.pop('official_schedule')
            official = None
        values = dict(identity=identity(row), provider_observation=serial(new), observed_at=now,
                      effective_kickoff=utc(official['fixture_date'] if official else row['fixture_date']),
                      effective_status=official['status'] if official else row['status'],
                      state=schedule_state(prior, dict(new, status=official['status']) if official else new), evidence=ev,
                      schedule_hold=current['schedule_hold'] if current else False,
                      superseded_by=current['superseded_by'] if current else None,
                      conflicts=current['conflicts'] if current else [],
                      history=list(current['history']) if current else [], revision=(current['revision'] if current else 0))
        if prior is None or any(prior.get(k) != new.get(k) for k in ('fixture_date', 'status','venue')):
            values['history'].append(dict(at=now.isoformat(), before=serial(prior), after=serial(new)))
            values['revision'] += 1
        if released_official:
            values['history'].append(dict(at=now.isoformat(),reason='RESCHEDULED_AFTER_OFFICIAL_POSTPONEMENT',
                                         prior_official_schedule=released_official))
            values['state'] = 'CONFIRMED_RESCHEDULED'
            values['revision'] += 1
        if official and official['status'] == 'PST':
            values['state'] = 'CONFIRMED_POSTPONED'
        elif official and utc(official['fixture_date']) != utc(new['fixture_date']):
            values['state'] = 'CONFIRMED_RESCHEDULED'
        values['revision'] = max(1, values['revision'])
        pending.append(dict(fixture_id=fid, **values))
        if fid in policies:
            connection.execute(VENUES.update().where(VENUES.c.fixture_id == fid).values(provider_venue=new.get('venue')))
        observed[fid] = dict(row)
        updates += 1
    # Bound parameter counts and avoid a database round trip per ordinary observation.
    if connection.dialect.name == 'postgresql':
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    for offset in range(0, len(pending), 150):
        statement = insert(SCHEDULE).values(pending[offset:offset+150])
        statement = statement.on_conflict_do_update(index_elements=['fixture_id'],
            set_={col.name:statement.excluded[col.name] for col in SCHEDULE.c if col.name!='fixture_id'})
        connection.execute(statement)
    if not observed:
        return dict(observed=0, cases=[], identity_holds=identity_holds)
    teams = {r[k] for r in observed.values() for k in ('home_team_id', 'away_team_id') if r[k]}
    open_ids = list(connection.execute(select(SCHEDULE.c.fixture_id).where(SCHEDULE.c.state=='SUSPECTED_CONFLICT')).scalars())
    effective_date = func.coalesce(SCHEDULE.c.effective_kickoff,fixtures.c.fixture_date)
    rows = [dict(r) for r in connection.execute(select(fixtures).outerjoin(SCHEDULE,SCHEDULE.c.fixture_id==fixtures.c.fixture_id).where(or_(
        fixtures.c.home_team_id.in_(teams), fixtures.c.away_team_id.in_(teams)),
        or_(effective_date>=now-timedelta(hours=3),fixtures.c.fixture_id.in_(open_ids+list(observed))))).mappings()]
    states = {r['fixture_id']: dict(r) for r in connection.execute(select(SCHEDULE).where(
        SCHEDULE.c.fixture_id.in_([r['fixture_id'] for r in rows]))).mappings()}
    for r in rows:
        s = states.get(r['fixture_id'])
        if s:
            r.update(fixture_date=s['effective_kickoff'], status=s['effective_status'],superseded_by=s['superseded_by'])
    cases = detect_conflicts(rows, {fid: s['evidence'] for fid, s in states.items()}, now=now)
    previous_cases = {case['key']: case for state in states.values() for case in state['conflicts']}
    for case in cases:
        old = previous_cases.get(case['key'])
        case['first_seen'] = old.get('first_seen', now.isoformat()) if old else now.isoformat()
        case['last_seen'] = now.isoformat()
        case['new_or_material_change'] = old is None or old['high_confidence'] != case['high_confidence']
        if old and old['high_confidence'] and not case['high_confidence'] and case['reason']=='OVERLAPPING_KICKOFFS':
            # Expired/changed timing evidence cannot silently remove a still-overlapping safeguard.
            case['high_confidence'] = True
            case['reason'] = 'OVERLAP_REQUIRES_REVALIDATION'
    by_id = defaultdict(list)
    for case in cases:
        for fid in case['fixture_ids']:
            by_id[fid].append(case)
    for row in rows:
        fid = row['fixture_id']
        prior = states.get(fid)
        relevant = by_id[fid]
        if prior:
            for old in prior['conflicts']:
                if any(c['key'] == old['key'] for c in relevant):
                    continue
                # Close only on a fresh observation of a member, not absence from today's inventory.
                if not set(old['fixture_ids']) & set(observed):
                    relevant.append(old)
        if not relevant and (not prior or not prior['conflicts']):
            continue
        hold = any(c['high_confidence'] for c in relevant)
        state = 'SUSPECTED_CONFLICT' if relevant else ('RESOLVED_CONFLICT' if prior and prior['conflicts'] else prior['state'])
        if prior and prior['effective_status'] == 'PST':
            state = 'CONFIRMED_POSTPONED'
        if prior:
            connection.execute(SCHEDULE.update().where(SCHEDULE.c.fixture_id == fid).values(
                conflicts=relevant, schedule_hold=hold, state=state))
        else:
            # Counterpart may not have been fetched yet; retain its raw stored observation explicitly.
            connection.execute(SCHEDULE.insert().values(fixture_id=fid, identity=identity(row), state=state,
                provider_observation=serial(row), observed_at=now, effective_kickoff=utc(row['fixture_date']),
                effective_status=row['status'], schedule_hold=hold, evidence={}, conflicts=relevant, history=[], revision=1))
    return dict(observed=updates, cases=cases, identity_holds=identity_holds)


def exception_digest(report, accounting, groups, *, after, now=None):
    now = now or datetime.now(UTC)
    exceptions = {}
    def add(fid, reason, *, high=False, kickoff_override=None, case_key=None):
        row = after.get(fid)
        kickoff = kickoff_override or (row.get('fixture_date') if row else None)
        imminent = bool(kickoff and utc(kickoff) <= now+timedelta(hours=72))
        exceptions[(fid, reason)] = dict(fixture_id=fid, reason=reason, kickoff=kickoff,
            case_key=case_key or f'{fid}:{reason}',
            priority='P0' if high and imminent else 'P1' if imminent else 'P2')
    for r in accounting['rejects']:
        add(r['fixture_id'], r['reason'])
    for fid, row in after.items():
        if row.get('venue_id') is None and row.get('status') in ACTIVE:
            add(fid, 'UNRESOLVED_VENUE')
    for group in groups:
        for geo in group.get('integrity',{}).get('venue_geography',[]):
            for reason in geo['reasons']:add(geo['fixture_id'],reason,high=geo['hold'])
        for case in group.get('integrity', {}).get('cases', []):
            for fid in case['fixture_ids']:
                add(fid, case['reason'], high=case['high_confidence'],kickoff_override=case['kickoff'],case_key=case['key'])
        for hold in group.get('integrity', {}).get('identity_holds', []):
            add(hold['fixture_id'],hold['reason'])
    for row in report.get('manifest', []):
        if row.get('venue_mapping') in {'DISPUTED','AMBIGUOUS','UNKNOWN','UNRESOLVED_DIRECTIONS'}:
            add(row['fixture_id'], 'VENUE_'+row['venue_mapping'], high=True)
    return dict(exceptions=sorted(exceptions.values(), key=lambda r:(r['priority'],r['kickoff'] or '9999',r['fixture_id'])),
        routine_updates=accounting['updated'],
        mapping_failures=len({r['fixture_id'] for r in report.get('manifest', []) if r.get('classification')=='IDENTITY_MISMATCH'} |
                             {r['fixture_id'] for r in accounting['rejects'] if any(s in r['reason'] for s in ('TEAM','IDENTITY','CANONICAL'))}),
        verified_venue_overrides_preserved=[r['fixture_id'] for r in report.get('manifest',[]) if r.get('venue_mapping')=='MATCHED_VERIFIED_OVERRIDE'],
        postponed=sum(r.get('status')=='PST' for r in after.values()),
        rescheduled=sum('fixture_date' in r.get('proposed_changed_fields',[]) for r in report.get('manifest',[])),
        notification_sent=False)


def set_schedule_evidence(connection, fixture_id, *, evidence, expected_revision, now=None):
    """An authorised review primitive; no web/AI evidence is approved by this function itself."""
    now = now or datetime.now(UTC)
    evidence = serial(evidence)
    if not evidence.get('source_url', '').startswith('https://') or not evidence.get('actor'):
        raise ValueError('SCHEDULE_PROVENANCE_REQUIRED')
    if not evidence.get('review_after') or utc(evidence['review_after']) <= now:
        raise ValueError('SCHEDULE_REVIEW_DEADLINE_REQUIRED')
    fixtures = Table('fixtures', MetaData(), autoload_with=connection)
    connection.execute(select(fixtures.c.fixture_id).where(fixtures.c.fixture_id==fixture_id).with_for_update()).one()
    row = connection.execute(select(SCHEDULE).where(SCHEDULE.c.fixture_id == fixture_id).with_for_update()).mappings().one()
    if row['evidence'] == evidence:
        return False
    if row['revision'] != expected_revision:
        raise ValueError('SCHEDULE_REVISION_CHANGED')
    values = dict(evidence=serial(evidence), revision=row['revision']+1)
    official = evidence.get('official_schedule')
    if official:
        if official['status'] not in ACTIVE | INACTIVE | FINISHED:
            raise ValueError('INVALID_SCHEDULE_STATUS')
        values.update(effective_kickoff=utc(official['fixture_date']), effective_status=official['status'],
                      state='CONFIRMED_POSTPONED' if official['status']=='PST' else 'CONFIRMED_RESCHEDULED')
        values['history'] = list(row['history'])+[dict(at=now.isoformat(),reason='VERIFIED_SCHEDULE_DECISION',
            before=dict(fixture_date=utc(row['effective_kickoff']).isoformat(),status=row['effective_status']),
            after=official,source_url=evidence['source_url'],actor=evidence['actor'])]
    connection.execute(SCHEDULE.update().where(SCHEDULE.c.fixture_id==fixture_id).values(**values))
    reconcile_observations(connection,{fixture_id:[row['provider_observation']]},now=now)
    return True


def availability(status, kickoff, *, hold=False, superseded=False, now=None):
    now = now or datetime.now(UTC)
    return not hold and not superseded and (status in ACTIVE or status in FINISHED and utc(kickoff) <= now)


def eligibility_query(query, db, fixture, *, retain_history=False):
    """Filter before counts/pagination/geography. Old schemas still receive status safety."""
    status, kickoff = fixture.status, fixture.fixture_date
    predicates = [~geography_holds_sql(db.connection(), fixture)]
    if available(db.connection()):
        query = query.outerjoin(SCHEDULE, SCHEDULE.c.fixture_id == fixture.fixture_id)
        query = query.outerjoin(VENUES, VENUES.c.fixture_id == fixture.fixture_id)
        status = func.coalesce(SCHEDULE.c.effective_status, status)
        kickoff = func.coalesce(SCHEDULE.c.effective_kickoff, kickoff)
        predicates += [or_(SCHEDULE.c.schedule_hold.is_(None), SCHEDULE.c.schedule_hold.is_(False)),
                       SCHEDULE.c.superseded_by.is_(None),
                       or_(VENUES.c.state.is_(None), VENUES.c.state.not_in(['DISPUTED','UNRESOLVED']))]
    valid = and_(or_(status.in_(ACTIVE), and_(status.in_(FINISHED), kickoff <= func.current_timestamp())), *predicates)
    if retain_history:
        valid = or_(kickoff < func.current_timestamp(), valid)
    return query.filter(valid), kickoff


def project_rows(db, rows):
    """Project effective facts without mutating ORM or personal history."""
    if not rows or not available(db.connection()):
        return rows
    from types import SimpleNamespace
    ids = [r.fixture_id for r in rows]
    schedules = {r['fixture_id']: r for r in db.connection().execute(select(SCHEDULE).where(SCHEDULE.c.fixture_id.in_(ids))).mappings()}
    venues = {r['fixture_id']: r for r in db.connection().execute(select(VENUES).where(VENUES.c.fixture_id.in_(ids))).mappings()}
    result = []
    for row in rows:
        values = dict(vars(row))
        values.pop('_sa_instance_state', None)
        s, v = schedules.get(row.fixture_id), venues.get(row.fixture_id)
        values['integrity'] = dict(schedule_state=s['state'] if s else None,
            scheduling_uncertain=bool(s and s['conflicts']), schedule_hold=bool(s and s['schedule_hold']),
            superseded_by=s['superseded_by'] if s else None, venue_state=v['state'] if v else 'PROVIDER_ASSIGNED')
        if s:
            values.update(fixture_date=utc(s['effective_kickoff']), status=s['effective_status'])
        ground=values.get('venue') or getattr(row,'venue',None)
        geo=venue_geography(values,vars(ground) if ground is not None else None,verification=v)
        values['integrity']['venue_geography']=geo
        if geo['hold'] or (v and v['state'] in {'DISPUTED','UNRESOLVED'}):
            values.update(venue=None, venue_id=None, venue_name=None, venue_city=None)
        result.append(SimpleNamespace(**values))
    return result


def missed_run(rows, *, now=None, grace_hours=2):
    """Independent read-only check: a scheduled 04:20 UTC occurrence, not a last-success guess."""
    now = now or datetime.now(UTC)
    due = now.replace(hour=4, minute=20, second=0, microsecond=0)
    if now < due + timedelta(hours=grace_hours):
        due -= timedelta(days=1)
    matches = [r for r in rows if r.get('scheduled_for') and utc(r['scheduled_for']) == due
               and due <= utc(r['started_at']) <= due+timedelta(hours=grace_hours)]
    if not matches:
        late = [r for r in rows if r.get('scheduled_for') and utc(r['scheduled_for'])==due and utc(r['started_at'])>due]
        return dict(passed=False, reason='LATE_SCHEDULED_RUN' if late else 'MISSED_SCHEDULED_RUN',
                    scheduled_for=due.isoformat(),severity='P0')
    latest = max(matches, key=lambda r: utc(r['started_at']))
    passed = latest['state'] == 'COMPLETED'
    reason={'COMPLETED':'OK','INCOMPLETE':'COVERAGE_INCOMPLETE','RUNNING':'STALLED_SCHEDULED_RUN','FAILED':'FAILED_SCHEDULED_RUN'}[latest['state']]
    return dict(passed=passed, reason=reason, run_state=latest['state'],
                severity='P1' if latest['state']=='INCOMPLETE' else 'OK' if passed else 'P0',
                scheduled_for=due.isoformat(), run_id=latest['run_id'])


def transaction_integrity(connection, items, *, preimages=None, manifest=None, stage='lifecycle'):
    """Same-transaction sidecars and commit evidence; never another fixture writer."""
    if not available(connection):
        return
    if connection.dialect.name == 'postgresql':
        connection.exec_driver_sql('LOCK TABLE fixture_schedule_integrity,fixture_venue_verifications IN SHARE ROW EXCLUSIVE MODE')
    observations = {}
    accepted_ids = None if manifest is None else {r['fixture_id'] for r in manifest if r['classification'] in {
        'WOULD_UPDATE_TO_FINAL','WOULD_UPDATE_RESCHEDULED','WOULD_UPDATE_OTHER_ALLOWED_STATE','PROVIDER_STILL_UNRESOLVED','NO_CHANGE'}}
    for item in items:
        try:
            row = observation(item)
        except (KeyError, TypeError, ValueError):
            continue
        if accepted_ids is not None and row['fixture_id'] not in accepted_ids:
            continue
        bucket = observations.setdefault(row['fixture_id'], [])
        if row not in bucket:
            bucket.append(row)
    from backend.fixture_catalogue_recheck import protect_original_bindings
    original_binding_holds = protect_original_bindings(connection, preimages, observations)
    result = reconcile_observations(connection, observations, preimages=preimages)
    fixtures = Table('fixtures', MetaData(), autoload_with=connection)
    for diagnostic in manifest or []:
        outcome = diagnostic.get('venue_mapping')
        if outcome not in {'DISPUTED', 'AMBIGUOUS', 'UNKNOWN', 'MATCHED', 'MATCHED_HOME_REVIEW'}:
            continue
        fid = diagnostic['fixture_id']
        current = connection.execute(select(VENUES).where(VENUES.c.fixture_id==fid)).mappings().first()
        if current and current['state']=='OFFICIAL_VERIFIED':
            continue
        if accepted_ids is not None and fid not in accepted_ids:
            if current and current['state'] in {'DISPUTED', 'UNRESOLVED'}:
                continue  # Rejected identity evidence cannot release an existing hold.
            if outcome not in {'DISPUTED', 'AMBIGUOUS', 'UNKNOWN'}:
                continue  # Still permit protective quarantine of an unheld wrong pin.
        if current and (current['source_url'] or current['evidence_sha256'] or
                current['state'] in {'DISPUTED', 'UNRESOLVED'} and current['actor'] not in {
                    'AUTOMATED_CANONICAL_CONFLICT', 'AUTOMATED_GEOGRAPHIC_CONFLICT'}):
            continue  # Preserve reviewed and explicitly owned holds.
        row = connection.execute(select(fixtures).where(fixtures.c.fixture_id==fid)).mappings().first()
        if row is None:
            continue
        if outcome in {'DISPUTED','AMBIGUOUS','UNKNOWN'}:
            decision_state = 'UNRESOLVED' if outcome=='UNKNOWN' else 'DISPUTED'
            provider_venue=diagnostic.get('raw_provider_venue') or {}
            if current and current['state']==decision_state and current['provider_venue']==provider_venue:
                continue
            values = dict(identity=identity(row),state=decision_state,provider_venue=provider_venue,
                          actor='AUTOMATED_CANONICAL_CONFLICT', revision=(current['revision'] if current else 0)+1)
            connection.execute(VENUES.update().where(VENUES.c.fixture_id==fid).values(**values) if current
                               else VENUES.insert().values(fixture_id=fid,**values))
        elif current and current['actor']=='AUTOMATED_CANONICAL_CONFLICT':
            if fid in original_binding_holds:
                continue
            provider_id = (diagnostic.get('raw_provider_venue') or {}).get('id')
            if current['state'] in {'DISPUTED', 'UNRESOLVED'} and (
                    type(provider_id) is not int or provider_id <= 0):
                continue  # A name-only/zero-ID match is not authority to release a hold.
            connection.execute(VENUES.update().where(VENUES.c.fixture_id==fid).values(
                state='PROVIDER_ASSIGNED',venue_id=row['venue_id'],revision=current['revision']+1))
    # Audit the stored relationship even when the provider venue is NULL. This
    # catches legacy geocoding errors rather than trusting a country label alone.
    result['venue_geography']=[]
    ids=sorted(observations)
    if ids:
        rows=list(connection.execute(select(fixtures).where(fixtures.c.fixture_id.in_(ids))).mappings())
        grounds=Table('venues',MetaData(),autoload_with=connection)
        teams=Table('teams',MetaData(),autoload_with=connection)
        tids={r[k] for r in rows for k in ('home_team_id','away_team_id')}
        clubs={r['team_id']:dict(r) for r in connection.execute(select(teams).where(teams.c.team_id.in_(tids))).mappings()} if 'team_id' in teams.c else {}
        vids={r['venue_id'] for r in rows if r.get('venue_id')}|{t['venue_id'] for t in clubs.values() if t.get('venue_id')}
        places={r['venue_id']:dict(r) for r in connection.execute(select(grounds).where(grounds.c.venue_id.in_(vids))).mappings()}
        policies={r['fixture_id']:r for r in connection.execute(select(VENUES).where(VENUES.c.fixture_id.in_(ids))).mappings()}
        for row in rows:
            fid=row['fixture_id'];current=policies.get(fid)
            participants=[clubs.get(row[k],{}) for k in ('home_team_id','away_team_id')]
            geo=venue_geography(row,places.get(row.get('venue_id')),
                club_countries=[t['country'] for t in participants if t.get('country')],
                home_grounds=[places[t['venue_id']] for t in participants if t.get('venue_id') in places],verification=current)
            if geo['reasons']:result['venue_geography'].append(dict(fixture_id=fid,**geo))
            if geo['hold'] and not (current and current['state']=='OFFICIAL_VERIFIED'):
                if current and current['state']=='DISPUTED' and current['actor']=='AUTOMATED_GEOGRAPHIC_CONFLICT':continue
                values=dict(identity=identity(row),state='DISPUTED',actor='AUTOMATED_GEOGRAPHIC_CONFLICT',revision=(current['revision'] if current else 0)+1)
                connection.execute(VENUES.update().where(VENUES.c.fixture_id==fid).values(**values) if current else VENUES.insert().values(fixture_id=fid,**values))
            elif not geo['hold'] and current and current['actor']=='AUTOMATED_GEOGRAPHIC_CONFLICT':
                if fid in original_binding_holds:continue
                connection.execute(VENUES.update().where(VENUES.c.fixture_id==fid).values(state='PROVIDER_ASSIGNED',venue_id=row['venue_id'],revision=current['revision']+1,actor='AUTOMATED_GEOGRAPHIC_RESOLUTION'))
    # Both lifecycle and discovery writers use this same transaction hook.
    # Reuse approved catalogue facts across future seasons without provider I/O.
    from backend.fixture_catalogue_recheck import reevaluate
    result['catalogue_reevaluation'] = reevaluate(connection, items=items, manifest=manifest, preimages=preimages)
    run = CURRENT_RUN.get()
    if run is not None:
        stored = connection.execute(select(RUNS.c.receipt).where(RUNS.c.run_id==run.run_id).with_for_update()).scalar_one()
        stored = dict(stored)
        stored.setdefault('committed_groups', []).append(dict(stage=stage,
            observed_ids=sorted(observations), integrity=result))
        connection.execute(RUNS.update().where(RUNS.c.run_id==run.run_id).values(receipt=serial(stored)))


class RunReceipt:
    """Separate durable receipt transactions survive fixture rollback; no provider calls."""
    def __init__(self, engine, *, now=None, source_sha=None):
        self.engine, self.started_at = engine, now or datetime.now(UTC)
        self.run_id = str(uuid.uuid4())
        self.scheduled_for = self.started_at.replace(hour=4, minute=20, second=0, microsecond=0)
        self.attempted = self.completed = 0
        self.requests, self.observations, self.preimages = [], {}, {}
        with engine.begin() as c:
            if not available(c):
                raise RuntimeError('INTEGRITY_MIGRATION_REQUIRED_BEFORE_WRITES')
            c.execute(RUNS.insert().values(run_id=self.run_id, scheduled_for=self.scheduled_for,
                started_at=self.started_at, state='RUNNING', source_sha=source_sha,
                requests_attempted=0, requests_completed=0, receipt={}))
            self.fixtures = Table('fixtures', MetaData(), autoload_with=c)

    def request(self, endpoint, params, *, payload=None, failed=False):
        if payload is None and not failed:
            self.attempted += 1
            self.requests.append(dict(endpoint=endpoint, params=serial(params), state='ATTEMPTED'))
        else:
            if not failed:
                self.completed += 1
            self.requests[-1]['state'] = 'FAILED' if failed else 'COMPLETED'
            responses = payload.get('response', []) if isinstance(payload, dict) else []
            self.requests[-1]['fixture_count'] = len(responses) if endpoint == '/fixtures' else None
            if endpoint == '/fixtures' and not failed:
                ids = []
                scope_counts = defaultdict(int)
                malformed = 0
                for p in responses:
                    try:
                        obs = observation(p)
                    except (KeyError, TypeError, ValueError):
                        malformed += 1
                        continue
                    fid = obs['fixture_id']
                    ids.append(fid)
                    scope_counts[f"{obs['league_id']}:{obs['season']}"] += 1
                    if obs not in self.observations.setdefault(fid, []):
                        self.observations[fid].append(obs)
                self.requests[-1].update(fixture_ids=ids, scopes=dict(scope_counts),malformed_count=malformed,
                    payload_sha256=hashlib.sha256(json.dumps(serial(payload),sort_keys=True).encode()).hexdigest())
                unseen = set(ids)-set(self.preimages)
                with self.engine.connect() as c:
                    fixtures = self.fixtures
                    for r in c.execute(select(fixtures).where(fixtures.c.fixture_id.in_(unseen))).mappings():
                        self.preimages.setdefault(r['fixture_id'], serial(dict(r)))
                for fid in unseen:
                    self.preimages.setdefault(fid, None)
        with self.engine.begin() as c:
            stored = dict(c.execute(select(RUNS.c.receipt).where(RUNS.c.run_id==self.run_id)).scalar_one())
            stored['requests'] = self.requests
            c.execute(RUNS.update().where(RUNS.c.run_id == self.run_id).values(
                requests_attempted=self.attempted, requests_completed=self.completed,
                receipt=stored))

    def finish(self, report, *, error=None):
        # Decisions commit with their fixture transaction, never as an after-the-fact second writer.
        with self.engine.connect() as c:
            partial = dict(c.execute(select(RUNS.c.receipt).where(RUNS.c.run_id==self.run_id)).scalar_one())
        integrity = dict(groups=partial.get('committed_groups', []))
        state = 'FAILED' if error or not report.get('execution_success') else 'COMPLETED'
        if state == 'COMPLETED' and not report.get('complete', False):
            state = 'INCOMPLETE'
        with self.engine.connect() as c:
            fixtures = self.fixtures
            after = {r['fixture_id']: serial(dict(r)) for r in c.execute(select(fixtures).where(
                fixtures.c.fixture_id.in_(self.observations))).mappings()}
            schedule_rows = {r['fixture_id']:r for r in c.execute(select(SCHEDULE).where(
                SCHEDULE.c.fixture_id.in_(self.observations))).mappings()}
        missing = sorted(set(self.observations)-set(after))
        reasons = {r['fixture_id']: r.get('reason') or r.get('classification') for r in report.get('manifest', [])
                   if r.get('classification') in {'IDENTITY_MISMATCH','PROVIDER_MALFORMED','MANUAL_REVIEW_HOLD','PROVIDER_DUPLICATE'}}
        groups = [g for g in [report.get('fixture_discovery')] + (report.get('global_fixture_discovery') or {}).get('groups', []) if isinstance(g, dict)]
        for g in groups:
            for held in g.get('held', []):
                reasons[held['fixture_id']] = held['reason']
            if g.get('errors') or g.get('overflow'):
                for fid, observations in self.observations.items():
                    if ('league_id' not in g or g['league_id']==observations[0]['league_id']) and fid in missing:
                        reasons.setdefault(fid, 'GROUP_FAILED_OR_OVERFLOW')
        unaccounted = [fid for fid in missing if fid not in reasons]
        if unaccounted and state=='COMPLETED':
            state = 'INCOMPLETE'
        if any(r.get('malformed_count') for r in self.requests) and state=='COMPLETED':
            state = 'INCOMPLETE'
        accounting = dict(returned_unique_ids=len(self.observations), returned_observations=sum(len(x) for x in self.observations.values()),
            inserted=sum(fid in after and self.preimages.get(fid) is None for fid in self.observations),
            updated=sum(fid in after and self.preimages.get(fid) is not None and after[fid]!=self.preimages[fid] for fid in self.observations),
            skips=sum(fid in after and after[fid]==self.preimages.get(fid) for fid in self.observations),
            rejects=[dict(fixture_id=fid,reason=reasons.get(fid,'UNACCOUNTED')) for fid in missing],
            missing_ids=missing, unaccounted_missing_ids=unaccounted)
        data = dict(report=serial({k: v for k, v in report.items() if k != 'manifest'}),
                    requests=self.requests, integrity=integrity, accounting=accounting,
                    lifecycle_decisions=serial(report.get('manifest', [])), error=error)
        effective_after = {fid:dict(row) for fid,row in after.items()}
        for fid, decision in schedule_rows.items():
            if fid in effective_after:
                effective_after[fid].update(fixture_date=utc(decision['effective_kickoff']).isoformat(),status=decision['effective_status'])
        data['exception_report'] = exception_digest(report, accounting, partial.get('committed_groups', []), after=effective_after)
        # Observational only: coverage failure must not rewrite execution health,
        # release holds, or prevent the existing durable failure receipt.
        try:
            from backend.fixture_coverage import collect
            with self.engine.connect().execution_options(isolation_level='REPEATABLE READ') as c:
                c.exec_driver_sql('SET TRANSACTION READ ONLY')
                previous = c.execute(select(RUNS.c.receipt).where(
                    RUNS.c.run_id != self.run_id, RUNS.c.completed_at.is_not(None),
                    RUNS.c.state.in_(['COMPLETED','INCOMPLETE']))
                    .order_by(RUNS.c.completed_at.desc()).limit(1)).scalar_one_or_none()
                data['league_coverage'] = collect(c, datetime.now(UTC), (previous or {}).get('league_coverage'))
        except Exception as coverage_error:
            data['league_coverage'] = dict(status='UNAVAILABLE', reason=type(coverage_error).__name__,
                                          note='No Discover coverage pass claimed; execution health is reported separately.')
        with self.engine.begin() as c:
            c.execute(RUNS.update().where(RUNS.c.run_id == self.run_id).values(
                completed_at=datetime.now(UTC), state=state, receipt=data,
                requests_attempted=self.attempted, requests_completed=self.completed))
        return dict(run_id=self.run_id, state=state, integrity=integrity)
