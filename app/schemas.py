from datetime import datetime
from pydantic import BaseModel


class FixtureResponse(BaseModel):
    fixture_id: int
    fixture_date: datetime
    venue_name: str
    venue_city: str
    league_name: str
    home_team: str
    away_team: str
    home_goals: int
    away_goals: int

    class Config:
        from_attributes = True

class VenueResponse(BaseModel):
    venue_id: int
    name: str
    address: str
    city: str
    country: str
    capacity: int
    latitude: str
    longitude: str

    class Config:
        from_attributes = True

class FixtureWithVenueResponse(BaseModel):
    fixture_id: int
    fixture_date: datetime
    home_team: str
    away_team: str
    venue: VenueNested

    class Config:
        from_attributes = True

class VenueNested(BaseModel):
    name: str
    city: str
    country: str
    latitude: str
    longitude: str

    class Config:
        from_attributes = True

class NearbyFixtureResponse(BaseModel):
    fixture_id: int
    fixture_date: datetime
    home_team: str
    away_team: str
    venue_name: str
    venue_city: str
    latitude: float
    longitude: float
    distance_miles: float

    class Config:
        from_attributes = True