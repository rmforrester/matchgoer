"""Reviewed manual venue overrides, separate from provider ingestion logic."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ManualVenueOverride:
    provider: str
    league_id: int
    season: int
    home_team_provider_id: int
    team_name: str
    venue_name: str
    city: str
    country: str
    latitude: float
    longitude: float
    source: str = "manual_verified"


MANUAL_VENUE_OVERRIDES = (
    ManualVenueOverride(
        provider="api_football",
        league_id=253,
        season=2026,
        home_team_provider_id=25484,
        team_name="San Diego FC",
        venue_name="Snapdragon Stadium",
        city="San Diego",
        country="USA",
        latitude=32.7842418,
        longitude=-117.1223904,
    ),
    ManualVenueOverride(
        provider="api_football",
        league_id=255,
        season=2026,
        home_team_provider_id=25959,
        team_name="Sporting JAX",
        venue_name="Hodges Stadium",
        city="Jacksonville",
        country="USA",
        latitude=30.2752055,
        longitude=-81.511875,
    ),
    ManualVenueOverride(
        provider="api_football",
        league_id=255,
        season=2026,
        home_team_provider_id=27252,
        team_name="Brooklyn",
        venue_name="Maimonides Park",
        city="Brooklyn",
        country="USA",
        latitude=40.5743913,
        longitude=-73.9840186,
    ),
)


def manual_override_for(league_id: int, season: int, home_team_provider_id: int | None) -> ManualVenueOverride | None:
    matches = [
        override
        for override in MANUAL_VENUE_OVERRIDES
        if override.provider == "api_football"
        and override.league_id == league_id
        and override.season == season
        and override.home_team_provider_id == home_team_provider_id
    ]
    if len(matches) > 1:
        raise RuntimeError(
            f"Duplicate manual venue overrides for league={league_id}, season={season}, "
            f"home_team_provider_id={home_team_provider_id}"
        )
    return matches[0] if matches else None
