"""Idempotent API-Football dry-run and write pipeline."""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import MetaData, Table, create_engine, select

from config.leagues import LeagueScope
from config.venue_overrides import ManualVenueOverride, manual_override_for
from ingestion.api_football import ApiFootballClient
from ingestion.coordinates import NominatimCoordinateEnricher, valid_coordinates


@dataclass
class QaReport:
    country: str
    league: str
    league_id: int | None
    provider_season: int
    display_season: str
    season_available: bool = False
    fixture_coverage: str = "unavailable"
    team_coverage: str = "unavailable"
    venue_availability: str = "unavailable"
    teams: int = 0
    venues: int = 0
    fixtures: int = 0
    new_teams: int = 0
    updated_teams: int = 0
    new_venues: int = 0
    updated_venues: int = 0
    new_fixtures: int = 0
    updated_fixtures: int = 0
    fixtures_linked_to_venues: int = 0
    fixtures_missing_venue: int = 0
    fixtures_linked_fixture_provider: int = 0
    fixtures_linked_fixture_provider_name: int = 0
    fixtures_linked_home_team_fallback: int = 0
    fixtures_linked_manual_verified: int = 0
    fixtures_direct_home_team_conflicts: int = 0
    teams_without_venue_ids: int = 0
    venues_with_valid_coordinates: int = 0
    venues_missing_coordinates: int = 0
    coordinates_requiring_geocoding: int = 0
    unresolved_geocoding: int = 0
    unresolved_venues: list[dict[str, Any]] = field(default_factory=list)
    ambiguous_venue_matches: list[dict[str, Any]] = field(default_factory=list)
    observed_venue_name_candidates: list[dict[str, Any]] = field(default_factory=list)
    provider_reference_review_candidates: list[dict[str, Any]] = field(default_factory=list)
    duplicate_provider_ids: list[str] = field(default_factory=list)
    failed_api_requests: list[str] = field(default_factory=list)
    api_requests: int = 0
    api_cache_hits: int = 0

    def serializable(self) -> dict[str, Any]:
        return asdict(self)


