from fastapi import FastAPI
from sqlalchemy import cast, Date, func
from geopy.distance import geodesic

from .database import SessionLocal
from .models import Fixture, Venue
from .schemas import (
    FixtureResponse,
    VenueResponse,
    FixtureWithVenueResponse,
    NearbyFixtureResponse
)

app = FastAPI(title="Matchgoer API")


@app.get("/fixtures", response_model=list[FixtureWithVenueResponse])
def get_fixtures(date: str | None = None):

    db = SessionLocal()

    query = db.query(Fixture)

    if date:
        query = query.filter(
            cast(Fixture.fixture_date, Date) == date
        )

    fixtures = query.limit(500).all()

    db.close()

    return fixtures

@app.get("/venues", response_model=list[VenueResponse])
def get_venues():

    db = SessionLocal()

    venues = db.query(Venue).limit(100).all()

    db.close()

    return venues

@app.get("/nearby", response_model=list[NearbyFixtureResponse])
def get_nearby(
    latitude: float,
    longitude: float,
    radius: float = 50,
    date: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    league: str | None = None,
    limit: int = 20,
    offset: int = 0,
    season: int = 2026
):

    db = SessionLocal()

    query = db.query(Fixture)
    query = query.filter(
    Fixture.season == season
)

    if date:
        query = query.filter(
            cast(Fixture.fixture_date, Date) == date
    )

    if start_date and end_date:
        query = query.filter(
            cast(Fixture.fixture_date, Date).between(
            start_date,
            end_date
        )
    )

    if league:
        query = query.filter(
            func.lower(Fixture.league_name) == league.lower()
    )

    fixtures = query.all()

    results = []

    for fixture in fixtures:

        if fixture.venue:

            venue_location = (
                fixture.venue.latitude,
                fixture.venue.longitude
            )

            user_location = (
                latitude,
                longitude
            )

            distance = geodesic(
                user_location,
                venue_location
            ).miles

            if distance <= radius:

                results.append({
                    "fixture_id": fixture.fixture_id,
                    "fixture_date": fixture.fixture_date,
                    "home_team": fixture.home_team,
                    "away_team": fixture.away_team,
                    "venue_name": fixture.venue.name,
                    "venue_city": fixture.venue.city,
                    "latitude": fixture.venue.latitude,
                    "longitude": fixture.venue.longitude,
                    "distance_miles": round(distance, 2)
                })

    db.close()

    results.sort(
        key=lambda fixture: fixture["distance_miles"]
    )

    return results[offset:offset + limit]
