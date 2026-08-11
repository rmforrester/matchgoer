from datetime import datetime
from pydantic import BaseModel, Field

class VenueResponse(BaseModel):

    venue_id: int
    name: str
    city: str | None = None
    latitude: float | None = None
    longitude: float | None = None

    class Config:
        from_attributes = True


class FixtureResponse(BaseModel):

    fixture_id: int
    fixture_date: datetime

    home_team: str
    away_team: str

    league_name: str

    interested_count: int = 0

    class Config:
        from_attributes = True


class FixtureWithVenueResponse(BaseModel):

    fixture_id: int
    fixture_date: datetime

    home_team: str
    away_team: str

    league_name: str

    venue: VenueResponse | None = None

    class Config:
        from_attributes = True


class MatchdayTipCreate(BaseModel):

    venue_id: int
    tip: str


class MatchdayTipResponse(BaseModel):

    tip_id: int
    venue_id: int
    tip: str
    helpful_votes: int
    report_count: int
    status: str

    class Config:
        from_attributes = True


# =========================================================
# AWAY DAY REVIEWS
# =========================================================

class AwayDayReviewCreate(BaseModel):

    venue_id: int

    fixture_id: int | None = None

    visit_date: datetime | None = None

    recommend: bool | None = None

    overall_score: int | None = Field(
        default=None,
        ge=1,
        le=10
    )

    atmosphere_score: int | None = Field(
        default=None,
        ge=1,
        le=10
    )

    pubs_score: int | None = Field(
        default=None,
        ge=1,
        le=10
    )

    getting_there_score: int | None = Field(
        default=None,
        ge=1,
        le=10
    )

    facilities_score: int | None = Field(
        default=None,
        ge=1,
        le=10
    )

class AwayDayReviewUpdate(BaseModel):

    recommend: bool | None = None

    overall_score: int | None = Field(
        default=None,
        ge=1,
        le=10
    )

    atmosphere_score: int | None = Field(
        default=None,
        ge=1,
        le=10
    )

    pubs_score: int | None = Field(
        default=None,
        ge=1,
        le=10
    )

    getting_there_score: int | None = Field(
        default=None,
        ge=1,
        le=10
    )

    facilities_score: int | None = Field(
        default=None,
        ge=1,
        le=10
    )

class AwayDayReviewResponse(BaseModel):

    review_id: int
    venue_id: int

    recommend: bool | None = None

    overall_score: float | None = None
    atmosphere_score: int | None = None
    pubs_score: int | None = None
    getting_there_score: int | None = None
    facilities_score: int | None = None

    created_at: datetime | None = None

    class Config:
        from_attributes = True


class AwayDayScoreResponse(BaseModel):

    away_day_score: float | None = None

    review_count: int

    recommend_percentage: float | None = None

    category_scores: dict[str, float | None]

class MyReviewResponse(BaseModel):

    review_id: int

    venue_id: int
    venue_name: str
    venue_city: str | None = None

    fixture_id: int | None = None
    fixture_date: datetime | None = None

    home_team: str | None = None
    away_team: str | None = None

    visit_date: datetime | None = None

    recommend: bool | None = None

    overall_score: float | None = None
    atmosphere_score: int | None = None
    pubs_score: int | None = None
    getting_there_score: int | None = None
    facilities_score: int | None = None

    created_at: datetime | None = None

    class Config:
            from_attributes = True