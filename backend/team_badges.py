"""Fail-closed API-Football team-badge proxy with bounded in-process caching."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import threading
from typing import Callable

import requests


PROVIDER_BADGE_URL = "https://media.api-sports.io/football/teams/{provider_team_id}.png"
MAX_BADGE_BYTES = 1_000_000
FRESH_TTL = timedelta(days=2)
STALE_TTL = timedelta(days=7)
NEGATIVE_TTL = timedelta(hours=12)

# Visually verified API-Football generic/default assets from the accepted preflight.
PLACEHOLDER_SHA256 = frozenset({
    "5026ce6ca0838a1c6d32982f5466281c36ea5cdb5e67eac6bc4c8b6e0cda6437",
    "72f0bbb253ab54961cd5d66148e55aceb3e6bc9823da43e57a6e0812e5427430",
    "7670cc2d08b0b4a846ac6ec076c99d3767c4d2b9322e2d31cd05871422ddbbda",
    "78e6132b4b2566fbab177137480d0f883aee9c2370bd9a668787263c1a2d9138",
    "9f8004a0b4a645c2061f82ebf7ede6520830c071eb2ca9a37fa3f150d53bef11",
    "a2cea5dc38d2802f6f45317809cba250357b375cd3ba0373754fa9b4938f453b",
    "b602abdd01273f6dd29855a6aed585747243148768da4a5a54e3cebd9989fd36",
    "ca02d37d38e861d37a4bf5cec5e9ee69f8e16f3c420b38d710a2155a5a1a5d11",
    "fdcdcd96e5197b389a1930db1a1f47045ca4e59b65284c4687c94096a8a81338",
})


@dataclass(frozen=True)
class CachedBadge:
    content: bytes | None
    media_type: str | None
    digest: str | None
    fresh_until: datetime
    stale_until: datetime


@dataclass(frozen=True)
class BadgeResult:
    content: bytes
    media_type: str
    digest: str
    stale: bool = False


_cache: dict[int, CachedBadge] = {}
_cache_lock = threading.Lock()


def provider_badge_id(canonical_team_id: int | None) -> int | None:
    """Resolve only the established provider-ID keyed identity model.

    Reviewed unresolved identities use a non-positive sentinel and must never
    inherit the badge of the provider ID involved in the ambiguity.
    """
    if canonical_team_id is None or canonical_team_id <= 0:
        return None
    return canonical_team_id


def badge_proxy_path(canonical_team_id: int | None) -> str | None:
    provider_team_id = provider_badge_id(canonical_team_id)
    return f"/teams/{provider_team_id}/badge" if provider_team_id else None


def _download(provider_team_id: int) -> BadgeResult | None:
    response = requests.get(
        PROVIDER_BADGE_URL.format(provider_team_id=provider_team_id),
        timeout=5,
        headers={"Accept": "image/png,image/*;q=0.8"},
    )
    response.raise_for_status()
    media_type = (response.headers.get("content-type") or "").split(";", 1)[0].lower()
    content = response.content
    if not media_type.startswith("image/") or not content or len(content) > MAX_BADGE_BYTES:
        return None
    digest = hashlib.sha256(content).hexdigest()
    if digest in PLACEHOLDER_SHA256:
        return None
    return BadgeResult(content=content, media_type=media_type, digest=digest)


def resolve_badge(
    provider_team_id: int,
    *,
    now: datetime | None = None,
    downloader: Callable[[int], BadgeResult | None] = _download,
) -> BadgeResult | None:
    if provider_team_id <= 0:
        return None
    current_time = now or datetime.now(timezone.utc)
    with _cache_lock:
        cached = _cache.get(provider_team_id)
    if cached and current_time < cached.fresh_until:
        if cached.content is None or cached.media_type is None or cached.digest is None:
            return None
        return BadgeResult(cached.content, cached.media_type, cached.digest)

    try:
        downloaded = downloader(provider_team_id)
    except (requests.RequestException, RuntimeError):
        if cached and cached.content and cached.media_type and cached.digest and current_time < cached.stale_until:
            return BadgeResult(cached.content, cached.media_type, cached.digest, stale=True)
        return None

    if downloaded is None:
        if cached and cached.content and cached.media_type and cached.digest and current_time < cached.stale_until:
            return BadgeResult(cached.content, cached.media_type, cached.digest, stale=True)
        negative = CachedBadge(None, None, None, current_time + NEGATIVE_TTL, current_time + NEGATIVE_TTL)
        with _cache_lock:
            _cache[provider_team_id] = negative
        return None

    stored = CachedBadge(
        downloaded.content,
        downloaded.media_type,
        downloaded.digest,
        current_time + FRESH_TTL,
        current_time + FRESH_TTL + STALE_TTL,
    )
    with _cache_lock:
        _cache[provider_team_id] = stored
    return downloaded


def clear_badge_cache() -> None:
    """Test helper; production cache lifetime is process-bounded."""
    with _cache_lock:
        _cache.clear()
