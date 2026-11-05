"""Event-only canonical reuse for explicitly reviewed global discovery scopes."""
from datetime import date
import re
from ingestion.coordinates import valid_coordinates
from ingestion.venue_identity import CanonicalVenues, VenueIdentity, locality_compatible, normalize_identity


def reviewed_home_proof(item, reviews):
    """Use only current, scoped attestations for ordinary regular-season matches.

    No provider/home-team affiliation alone establishes the event venue. Cup,
    playoff and exceptional rounds never receive this fallback.
    """
    league=item.get('league') or {};raw=item.get('fixture') or {}
    event=raw.get('venue') or {}
    if event.get('id') is not None or event.get('name'):
        return None
    if not re.fullmatch(r'Regular Season - [0-9]+',str(league.get('round','')),re.I):
        return None
    kickoff=date.fromisoformat(raw['date'][:10])
    home=((item.get('teams') or {}).get('home') or {}).get('id')
    matching=[]
    for r in reviews:
        if (r.get('league_id'),r.get('season'),r.get('home_team_id'))!=(league.get('id'),league.get('season'),home):
            continue
        if (r.get('review_status')!='VERIFIED_CURRENT_HOME' or r.get('competition_type')!='league'
                or r.get('no_venue_exceptions') is not True or not r.get('source','').startswith('https://')):
            continue
        if date.fromisoformat(r['valid_from'])<=kickoff<=date.fromisoformat(r['valid_until']):
            matching.append(r)
    if len(matching)>1:
        raise ValueError('AMBIGUOUS_REVIEWED_HOME_GROUND')
    return matching[0] if matching else None


def resolve_event_venue(event, scope, venues, refs, aliases, proof=None):
    physical = CanonicalVenues({vid: v['canonical_venue_id'] for vid,v in venues.items()
                               if v.get('canonical_venue_id') is not None})
    countries = set(getattr(scope, 'venue_countries', ())) or {scope.country}
    names = {vid: {normalize_identity(v.get('name'))} for vid,v in venues.items()}
    for a in aliases:
        if not a.get('valid_to') and a['venue_id'] in names:
            names[a['venue_id']].add(normalize_identity(a['name']))
    grouped_names = {}
    for vid, ns in names.items():
        grouped_names.setdefault(physical.canonical(vid),set()).update(ns)
    reviews={}
    for review in getattr(scope,'venue_reviews',()):
        if not review.get('source','').startswith('https://'):
            raise ValueError('UNREVIEWED_VENUE_ALIAS')
        root=physical.canonical(review['venue_id'])
        if root not in venues:
            raise ValueError('UNKNOWN_REVIEWED_VENUE')
        reviews[root]=review
        grouped_names[root].update(normalize_identity(n) for n in review.get('names',()))
    pid = event.get('id')
    if pid is not None and (type(pid) is not int or pid <= 0):
        raise ValueError('INVALID_PROVIDER_VENUE_ID')
    direct = set()
    if pid:
        direct.update(physical.canonical(r['venue_id']) for r in refs
                      if r['provider']=='api_football' and r['provider_venue_id']==pid and not r.get('valid_to'))
        direct.update(physical.canonical(vid) for vid,v in venues.items() if v.get('provider_venue_id')==pid)
    proposed = VenueIdentity.from_values(name=event.get('name'),city=event.get('city'))
    named = {root for root,ns in grouped_names.items() if proposed.name and proposed.name in ns}
    def compatible(root):
        v = venues.get(root)
        review=reviews.get(root,{})
        actual_country=review.get('physical_country',v.get('country') if v else None)
        allowed_city=proposed.city in {normalize_identity(c) for c in review.get('localities',())}
        return bool(v and actual_country in countries and (allowed_city or locality_compatible(
            proposed, VenueIdentity.from_values(name=v.get('name'),city=v.get('city')))))
    if proof:
        root = physical.canonical(proof['venue_id'])
        if (not proof.get('source','').startswith('https://') or root not in venues
                or (direct and direct != {root}) or (named and root not in named)):
            raise ValueError('REVIEWED_EVENT_VENUE_CONFLICT')
        # An event proof cannot overrule a contradictory supplied locality.
        if event.get('city') and not compatible(root):
            raise ValueError('REVIEWED_EVENT_VENUE_CONFLICT')
        ids = {root}
    elif direct:
        if len(direct)>1:
            raise ValueError('AMBIGUOUS_EVENT_VENUE')
        root = next(iter(direct))
        if root not in venues:
            raise ValueError('UNKNOWN_CANONICAL_VENUE')
        if reviews.get(root,{}).get('physical_country',venues[root].get('country')) not in countries:
            raise ValueError('VENUE_COUNTRY_CONFLICT')
        if not compatible(root):
            raise ValueError('VENUE_LOCALITY_CONFLICT')
        # Stable provider references establish identity; labels do not rename a ground.
        # A label identifying another existing physical ground is a real contradiction.
        if named and root not in named:
            raise ValueError('VENUE_NAME_CONFLICT')
        ids = direct
    else:
        ids = {root for root in named if compatible(root)}
        if named and not ids:
            raise ValueError('VENUE_LOCALITY_CONFLICT')
    if len(ids)>1:
        raise ValueError('AMBIGUOUS_EVENT_VENUE')
    if not ids:
        return None, 'UNRESOLVED_EVENT_VENUE'
    vid = next(iter(ids));v=venues[vid]
    if reviews.get(vid,{}).get('physical_country',v.get('country')) not in countries:
        raise ValueError('VENUE_COUNTRY_CONFLICT')
    if reviews.get(vid,{}).get('geographic_hold'):
        return None,'INVALID_COORDINATES_UNLINKED'
    lat,lon = v.get('latitude'),v.get('longitude')
    if lat is None or lon is None:
        return vid,'KNOWN_VENUE_MISSING_COORDINATES'
    if not valid_coordinates(lat,lon) or (float(lat),float(lon))==(0,0):
        return None,'INVALID_COORDINATES_UNLINKED'
    return vid,'MAP_READY'
