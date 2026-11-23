"""Rate-limited, cached API-Football client for ingestion."""

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any

import requests

LOGGER = logging.getLogger(__name__)
BASE_URL = "https://v3.football.api-sports.io"


class ApiFootballClient:
    def __init__(self, api_key: str, cache_dir: Path, timeout: int = 30, min_request_interval: float = 1.0) -> None:
        self.session = requests.Session()
        self.session.headers.update({"x-apisports-key": api_key})
        self.cache_dir, self.timeout = cache_dir, timeout
        self.min_request_interval, self.last_request_at = min_request_interval, 0.0
        self.requests_made = self.cache_hits = 0
        self.failures: list[str] = []
        self.quota = None
        self.quota_observed_at = None
        self.last_status_code = None
        self.retry_after = None

    def quota_is_fresh(self) -> bool:
        return self.quota_observed_at is not None and 0 <= time.monotonic() - self.quota_observed_at <= 120

    def highlights_quota_available(self) -> bool:
        return bool(self.quota_is_fresh() and self.quota is not None
                    and self.quota['daily_remaining'] > 100 and self.quota['minute_remaining'] > 0
                    and self.last_status_code not in {401, 403, 429} and not self.retry_after)

    def _observe_quota(self, response) -> None:
        self.last_status_code = response.status_code
        self.retry_after = response.headers.get('Retry-After')
        self.quota_observed_at = time.monotonic()
        self.quota = None
        try:
            daily = int(response.headers['x-ratelimit-requests-remaining'])
            minute = int(response.headers['x-ratelimit-remaining'])
            if daily >= 0 and minute >= 0:
                self.quota = dict(daily_remaining=daily, minute_remaining=minute)
        except (KeyError, TypeError, ValueError):
            pass

    def _cache_path(self, endpoint: str, params: dict[str, Any]) -> Path:
        identity = json.dumps([endpoint, sorted(params.items())], separators=(",", ":"))
        return self.cache_dir / f"{endpoint.strip('/').replace('/', '_')}-{hashlib.sha256(identity.encode()).hexdigest()}.json"

    def get(self, endpoint: str, *, use_cache: bool = True, **params: Any) -> list[dict[str, Any]]:
        cache_path = self._cache_path(endpoint, params)
        if use_cache and cache_path.exists():
            self.cache_hits += 1
            return json.loads(cache_path.read_text(encoding="utf-8"))["response"]
        delay = self.min_request_interval - (time.monotonic() - self.last_request_at)
        if delay > 0:
            time.sleep(delay)
        LOGGER.info("API-Football request: %s %s", endpoint, params)
        self.requests_made += 1
        self.last_request_at = time.monotonic()
        try:
            response = self.session.get(f"{BASE_URL}{endpoint}", params=params, timeout=self.timeout)
            self.last_request_at = time.monotonic()
            self._observe_quota(response)
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as error:
            message = f"{endpoint} {params}: {error}"
            self.failures.append(message)
            raise RuntimeError(message) from error
        if not isinstance(payload, dict) or not (isinstance(payload.get("response", []), list) or
                                                   endpoint == "/status" and isinstance(payload.get("response"), dict)):
            message = f"{endpoint}: malformed provider response"
            self.failures.append(message)
            raise RuntimeError(message)
        if payload.get("errors"):
            message = f"{endpoint} {params}: {payload['errors']}"
            self.failures.append(message)
            raise RuntimeError(message)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return payload.get("response", [])

    def leagues_by_country(self, country: str) -> list[dict[str, Any]]:
        return self.get("/leagues", country=country)

    def league_for_season(self, league_id: int, season: int) -> list[dict[str, Any]]:
        return self.get("/leagues", id=league_id, season=season)

    def teams(self, league_id: int, season: int) -> list[dict[str, Any]]:
        return self.get("/teams", league=league_id, season=season)

    def fixtures(self, league_id: int, season: int) -> list[dict[str, Any]]:
        return self.get("/fixtures", league=league_id, season=season)

    def fixtures_between(self, league_id: int, season: int, from_date: str, to_date: str) -> list[dict[str, Any]]:
        """Always fetch mutable fixture state; refreshes must never use stale cache."""
        return self.get(
            "/fixtures",
            use_cache=False,
            league=league_id,
            season=season,
            **{"from": from_date, "to": to_date},
        )

    def fixtures_by_ids(self, fixture_ids: list[int]) -> list[dict[str, Any]]:
        """Fetch mutable fixture state by up to 20 authoritative IDs, uncached."""
        if not fixture_ids:
            return []
        if len(fixture_ids) > 20:
            raise ValueError("API-Football accepts at most 20 fixture IDs per request")
        return self.get("/fixtures", use_cache=False, ids="-".join(map(str, fixture_ids)))
