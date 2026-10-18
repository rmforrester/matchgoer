"""Owned attendance projection over a versioned, reviewed current-season catalogue.

No provider calls, fixture-inventory scans, inferred homes, or historical membership.
The catalogue is release data, not a live copy of the coverage audit. New seasons
require another evidence review. Expired seasons fail closed automatically.
"""
from datetime import date, datetime, timezone
from functools import lru_cache
import json
from pathlib import Path

from models import ClubVenue, Team, Venue


@lru_cache(maxsize=1)
def membership_catalogue():
    data = json.loads(Path(__file__).with_name('footprint_membership.json').read_text(encoding='utf-8'))
    assert data['version'] == 1 and len(data['scopes']) <= 400
    keys = set()
    for scope in data['scopes']:
        key = (scope['competition_id'], scope['season'])
        assert key not in keys
        keys.add(key)
        assert date.fromisoformat(scope['start']) <= date.fromisoformat(scope['end'])
        members = scope['members']
        assert 0 < scope['total'] == len(members) <= 100
        assert len({m['team_id'] for m in members}) == len(members)
        assert scope['source'].startswith('https://')
        if scope.get('tier') is not None:
            assert type(scope['tier']) is int and 1 <= scope['tier'] <= 20
            assert scope.get('tier_source', '').startswith('https://')
        assert all(m['evidence'] for m in members)
        if scope['complete']:
            assert all(m['venue_id'] is not None for m in members)
    return data


def _relationship_key(row):
    def value(key):
        item = row.get(key) if isinstance(row, dict) else getattr(row, key)
        return item.isoformat() if isinstance(item, date) else item
    return tuple(value(k) for k in ('venue_id', 'relationship_type', 'valid_from', 'valid_until'))


def _mapping_is_current(member, teams, venues, relationships, today):
    team = teams.get(member['team_id'])
    if not team or member['venue_id'] not in venues:
        return False
    if team.venue_id != member['expected_team_venue_id']:
        return False
    actual = {_relationship_key(r) for r in relationships.get(member['team_id'], [])}
    expected = {_relationship_key(r) for r in member['expected_relationships']}
    if actual != expected:
        return False
    # A dated relationship expiring since review cannot remain silently current.
    chosen = [r for r in member['expected_relationships'] if r['venue_id'] == member['venue_id']]
    return not chosen or any((not r['valid_from'] or r['valid_from'] <= today.isoformat()) and
                             (not r['valid_until'] or today.isoformat() <= r['valid_until']) for r in chosen)


def competition_sort_key(competition):
    """Reviewed domestic tier first, unknown tiers last; stable same-tier ties."""
    tier = competition.get('tier')
    return (competition['season_label'], tier is None, tier or 0,
            competition['name'].casefold(), competition['competition_id'])


def project_footprint(visits, scopes, teams, venues, relationships, today):
    """Pure aggregation; callers MUST pass only the resolved owner's attendance.

    Overall season membership is the union of verified relevant season windows:
    a visit at a verified current home OR a fixture linked to that exact league
    season. The latter establishes a date window, never home-ground credit.
    Each competition then uses its own window, preventing cross-calendar credit.
    """
    season_visit_ids = set()
    competitions = []
    visit_venues = {v.venue_id for v in visits}
    for scope in scopes:
        start, end = date.fromisoformat(scope['start']), date.fromisoformat(scope['end'])
        if not start <= today <= end:
            continue
        safe_members = [m for m in scope['members'] if _mapping_is_current(m, teams, venues, relationships, today)]
        home_ids = {m['venue_id'] for m in safe_members}
        linked = [v for v in visits if v.fixture is not None and
                  (v.fixture.league_id, v.fixture.season) == (scope['competition_id'], scope['season'])]
        context_ids = {venue_id for m in scope['members'] for venue_id in m.get('context_venue_ids', [])}
        # Ambiguous homes can establish relevance, never credit or a season date.
        relevant_ids = ((home_ids | context_ids) & visit_venues) | {v.venue_id for v in linked}
        if not relevant_ids:
            continue
        linked_ids = {v.visit_id for v in linked}
        eligible = [v for v in visits if v.venue_id in home_ids or v.visit_id in linked_ids]
        dated = [v for v in eligible if v.visit_date is not None and start <= v.visit_date <= today]
        season_visit_ids.update(v.visit_id for v in dated)
        lifetime_homes = home_ids & visit_venues
        seasonal_homes = home_ids & {v.venue_id for v in dated}
        complete = scope['complete'] and len(safe_members) == scope['total']
        start_year, end_year = start.year, end.year
        label = str(start_year) if start_year == end_year else f'{start_year}/{str(end_year)[2:]}'
        competitions.append(dict(
            competition_id=scope['competition_id'], season=scope['season'], season_label=label,
            tier=scope.get('tier'),
            name=scope['name'], country=scope['country'], season_start=scope['start'], season_end=scope['end'],
            coverage='ready' if complete else 'incomplete', total_clubs=scope['total'],
            lifetime_clubs=sum(m['venue_id'] in lifetime_homes for m in safe_members) if complete else None,
            season_clubs=sum(m['venue_id'] in seasonal_homes for m in safe_members) if complete else None,
            # Only relevant attended grounds and credited club names leave the server.
            grounds=[dict(venue_id=venue_id,
                          clubs=[m['name'] for m in safe_members if m['venue_id'] == venue_id],
                          season_visit_ids=[v.visit_id for v in dated if v.venue_id == venue_id])
                     for venue_id in sorted(relevant_ids)]))
    return dict(season_visit_ids=sorted(season_visit_ids),
                unclassified_dated_visits=sum(v.visit_date is not None and v.visit_id not in season_visit_ids for v in visits),
                competitions=sorted(competitions, key=competition_sort_key))


def build_footprint(db, visits, today=None):
    today = today or datetime.now(timezone.utc).date()
    catalogue = membership_catalogue()
    # Fixed catalogue bound, then only competitions related to this owner's visits.
    owned_venues = {v.venue_id for v in visits}
    linked_scopes = {(v.fixture.league_id, v.fixture.season) for v in visits if v.fixture is not None}
    scopes = [s for s in catalogue['scopes'] if s['start'] <= today.isoformat() <= s['end'] and
              ((s['competition_id'], s['season']) in linked_scopes or
               any(m['venue_id'] in owned_venues or owned_venues.intersection(m.get('context_venue_ids', []))
                   for m in s['members']))]
    members = [m for s in scopes for m in s['members']]
    teams, venues, relationships = {}, set(), {}
    if members:
        team_ids = {m['team_id'] for m in members}
        venue_ids = {m['venue_id'] for m in members if m['venue_id'] is not None}
        teams = {t.team_id: t for t in db.query(Team).filter(Team.team_id.in_(team_ids)).all()}
        venues = {v.venue_id for v in db.query(Venue.venue_id).filter(Venue.venue_id.in_(venue_ids)).all()}
        for r in db.query(ClubVenue).filter(ClubVenue.team_id.in_(team_ids), ClubVenue.status == 'CURRENT').all():
            relationships.setdefault(r.team_id, []).append(r)
    result = project_footprint(visits, scopes, teams, venues, relationships, today)
    return dict(reviewed_on=catalogue['reviewed_on'], **result)
