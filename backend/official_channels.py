"""Optional official enrichment and narrowly approved catalogue destinations."""
import ipaddress
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

HTTP_TICKETING = frozenset(tuple(row) for row in json.loads(
    (Path(__file__).resolve().parents[1] / 'config/europe-approved-http-ticketing.json').read_text()
))
INFORMATION_STATE = 'VERIFIED_OFFICIAL_TICKET_INFORMATION_SOURCE'


def public_web_url(value):
    if not isinstance(value, str) or not value or re.search(r'[\s\x00-\x1f\x7f\\]', value):
        return False
    try:
        parsed = urlsplit(value)
        host = parsed.hostname
        if parsed.scheme not in ('https', 'http') or not host or parsed.username or parsed.password:
            return False
        if parsed.port is not None and not 1 <= parsed.port <= 65535:
            return False
        if host.lower() == 'localhost' or host.lower().endswith(('.localhost', '.local', '.internal')):
            return False
        try:
            return ipaddress.ip_address(host).is_global
        except ValueError:
            return '.' in host and bool(re.fullmatch(r'[A-Za-z0-9.-]+', host))
    except ValueError:
        return False


def instagram_profile_url(value):
    if not public_web_url(value):
        return False
    p = urlsplit(value)
    return (p.scheme == 'https' and p.hostname in ('instagram.com', 'www.instagram.com')
            and not p.query and not p.fragment
            and bool(re.fullmatch(r'/[A-Za-z0-9_.]+/?', p.path))
            and p.path.strip('/').lower() not in ('p', 'reel', 'reels', 'explore', 'accounts'))


def official_channels(team):
    homepage = getattr(team, 'official_homepage_url', None)
    instagram = getattr(team, 'official_instagram_url', None)
    return {'official_homepage_url': homepage if public_web_url(homepage) else None,
            'official_instagram_url': instagram if instagram_profile_url(instagram) else None}


def ticket_destination_allowed(source):
    url = getattr(source, 'source_url', None)
    if not public_web_url(url):
        return False
    if urlsplit(url).scheme == 'https':
        return True
    model = source.ticketing_model
    state = source.source_state
    expected = INFORMATION_STATE if model == 'OFFICIAL_INFORMATION' else 'VERIFIED_OFFICIAL_TICKET_NAVIGATION_SOURCE'
    return (state == expected and getattr(source, 'club_venue_id', None) is None
            and (getattr(source, 'team_id', None), model, url) in HTTP_TICKETING)
