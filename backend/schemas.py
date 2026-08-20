from datetime import date, datetime
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
    status: str | None = None
    home_goals: int | None = None
    away_goals: int | None = None

    interested_count: int = 0

    class Config:
        from_attributes = True


class FixtureWithVenueResponse(BaseModel):

    fixture_id: int
    fixture_date: datetime

    home_team: str
    away_team: str

    league_name: str
    status: str | None = None
    home_goals: int | None = None
    away_goals: int | None = None

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
    recommend_percentage: float | None = None

    overall_score: float | None = None
    atmosphere_score: int | None = None
    pubs_score: int | None = None
    getting_there_score: int | None = None
    facilities_score: int | None = None

    created_at: datetime | None = None

    class Config:
            from_attributes = True


class VenueVisitCreate(BaseModel):
    visit_date: date | None = None
    fixture_id: int | None = None


class VenueVisitResponse(BaseModel):
    visit_id: int
    venue_id: int
    fixture_id: int | None = None
    visit_date: date | None = None
    source: str
    created_at: datetime

    class Config:
        from_attributes = True


class MyGroundReviewSummary(BaseModel):
    review_id: int
    state: str
    completed: bool
    overall_score: float | None = None
    recommend: bool | None = None
    atmosphere_score: int | None = None
    pubs_score: int | None = None
    getting_there_score: int | None = None
    facilities_score: int | None = None


class MyGroundFixtureSummary(BaseModel):
    fixture_id: int
    fixture_date: datetime
    home_team: str
    away_team: str


class MyGroundResponse(BaseModel):
    venue_id: int
    venue_name: str
    venue_city: str | None = None
    venue_country: str | None = None
    capacity: int | None = None
    latitude: float | None = None
    longitude: float | None = None
    visit_count: int
    first_visit_date: date | None = None
    latest_visit_date: date | None = None
    has_undated_visit: bool
    attended_fixtures: list[MyGroundFixtureSummary]
    review: MyGroundReviewSummary | None = None
    community_terrace_rating: float | None = None
    community_review_count: int
    community_recommend_percentage: float | None = None


class ProfileCreate(BaseModel):
    display_name: str = Field(min_length=2, max_length=40)
    supported_club: str | None = Field(default=None, max_length=80)


class ProfileUpdate(BaseModel):
    username: str = Field(min_length=3, max_length=30)
    display_name: str = Field(min_length=2, max_length=40)
    supported_club: str | None = Field(default=None, max_length=80)
    broad_location: str | None = Field(default=None, max_length=100)
    bio: str | None = Field(default=None, max_length=280)


class AccountContextResponse(BaseModel):
    registered: bool
    profile_complete: bool
    anonymous_session_present: bool
    anonymous_activity: bool


class MatchBoardPostCreate(BaseModel):
    body: str = Field(min_length=1, max_length=500)
    parent_post_id: int | None = None


class MeetingIntentUpdate(BaseModel):
    open_to_meet: bool


class AccountClaimResponse(BaseModel):
    user_id: int
    account_status: str
    claimed: bool
    idempotent: bool
    profile_complete: bool


class MatchBoardReportCreate(BaseModel):
    reason: str
