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
    fixture_provider_id: int | None = None
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
    ManualVenueOverride(
        provider="api_football",
        league_id=436,
        season=2026,
        home_team_provider_id=593,
        team_name="CE Europa",
        venue_name="Can Dragó",
        city="Barcelona",
        country="Spain",
        latitude=41.432594,
        longitude=2.181415,
    ),
    ManualVenueOverride(
        provider="api_football", league_id=61, season=2026,
        home_team_provider_id=94, team_name="Rennes",
        venue_name="Roazhon Park", city="Rennes", country="France",
        latitude=48.1075655, longitude=-1.7126543,
        fixture_provider_id=1552735,
    ),
    ManualVenueOverride(
        provider="api_football", league_id=61, season=2026,
        home_team_provider_id=114, team_name="Paris FC",
        venue_name="Stade Jean-Bouin", city="Paris", country="France",
        latitude=48.8433187, longitude=2.2529615,
    ),
    ManualVenueOverride(
        provider="api_football", league_id=345, season=2026,
        home_team_provider_id=560, team_name="Slavia Praha",
        venue_name="Fortuna Arena", city="Prague", country="Czech-Republic",
        latitude=50.067487, longitude=14.4797136,
    ),
    ManualVenueOverride(
        provider="api_football", league_id=357, season=2026,
        home_team_provider_id=670, team_name="Derry City",
        venue_name="The Ryan McBride Brandywell Stadium", city="Derry", country="Ireland",
        latitude=54.9904809, longitude=-7.3362743,
        fixture_provider_id=1492622,
    ),
    ManualVenueOverride(
        provider="api_football", league_id=358, season=2026,
        home_team_provider_id=11328, team_name="Kerry",
        venue_name="Mounthawk Park", city="Tralee", country="Ireland",
        latitude=52.2831897, longitude=-9.7147260,
    ),
    *(
        ManualVenueOverride(
            provider="api_football",
            league_id=758,
            season=2026,
            home_team_provider_id=team_id,
            team_name=team_name,
            venue_name="Europa Sports Park",
            city="Gibraltar",
            country="Gibraltar",
            latitude=36.110694,
            longitude=-5.34675,
        )
        for team_id, team_name in (
            (667, "Lincoln Red Imps FC"),
            (698, "St Joseph's FC"),
            (10125, "Europa FC"),
            (16130, "College 1975"),
            (16131, "Europa Point FC"),
            (16132, "Glacis United FC"),
            (16133, "Lions Gibraltar FC"),
            (16134, "Lynx FC"),
            (16135, "FC Magpies"),
            (16137, "Mons Calpe FC"),
            (16790, "FC Hound Dogs"),
        )
    ),
)


def manual_override_for(
    league_id: int,
    season: int,
    home_team_provider_id: int | None,
    fixture_provider_id: int | None = None,
) -> ManualVenueOverride | None:
    matches = [
        override
        for override in MANUAL_VENUE_OVERRIDES
        if override.provider == "api_football"
        and override.league_id == league_id
        and override.season == season
        and override.home_team_provider_id == home_team_provider_id
        and override.fixture_provider_id in (None, fixture_provider_id)
    ]
    fixture_matches = [
        override for override in matches
        if override.fixture_provider_id is not None
        and override.fixture_provider_id == fixture_provider_id
    ]
    if len(fixture_matches) > 1:
        raise RuntimeError(
            f"Duplicate manual venue overrides for league={league_id}, season={season}, "
            f"home_team_provider_id={home_team_provider_id}, fixture_provider_id={fixture_provider_id}"
        )
    if fixture_matches:
        return fixture_matches[0]
    season_matches = [override for override in matches if override.fixture_provider_id is None]
    if len(season_matches) > 1:
        raise RuntimeError(
            f"Duplicate manual venue overrides for league={league_id}, season={season}, "
            f"home_team_provider_id={home_team_provider_id}"
        )
    return season_matches[0] if season_matches else None