class TerraceTalkImporter:
    def __init__(self, client: ApiFootballClient, database_url: str) -> None:
        self.client = client
        self.engine = create_engine(database_url, connect_args={"connect_timeout": 10})
        metadata = MetaData()
        metadata.reflect(
            self.engine,
            only=["fixtures", "venues", "teams", "venue_names", "venue_provider_refs"],
        )
        self.fixtures: Table = metadata.tables["fixtures"]
        self.venues: Table = metadata.tables["venues"]
        self.teams: Table = metadata.tables["teams"]
        self.venue_names: Table = metadata.tables["venue_names"]
        self.venue_provider_refs: Table = metadata.tables["venue_provider_refs"]

    @staticmethod
    def _normalize_venue_name(value: str) -> str:
        return " ".join(re.sub(r"[-\u2010-\u2015]+", " ", value.strip().lower()).split())

    @classmethod
    def _normalize_venue_identity_name(cls, value: str) -> str:
        normalized = unicodedata.normalize("NFKD", cls._normalize_venue_name(value))
        ascii_name = "".join(character for character in normalized if not unicodedata.combining(character))
        return re.sub(r"^(?:stadium|stadion)\s+", "", ascii_name)

    def _canonical_venue_name_mapping(self, connection) -> dict[str, int]:
        """Exact venue identity aliases derived from linked canonical team names.

        Provider strings such as ``Stadium Viktoria Zizkov`` identify the venue
        through the resident club identity. Ordinary venue labels are not
        inferred here: a direct name/default conflict must otherwise remain a
        reviewed decision rather than silently changing an established link.
        """
        candidates: dict[str, set[int]] = {}

        def add(name: str | None, venue_id: int | None) -> None:
            if not name or venue_id is None:
                return
            key = self._normalize_venue_identity_name(name)
            if key:
                candidates.setdefault(key, set()).add(venue_id)

        for row in connection.execute(
            select(self.teams.c.venue_id, self.teams.c.team_name).where(self.teams.c.venue_id.is_not(None))
        ):
            add(row.team_name, row.venue_id)
        return {name: next(iter(venue_ids)) for name, venue_ids in candidates.items() if len(venue_ids) == 1}

    @staticmethod
    def _venue_update_values(values: dict[str, Any]) -> dict[str, Any]:
        """Provider omissions must not erase established hosted venue metadata."""
        return {
            key: value for key, value in values.items()
            if key != "provider_venue_id" and value is not None
        }

    def _provider_mapping(self, connection, provider_ids: set[int]) -> dict[int, int]:
        if not provider_ids:
            return {}
        mapping = dict(connection.execute(
            select(
                self.venue_provider_refs.c.provider_venue_id,
                self.venue_provider_refs.c.venue_id,
            ).where(
                self.venue_provider_refs.c.provider == "api_football",
                self.venue_provider_refs.c.provider_venue_id.in_(provider_ids),
            )
        ).all())
        missing = provider_ids - set(mapping)
        if missing:
            mapping.update(dict(connection.execute(
                select(self.venues.c.provider_venue_id, self.venues.c.venue_id)
                .where(self.venues.c.provider_venue_id.in_(missing))
            ).all()))
        return mapping

    def _sync_current_name(self, connection, venue_id: int, name: str | None, source: str) -> str | None:
        if not name or not name.strip():
            return name
        normalized = self._normalize_venue_name(name)
        current = connection.execute(
            select(
                self.venue_names.c.venue_name_id,
                self.venue_names.c.name,
                self.venue_names.c.normalized_name,
                self.venue_names.c.source,
            )
            .where(
                self.venue_names.c.venue_id == venue_id,
                self.venue_names.c.name_type == "current",
            )
        ).first()
        if current and self._normalize_venue_name(current.name) == normalized:
            return current.name
        if current and (current.source or "").startswith("reviewed_") and source == "api_football":
            return current.name
        if current:
            connection.execute(
                self.venue_names.update()
                .where(self.venue_names.c.venue_name_id == current.venue_name_id)
                .values(name_type="historical")
            )
        existing = connection.execute(
            select(self.venue_names.c.venue_name_id).where(
                self.venue_names.c.venue_id == venue_id,
                self.venue_names.c.normalized_name == normalized,
            )
        ).scalar_one_or_none()
        values = {"name": name.strip(), "name_type": "current", "valid_to": None, "source": source}
        if existing is None:
            connection.execute(self.venue_names.insert().values(
                venue_id=venue_id, normalized_name=normalized, **values
            ))
        else:
            connection.execute(
                self.venue_names.update()
                .where(self.venue_names.c.venue_name_id == existing)
                .values(**values)
            )
        return name.strip()

    @staticmethod
    def _accepted_checkpoint_coordinates() -> dict[int, tuple[float, float]]:
        checkpoint_path = Path(__file__).resolve().parents[1] / ".cache" / "nominatim" / "coordinate-dry-run-2026.json"
        if not checkpoint_path.exists():
            return {}
        payload = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        return {
            int(venue_id): (float(result["latitude"]), float(result["longitude"]))
            for venue_id, result in payload.items()
            if result.get("status") == "geocoded"
            and valid_coordinates(result.get("latitude"), result.get("longitude"))
        }

    def _existing_ids(self, table: Table, column: str, identifiers: set[int]) -> set[int]:
        if not identifiers:
            return set()
        with self.engine.connect() as connection:
            return set(connection.execute(select(table.c[column]).where(table.c[column].in_(identifiers))).scalars())

    def _records(self, scope: LeagueScope) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool]:
        if scope.league_id is None:
            raise ValueError("A resolved API-Football league ID is required for import.")
        coverage = self.client.league_for_season(scope.league_id, scope.provider_season)
        available = bool(coverage and any(item.get("league", {}).get("id") == scope.league_id for item in coverage))
        if not available:
            return [], [], False
        return self.client.teams(scope.league_id, scope.provider_season), self.client.fixtures(scope.league_id, scope.provider_season), True

    @staticmethod
    def _venue_record(raw: dict[str, Any], country: str) -> dict[str, Any] | None:
        if not raw.get("id"):
            return None
        return {
            "provider_venue_id": raw["id"], "name": raw.get("name"), "address": raw.get("address"),
            "city": raw.get("city"), "country": raw.get("country") or country,
            "capacity": raw.get("capacity"), "latitude": raw.get("latitude"), "longitude": raw.get("longitude"),
        }

    @staticmethod
    def _home_team_venues(team_payloads: list[dict[str, Any]]) -> dict[int, int]:
        return {
            item["team"]["id"]: item["venue"]["id"]
            for item in team_payloads
            if item.get("team", {}).get("id") and item.get("venue", {}).get("id")
        }

    @staticmethod
    def _fixture_venue_link(
        fixture: dict[str, Any],
        home_team_id: int | None,
        home_team_venues: dict[int, int],
        scope: LeagueScope,
        canonical_name_venues: dict[str, int] | None = None,
    ) -> tuple[int | None, str, int | None, ManualVenueOverride | None]:
        direct_venue_id = (fixture.get("venue") or {}).get("id")
        home_team_venue_id = home_team_venues.get(home_team_id) if home_team_id else None
        override = manual_override_for(
            scope.league_id,
            scope.provider_season,
            home_team_id,
            fixture.get("id"),
        )
        if override:
            return None, override.source, home_team_venue_id, override
        if direct_venue_id:
            return direct_venue_id, "fixture_provider", home_team_venue_id, None
        direct_venue_name = (fixture.get("venue") or {}).get("name")
        if direct_venue_name and canonical_name_venues:
            internal_venue_id = canonical_name_venues.get(
                TerraceTalkImporter._normalize_venue_identity_name(direct_venue_name)
            )
            if internal_venue_id is not None:
                return internal_venue_id, "fixture_provider_name", home_team_venue_id, None
        if home_team_venue_id:
            return home_team_venue_id, "home_team_fallback", None, None
        return None, "unresolved", None, None

    def dry_run(self, scope: LeagueScope) -> QaReport:
        report = QaReport(scope.country, scope.display_name, scope.league_id, scope.provider_season, scope.display_season)
        try:
            team_payloads, fixture_payloads, report.season_available = self._records(scope)
        except RuntimeError:
            report.failed_api_requests = self.client.failures.copy()
            report.api_requests, report.api_cache_hits = self.client.requests_made, self.client.cache_hits
            return report
        if not report.season_available:
            report.failed_api_requests.append("League or requested provider season is unavailable.")
            return report
        report.fixture_coverage = "available" if fixture_payloads else "available, no fixtures returned"
        report.team_coverage = "available" if team_payloads else "available, no teams returned"
        teams: dict[int, dict[str, Any]] = {}
        venues: dict[int, dict[str, Any]] = {}
        manual_overrides: set[ManualVenueOverride] = set()
        fixture_ids: set[int] = set()
        for item in team_payloads:
            team = item.get("team", {})
            if team.get("id"):
                if team["id"] in teams:
                    report.duplicate_provider_ids.append(f"team:{team['id']}")
                teams[team["id"]] = team
            venue = self._venue_record(item.get("venue") or {}, scope.country)
            if venue:
                if venue["provider_venue_id"] in venues:
                    report.duplicate_provider_ids.append(f"venue:{venue['provider_venue_id']}")
                venues[venue["provider_venue_id"]] = venue
        home_team_venues = self._home_team_venues(team_payloads)
        with self.engine.connect() as connection:
            canonical_name_venues = self._canonical_venue_name_mapping(connection)
        report.teams_without_venue_ids = len(teams) - len(home_team_venues)
        for item in fixture_payloads:
            fixture = item.get("fixture", {})
            fixture_id = fixture.get("id")
            home_team_id = item.get("teams", {}).get("home", {}).get("id")
            if fixture_id in fixture_ids:
                report.duplicate_provider_ids.append(f"fixture:{fixture_id}")
            elif fixture_id:
                fixture_ids.add(fixture_id)
            venue_id, link_source, home_team_venue_id, override = self._fixture_venue_link(
                fixture, home_team_id, home_team_venues, scope, canonical_name_venues
            )
            if link_source == "fixture_provider":
                report.fixtures_linked_fixture_provider += 1
                if home_team_venue_id and home_team_venue_id != venue_id:
                    report.fixtures_direct_home_team_conflicts += 1
            elif link_source == "fixture_provider_name":
                report.fixtures_linked_fixture_provider_name += 1
            elif link_source == "home_team_fallback":
                report.fixtures_linked_home_team_fallback += 1
                observed_name = (fixture.get("venue") or {}).get("name")
                if observed_name and venue_id:
                    report.observed_venue_name_candidates.append({
                        "fixture_id": fixture_id,
                        "provider_venue_id": venue_id,
                        "observed_name": observed_name,
                        "reason": "fixture venue name observed without a fixture provider venue ID",
                    })
            elif link_source == "manual_verified":
                report.fixtures_linked_manual_verified += 1
                if override:
                    manual_overrides.add(override)
            else:
                report.unresolved_venues.append({
                    "fixture_id": fixture_id,
                    "home_team_id": home_team_id,
                    "reason": "fixture and home-team provider venue IDs missing",
                })
            venue = self._venue_record(fixture.get("venue") or {}, scope.country)
            if venue:
                venues.setdefault(venue["provider_venue_id"], venue)
        report.teams, report.venues, report.fixtures = len(teams), len(venues) + len(manual_overrides), len(fixture_ids)
        report.venue_availability = "available" if venues else "not exposed by team/fixture responses"
        old_teams = self._existing_ids(self.teams, "team_id", set(teams))
        with self.engine.connect() as connection:
            old_venues = set(self._provider_mapping(connection, set(venues)))
            existing_venues = connection.execute(select(
                self.venues.c.venue_id, self.venues.c.provider_venue_id, self.venues.c.name,
                self.venues.c.address, self.venues.c.city,
                self.venues.c.latitude, self.venues.c.longitude,
            )).all()
        for provider_id in set(venues) - old_venues:
            candidate = venues[provider_id]
            candidate_address = (candidate.get("address") or "").strip().lower()
            candidate_city = (candidate.get("city") or "").strip().lower()
            for existing in existing_venues:
                same_address = bool(candidate_address and candidate_city) and (
                    candidate_address == (existing.address or "").strip().lower()
                    and candidate_city == (existing.city or "").strip().lower()
                )
                same_coordinates = (
                    valid_coordinates(candidate.get("latitude"), candidate.get("longitude"))
                    and valid_coordinates(existing.latitude, existing.longitude)
                    and float(candidate["latitude"]) == float(existing.latitude)
                    and float(candidate["longitude"]) == float(existing.longitude)
                )
                if same_address or same_coordinates:
                    report.provider_reference_review_candidates.append({
                        "incoming_provider_venue_id": provider_id,
                        "incoming_name": candidate.get("name"),
                        "existing_venue_id": existing.venue_id,
                        "existing_provider_venue_id": existing.provider_venue_id,
                        "existing_name": existing.name,
                        "evidence": "exact address/city" if same_address else "exact coordinates",
                        "action": "review; never auto-merge",
                    })
        with self.engine.connect() as connection:
            existing_manual_venues = sum(
                connection.execute(
                    select(self.venues.c.venue_id).where(
                        self.venues.c.provider_venue_id.is_(None),
                        self.venues.c.name == override.venue_name,
                        self.venues.c.city == override.city,
                        self.venues.c.country == override.country,
                    )
                ).scalar_one_or_none() is not None
                for override in manual_overrides
            )
        old_fixtures = self._existing_ids(self.fixtures, "fixture_id", fixture_ids)
        report.new_teams, report.updated_teams = len(teams) - len(old_teams), len(old_teams)
        report.new_venues = len(venues) - len(old_venues) + len(manual_overrides) - existing_manual_venues
        report.updated_venues = len(old_venues) + existing_manual_venues
        report.new_fixtures, report.updated_fixtures = len(fixture_ids) - len(old_fixtures), len(old_fixtures)
        report.fixtures_linked_to_venues = (
            report.fixtures_linked_fixture_provider
            + report.fixtures_linked_fixture_provider_name
            + report.fixtures_linked_home_team_fallback
            + report.fixtures_linked_manual_verified
        )
        report.fixtures_missing_venue = report.fixtures - report.fixtures_linked_to_venues
        accepted_coordinates = self._accepted_checkpoint_coordinates()
        with self.engine.connect() as connection:
            provider_mapping = self._provider_mapping(connection, set(venues))
            coordinates_by_venue = {
                row.venue_id: (row.latitude, row.longitude)
                for row in connection.execute(
                select(self.venues.c.venue_id, self.venues.c.latitude, self.venues.c.longitude)
                .where(self.venues.c.venue_id.in_(set(provider_mapping.values())))
                )
            }
            existing_coordinates = {
                provider_id: coordinates_by_venue.get(venue_id, (None, None))
                for provider_id, venue_id in provider_mapping.items()
            }
        report.venues_with_valid_coordinates = sum(
            valid_coordinates(*existing_coordinates.get(venue_id, (None, None)))
            or valid_coordinates(*accepted_coordinates.get(venue_id, (None, None)))
            for venue_id in venues
        ) + sum(valid_coordinates(override.latitude, override.longitude) for override in manual_overrides)
        report.venues_missing_coordinates = report.venues - report.venues_with_valid_coordinates
        report.coordinates_requiring_geocoding = report.unresolved_geocoding = report.venues_missing_coordinates
        report.failed_api_requests = self.client.failures.copy()
        report.api_requests, report.api_cache_hits = self.client.requests_made, self.client.cache_hits
        return report

    def write_import(self, scope: LeagueScope, geocode: bool = True) -> QaReport:
        """Idempotent upsert; never deletes data and updates mutable fixtures."""
        report = self.dry_run(scope)
        if not report.season_available:
            return report
        team_payloads, fixture_payloads, _ = self._records(scope)
        teams = {
            item["team"]["id"]: {
                **item["team"],
                "provider_venue_id": (item.get("venue") or {}).get("id"),
            }
            for item in team_payloads
            if item.get("team", {}).get("id")
        }
        home_team_venues = self._home_team_venues(team_payloads)
        venues: dict[int, dict[str, Any]] = {}
        for item in [*team_payloads, *fixture_payloads]:
            raw = item.get("venue") or (item.get("fixture") or {}).get("venue") or {}
            venue = self._venue_record(raw, scope.country)
            if venue:
                venues.setdefault(venue["provider_venue_id"], venue)
        with self.engine.connect() as connection:
            provider_mapping = self._provider_mapping(connection, set(venues))
            coordinates_by_venue = {
                row.venue_id: (row.latitude, row.longitude)
                for row in connection.execute(
                select(self.venues.c.venue_id, self.venues.c.latitude, self.venues.c.longitude)
                .where(self.venues.c.venue_id.in_(set(provider_mapping.values())))
                )
            }
            existing_coordinates = {
                provider_id: coordinates_by_venue.get(venue_id, (None, None))
                for provider_id, venue_id in provider_mapping.items()
            }
        accepted_coordinates = self._accepted_checkpoint_coordinates()
        enricher = NominatimCoordinateEnricher() if geocode else None
        for venue in venues.values():
            provider_venue_id = venue["provider_venue_id"]
            saved_coordinates = existing_coordinates.get(provider_venue_id)
            audited_coordinates = accepted_coordinates.get(provider_venue_id)
            if saved_coordinates and valid_coordinates(*saved_coordinates):
                venue["latitude"], venue["longitude"] = saved_coordinates
            elif audited_coordinates and valid_coordinates(*audited_coordinates):
                venue["latitude"], venue["longitude"] = audited_coordinates
            else:
                # Provider payload coordinates are not accepted without audit.
                venue["latitude"], venue["longitude"] = None, None
                if enricher is not None:
                    result = enricher.enrich(venue)
                    venue["latitude"], venue["longitude"] = result.latitude, result.longitude
        with self.engine.begin() as connection:
            canonical_name_venues = self._canonical_venue_name_mapping(connection)
            provider_to_internal = self._provider_mapping(connection, set(venues))
            for provider_venue_id, values in venues.items():
                internal_venue_id = provider_to_internal.get(provider_venue_id)
                if internal_venue_id is None:
                    internal_venue_id = connection.execute(
                        self.venues.insert().values(**values).returning(self.venues.c.venue_id)
                    ).scalar_one()
                    self._sync_current_name(connection, internal_venue_id, values.get("name"), "api_football")
                else:
                    mutable_values = self._venue_update_values(values)
                    mutable_values["name"] = self._sync_current_name(
                        connection, internal_venue_id, values.get("name"), "api_football"
                    )
                    connection.execute(
                        self.venues.update().where(self.venues.c.venue_id == internal_venue_id).values(**mutable_values)
                    )
                existing_ref = connection.execute(select(self.venue_provider_refs.c.venue_provider_ref_id).where(
                    self.venue_provider_refs.c.provider == "api_football",
                    self.venue_provider_refs.c.provider_venue_id == provider_venue_id,
                )).scalar_one_or_none()
                if existing_ref is None:
                    has_primary = connection.execute(select(self.venue_provider_refs.c.venue_provider_ref_id).where(
                        self.venue_provider_refs.c.venue_id == internal_venue_id,
                        self.venue_provider_refs.c.provider == "api_football",
                        self.venue_provider_refs.c.is_primary.is_(True),
                    )).scalar_one_or_none() is not None
                    connection.execute(self.venue_provider_refs.insert().values(
                        venue_id=internal_venue_id, provider="api_football",
                        provider_venue_id=provider_venue_id, is_primary=not has_primary,
                    ))
                provider_to_internal[provider_venue_id] = internal_venue_id

            manual_internal_ids: dict[ManualVenueOverride, int] = {}
            for item in fixture_payloads:
                fixture = item.get("fixture") or {}
                home_team_id = (item.get("teams") or {}).get("home", {}).get("id")
                _, link_source, _, override = self._fixture_venue_link(
                    fixture, home_team_id, home_team_venues, scope, canonical_name_venues
                )
                if link_source != "manual_verified" or override is None or override in manual_internal_ids:
                    continue
                internal_venue_id = connection.execute(
                    select(self.venues.c.venue_id).where(
                        self.venues.c.provider_venue_id.is_(None),
                        self.venues.c.name == override.venue_name,
                        self.venues.c.city == override.city,
                        self.venues.c.country == override.country,
                    )
                ).scalar_one_or_none()
                manual_values = {
                    "provider_venue_id": None, "name": override.venue_name, "address": None,
                    "city": override.city, "country": override.country, "capacity": None,
                    "latitude": override.latitude, "longitude": override.longitude,
                }
                if internal_venue_id is None:
                    internal_venue_id = connection.execute(
                        self.venues.insert().values(**manual_values).returning(self.venues.c.venue_id)
                    ).scalar_one()
                else:
                    connection.execute(
                        self.venues.update().where(self.venues.c.venue_id == internal_venue_id).values(**manual_values)
                    )
                self._sync_current_name(connection, internal_venue_id, override.venue_name, override.source)
                manual_internal_ids[override] = internal_venue_id
            for team_id, team in teams.items():
                values = {
                    "team_name": team.get("name"),
                    "venue_id": provider_to_internal.get(team.get("provider_venue_id")),
                    "active": not bool(team.get("national")),
                }
                if connection.execute(select(self.teams.c.team_id).where(self.teams.c.team_id == team_id)).scalar_one_or_none() is None:
                    connection.execute(self.teams.insert().values(team_id=team_id, **values))
                else:
                    connection.execute(self.teams.update().where(self.teams.c.team_id == team_id).values(**values))
            for item in fixture_payloads:
                fixture, league, teams_payload, goals = item["fixture"], item["league"], item["teams"], item["goals"]
                venue = fixture.get("venue") or {}
                provider_venue_id, link_source, _, override = self._fixture_venue_link(
                    fixture, teams_payload["home"]["id"], home_team_venues, scope, canonical_name_venues
                )
                internal_venue_id = (
                    manual_internal_ids.get(override) if link_source == "manual_verified"
                    else provider_venue_id if link_source == "fixture_provider_name"
                    else provider_to_internal.get(provider_venue_id)
                )
                venue_name = override.venue_name if override else venue.get("name")
                venue_city = override.city if override else venue.get("city")
                values = {"fixture_date": datetime.fromisoformat(fixture["date"].replace("Z", "+00:00")), "venue_id": internal_venue_id, "venue_name": venue_name, "venue_city": venue_city, "league_id": league["id"], "league_name": league["name"], "country": league.get("country") or scope.country, "season": scope.provider_season, "round": league.get("round"), "status": fixture.get("status", {}).get("short"), "home_team_id": teams_payload["home"]["id"], "home_team": teams_payload["home"]["name"], "away_team_id": teams_payload["away"]["id"], "away_team": teams_payload["away"]["name"], "home_goals": goals.get("home"), "away_goals": goals.get("away")}
                where = self.fixtures.c.fixture_id == fixture["id"]
                if connection.execute(select(self.fixtures.c.fixture_id).where(where)).scalar_one_or_none() is None:
                    connection.execute(self.fixtures.insert().values(fixture_id=fixture["id"], **values))
                else:
                    connection.execute(self.fixtures.update().where(where).values(**values))
        return report
