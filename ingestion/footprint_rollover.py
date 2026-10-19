"""Offline Footprint rollover proposals. Never fetches, publishes or edits inputs.

Run with --help. Inputs are existing catalogue, canonical snapshot, and explicitly
reviewed season/roster envelopes. Output is a disposable review receipt only.
"""
import argparse
import copy
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from backend.football_footprint import (_mapping_is_current, MAX_CATALOGUE_SCOPES,
                                      MAX_CATALOGUE_BYTES, load_membership_catalogue)
from ingestion.venue_identity import CanonicalVenues


MAX_SCOPES = MAX_CATALOGUE_SCOPES
MAX_MEMBERS = 100


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(',', ':')) + '\n').encode('utf-8')


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def key(scope):
    return scope['competition_id'], scope['season']


def propose(catalogue, snapshot, plan, as_of):
    """Pure, deterministic proposal; caller supplies a frozen UTC date.

    Roster verification is an explicit reviewed input, never inferred from
    fixtures or provider current=true. No existing scope can be overwritten.
    """
    if catalogue.get('version') != 1 or plan.get('version') != 1:
        raise ValueError('Unsupported input version')
    if plan.get('snapshot_sha256') != digest(snapshot):
        raise ValueError('Canonical snapshot hash mismatch')
    if date.fromisoformat(plan['snapshot_as_of']) != as_of:
        raise ValueError('Snapshot review date must equal frozen as-of date')
    existing = {key(s): s for s in catalogue['scopes']}
    if len(existing) != len(catalogue['scopes']):
        raise ValueError('Duplicate catalogue season')
    requests = plan['scopes']
    if len(requests) > MAX_SCOPES or len({key(s) for s in requests}) != len(requests):
        raise ValueError('Duplicate or unbounded season requests')
    teams = {t['team_id']: SimpleNamespace(**t) for t in snapshot['teams']}
    venues = {v['venue_id'] for v in snapshot['venues']}
    if len(teams) != len(snapshot['teams']) or len(venues) != len(snapshot['venues']):
        raise ValueError('Ambiguous canonical snapshot identities')
    identity = CanonicalVenues({v['venue_id']: v['canonical_venue_id']
                               for v in snapshot['venues'] if v.get('canonical_venue_id')})
    if any(identity.canonical(v) not in venues for v in venues):
        raise ValueError('Missing canonical equivalence target')
    relationships = {}
    for r in snapshot['relationships']:
        if r['status'] == 'CURRENT':
            relationships.setdefault(r['team_id'], []).append(r)
    exceptions, changes, additions = [], [], []

    def valid(member, start, end):
        if not all(_mapping_is_current(member, teams, venues, relationships,
                                       day, identity) for day in {as_of, start, end}):
            return False
        chosen = [r for r in member['expected_relationships']
                  if identity.canonical(r['venue_id']) == identity.canonical(member['venue_id'])]
        if not chosen:
            return True
        # Endpoint checks alone would miss a gap between two temporary roles.
        cursor = start
        intervals = sorted((date.fromisoformat(r['valid_from']) if r['valid_from'] else date.min,
                            date.fromisoformat(r['valid_until']) if r['valid_until'] else date.max)
                           for r in chosen)
        for lo, hi in intervals:
            if hi < cursor:
                continue
            if lo > cursor:
                return False
            if hi >= end:
                return True
            cursor = hi + timedelta(days=1)
        return False

    def issue(scope, reason, team_id=None):
        exceptions.append(dict(competition_id=scope['competition_id'],
                               season=scope['season'], team_id=team_id, reason=reason))

    for request in sorted(requests, key=key):
        scope = copy.deepcopy(request['scope'])
        if key(scope) != key(request) or any(type(v) is not int or v <= 0 for v in key(scope)):
            raise ValueError('Scope identity mismatch')
        start, end = date.fromisoformat(scope['start']), date.fromisoformat(scope['end'])
        roster = request['roster']
        rows = roster.get('teams', [])
        ids = [r['team']['id'] for r in rows]
        # Accept only a bounded, complete, season-specific reviewed roster.
        if (start > end or request.get('membership_verified') is not True or
                request.get('domestic_league') is not True or
                not scope.get('source', '').startswith('https://') or
                roster.get('competition_id') != scope['competition_id'] or
                roster.get('season') != scope['season'] or
                roster.get('paging') != {'current': 1, 'total': 1} or
                roster.get('errors') not in ([], {}) or
                roster.get('results') != len(rows) or
                type(scope['total']) is not int or not 0 < scope['total'] == len(ids) <= MAX_MEMBERS or
                len(set(ids)) != len(ids) or
                any(type(t) is not int or t <= 0 for t in ids)):
            issue(scope, 'membership_or_calendar_unverified')
            continue
        if scope.get('tier') is not None and (
                type(scope['tier']) is not int or not 1 <= scope['tier'] <= 20 or
                not scope.get('tier_source', '').startswith('https://')):
            issue(scope, 'tier_unverified')
            continue
        reviewed = request.get('reviewed_members', [])
        if len({m['team_id'] for m in reviewed}) != len(reviewed) or any(m['team_id'] not in ids for m in reviewed):
            issue(scope, 'reviewed_participant_mismatch')
            continue
        members = []
        for tid in sorted(ids):
            explicit = [m for m in reviewed if m['team_id'] == tid]
            # Reuse across promotion/relegation by canonical club ID, never name.
            pool = explicit or [m for old in catalogue['scopes'] if old['complete']
                                for m in old['members'] if m['team_id'] == tid]
            eligible = [m for m in pool if m.get('evidence') and valid(m, start, end)]
            homes = {identity.canonical(m['venue_id']) for m in eligible}
            if len(homes) == 1 and (not explicit or len(eligible) == 1):
                member = copy.deepcopy(min(eligible, key=encoded))
            else:
                issue(scope, 'home_changed_expired_ambiguous_or_unreviewed', tid)
                # Preserve reviewed preimage fingerprints; never mint fresh ones.
                if pool:
                    member = copy.deepcopy(min(pool, key=encoded));member['venue_id'] = None
                else:
                    member = dict(team_id=tid, name=teams[tid].name if tid in teams else 'Unresolved club',
                                  venue_id=None, evidence=scope['source'],
                                  expected_team_venue_id=None, expected_relationships=[], context_venue_ids=[])
                member['reason'] = 'Season home requires targeted canonical review'
            members.append(member)
        scope['members'] = members
        scope['complete'] = all(m['venue_id'] is not None for m in members)
        if key(scope) in existing:
            if encoded(scope) != encoded(existing[key(scope)]):
                issue(scope, 'existing_season_immutable')
            continue
        if any(s['competition_id'] == scope['competition_id'] and
               max(s['start'], scope['start']) <= min(s['end'], scope['end'])
               for s in catalogue['scopes'] + additions):
            issue(scope, 'overlapping_competition_season_windows')
            continue
        additions.append(scope)
        previous = [s for s in catalogue['scopes'] if s['competition_id'] == scope['competition_id'] and s['end'] < scope['start']]
        prior = max(previous, key=lambda s: (s['end'], s['season'])) if previous else None
        old_ids = {m['team_id'] for m in prior['members']} if prior else set()
        changes.append(dict(competition_id=scope['competition_id'], season=scope['season'],
                            preimage=None, postimage=copy.deepcopy(scope),
                            added_participants=sorted(set(ids)-old_ids),
                            removed_participants=sorted(old_ids-set(ids)),
                            complete=scope['complete'], start=scope['start'], end=scope['end']))
    candidate = copy.deepcopy(catalogue)
    candidate['scopes'].extend(additions)

    def ready(cat):
        return sorted([list(key(s)) for s in cat['scopes'] if s['complete'] and
                       s['start'] <= as_of.isoformat() <= s['end'] and
                       all(_mapping_is_current(m, teams, venues, relationships, as_of, identity)
                           for m in s['members'])])

    before, after = ready(catalogue), ready(candidate)
    for s in catalogue['scopes']:
        if s['complete'] and s['start'] <= as_of.isoformat() <= s['end']:
            for member in s['members']:
                if not _mapping_is_current(member, teams, venues, relationships, as_of, identity):
                    issue(s, 'existing_active_mapping_stale', member['team_id'])
    over_capacity = len(candidate['scopes']) > MAX_SCOPES
    over_bytes = len(encoded(candidate)) > MAX_CATALOGUE_BYTES
    if over_capacity:
        exceptions.append(dict(reason='runtime_scope_capacity_exceeded', scopes=len(candidate['scopes']), limit=MAX_SCOPES))
    if over_bytes:
        exceptions.append(dict(reason='runtime_catalogue_byte_limit_exceeded', limit=MAX_CATALOGUE_BYTES))
    return dict(candidate=candidate, changes=changes, exceptions=exceptions,
                summary=dict(mode='dry-run-only', as_of=as_of.isoformat(),
                             catalogue_preimage_sha256=digest(catalogue), snapshot_sha256=digest(snapshot),
                             plan_sha256=digest(plan), candidate_sha256=digest(candidate),
                             ready_before=len(before), ready_after=len(after),
                             ready_added=[s for s in after if s not in before],
                             scopes_before=len(catalogue['scopes']), scopes_after=len(candidate['scopes']),
                             runtime_capacity_ok=not (over_capacity or over_bytes),
                             review_required=bool(exceptions), publication_authorised=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('catalogue', 'snapshot', 'plan', 'output'):
        parser.add_argument('--'+name, required=True, type=Path)
    parser.add_argument('--as-of', required=True, type=date.fromisoformat)
    args = parser.parse_args()
    inputs = [args.catalogue, args.snapshot, args.plan]
    # Never allow receipt output to replace any source, including symlink targets.
    names = ('candidate.json', 'changes.json', 'exceptions.json', 'summary.json')
    targets = [args.output/name for name in names]
    if any(t.resolve() == p.resolve() for t in targets for p in inputs):
        parser.error('Output would overwrite an input')
    result = propose(load_membership_catalogue(args.catalogue),
                     json.loads(args.snapshot.read_text(encoding='utf-8')),
                     json.loads(args.plan.read_text(encoding='utf-8')), args.as_of)
    result['summary']['input_file_sha256'] = {
        label: hashlib.sha256(path.read_bytes()).hexdigest()
        for label, path in zip(('catalogue', 'snapshot', 'plan'), inputs)}
    args.output.mkdir(parents=True, exist_ok=True)
    for name in names:
        field = name.split('.')[0]
        (args.output/name).write_bytes(encoded(result[field]))
    print(json.dumps(result['summary'], sort_keys=True))
    return 2 if result['summary']['review_required'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
