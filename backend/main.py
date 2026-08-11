from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import cast, Date, func
from geopy.distance import geodesic
from database import SessionLocal

from models import (
    Fixture,
    Venue,
    MatchdayTip,
    AwayDayReview,
    User,
    AnonymousSession,
    InterestedFixture,
)

from schemas import (
    FixtureResponse,
    FixtureWithVenueResponse,
    VenueResponse,
    MatchdayTipCreate,
    AwayDayReviewCreate,
    AwayDayReviewUpdate,
    AwayDayReviewResponse,
    AwayDayScoreResponse,
    MyReviewResponse,
)

import secrets

from fastapi import FastAPI, Cookie, Response, HTTPException


app = FastAPI(
    title="Terrace Talk API"
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)


@app.get("/")
def home():
    return {
        "message": "Terrace Talk API running"
    }


@app.get(
    "/fixtures",
    response_model=list[FixtureWithVenueResponse]
)
def get_fixtures(date: str | None = None):
    db = SessionLocal()

    query = db.query(Fixture)

    if date:
        query = query.filter(
            cast(Fixture.fixture_date, Date) == date
        )

    fixtures = query.limit(100).all()

    db.close()

    return fixtures


@app.get(
    "/venues",
    response_model=list[VenueResponse]
)
def get_venues(
    latitude: float | None = None,
    longitude: float | None = None,
    radius: float = 50,
    limit: int = 100
):
    db = SessionLocal()

    venues = (
        db.query(Venue)
        .all()
    )

    # If no location is supplied, return the
    # existing default venue list.
    if latitude is None or longitude is None:
        db.close()

        return venues[:limit]

    user_location = (
        latitude,
        longitude
    )

    nearby_venues = []

    for venue in venues:

        if (
            venue.latitude is None
            or venue.longitude is None
        ):
            continue

        venue_location = (
            venue.latitude,
            venue.longitude
        )

        distance = geodesic(
            user_location,
            venue_location
        ).miles

        if distance <= radius:
            nearby_venues.append(
                (
                    distance,
                    venue
                )
            )

    # Nearest stadiums first
    nearby_venues.sort(
        key=lambda item: item[0]
    )

    db.close()

    return [
        venue
        for distance, venue
        in nearby_venues[:limit]
    ]


@app.get("/venue/{venue_id}")
def get_venue(venue_id: int):
    db = SessionLocal()

    venue = (
        db.query(Venue)
        .filter(Venue.venue_id == venue_id)
        .first()
    )

    db.close()

    return venue


@app.get("/leagues")
def get_leagues():
    db = SessionLocal()

    leagues = (
        db.query(
            Fixture.league_id,
            Fixture.league_name
        )
        .distinct()
        .order_by(Fixture.league_id)
        .all()
    )

    db.close()

    return [
        {
            "league_id": league.league_id,
            "league_name": league.league_name
        }
        for league in leagues
    ]


# =========================================================
# ANONYMOUS SESSION
# =========================================================


@app.get("/session")
def get_session(
    response: Response,
    session_id: str | None = Cookie(
        default=None,
        alias="terrace_session"
    )
):

    db = SessionLocal()

    print(
        "SESSION COOKIE RECEIVED:",
        session_id
    )

    try:

        # -----------------------------------------------------
        # Check for an existing session
        # -----------------------------------------------------

        if session_id:

            session = (
                db.query(AnonymousSession)
                .filter(
                    AnonymousSession.session_id ==
                    session_id
                )
                .first()
            )

            if session:

                return {
                    "user_id": session.user_id,
                    "anonymous": True,
                }

        # -----------------------------------------------------
        # Create a new anonymous user
        # -----------------------------------------------------

        user = User(
            is_anonymous=True
        )

        db.add(user)

        db.commit()

        db.refresh(user)

        # -----------------------------------------------------
        # Create secure random session ID
        # -----------------------------------------------------

        new_session_id = secrets.token_urlsafe(32)

        session = AnonymousSession(
            session_id=new_session_id,
            user_id=user.user_id,
        )

        db.add(session)

        db.commit()

        # -----------------------------------------------------
        # Store session ID in browser cookie
        # -----------------------------------------------------

        response.set_cookie(
            key="terrace_session",
            value=new_session_id,
            httponly=True,
            samesite="lax",
            secure=False,
            max_age=60 * 60 * 24 * 365,
        )

        return {
            "user_id": user.user_id,
            "anonymous": True,
        }

    finally:

        db.close()


@app.get("/nearby")
def get_nearby(
    latitude: float,
    longitude: float,
    radius: float = 50,
    date: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    league: str | None = None,
    season: int | None = None,
    limit: int = 20,
    offset: int = 0
):

    db = SessionLocal()

    query = db.query(Fixture)

    # Exact date

    if date:

        query = query.filter(
            cast(Fixture.fixture_date, Date) == date
        )

    # Date range

    if start_date:

        query = query.filter(
            cast(Fixture.fixture_date, Date) >= start_date
        )

    if end_date:

        query = query.filter(
            cast(Fixture.fixture_date, Date) <= end_date
        )

    # League

    if league:

        query = query.filter(
            func.lower(Fixture.league_name) == league.lower()
        )

    # Season

    if season:

        query = query.filter(
            Fixture.season == season
        )

    fixtures = query.all()

    results = []

    user_location = (
        latitude,
        longitude
    )

    for fixture in fixtures:

        if not fixture.venue:
            continue

        if (
            fixture.venue.latitude is None
            or fixture.venue.longitude is None
        ):
            continue

        venue_location = (
            fixture.venue.latitude,
            fixture.venue.longitude
        )

        distance = geodesic(
            user_location,
            venue_location
        ).miles

        if distance <= radius:

            results.append({

                "fixture_id":
                    fixture.fixture_id,

                "fixture_date":
                    fixture.fixture_date,

                "home_team":
                    fixture.home_team,

                "away_team":
                    fixture.away_team,

                "venue_id":
                    fixture.venue_id,

                "venue_name":
                    fixture.venue.name,

                "venue_city":
                    fixture.venue.city,

                "latitude":
                    fixture.venue.latitude,

                "longitude":
                    fixture.venue.longitude,

                "distance_miles":
                    round(distance, 2)

            })

    db.close()

    # Nearest first

    results.sort(
        key=lambda fixture:
        fixture["distance_miles"]
    )

    return results[
        offset:
        offset + limit
    ]


# =========================================================
# MATCHDAY TIPS
# =========================================================


@app.post("/tips")
def create_tip(data: MatchdayTipCreate):

    db = SessionLocal()

    tip = MatchdayTip(
        venue_id=data.venue_id,
        tip=data.tip,
    )

    db.add(tip)

    db.commit()

    db.refresh(tip)

    db.close()

    return tip


@app.get("/venues/{venue_id}/tips")
def get_venue_tips(venue_id: int):

    db = SessionLocal()

    tips = (
        db.query(MatchdayTip)
        .filter(
            MatchdayTip.venue_id == venue_id,
            MatchdayTip.status == "active"
        )
        .order_by(
            MatchdayTip.created_at.desc()
        )
        .all()
    )

    db.close()

    return tips


@app.post("/tips/{tip_id}/helpful")
def mark_tip_helpful(tip_id: int):

    db = SessionLocal()

    tip = (
        db.query(MatchdayTip)
        .filter(
            MatchdayTip.tip_id == tip_id
        )
        .first()
    )

    if not tip:

        db.close()

        return {
            "error": "Tip not found"
        }

    tip.helpful_votes += 1

    db.commit()

    db.refresh(tip)

    db.close()

    return tip


@app.post("/tips/{tip_id}/report")
def report_tip(tip_id: int):

    db = SessionLocal()

    tip = (
        db.query(MatchdayTip)
        .filter(
            MatchdayTip.tip_id == tip_id
        )
        .first()
    )

    if not tip:

        db.close()

        return {
            "error": "Tip not found"
        }

    tip.report_count += 1

    if tip.report_count >= 3:

        tip.status = "reported"

    db.commit()

    db.refresh(tip)

    db.close()

    return {
        "message": "Tip reported",
        "report_count": tip.report_count,
        "status": tip.status
    }


# =========================================================
# VENUE SEARCH
# =========================================================


@app.get("/venues/search")
def search_venues(
    q: str,
    limit: int = 20
):

    q = q.strip()

    if len(q) < 2:
        return []

    db = SessionLocal()

    try:

        search_term = (
            f"%{q.strip().lower()}%"
        )

        venues = (
            db.query(Venue)
            .filter(
                func.lower(
                    Venue.name
                ).like(search_term)
                |
                func.lower(
                    Venue.city
                ).like(search_term)
            )
            .order_by(Venue.name)
            .limit(limit)
            .all()
        )

        return [

            {
                "venue_id":
                    venue.venue_id,

                "name":
                    venue.name,

                "city":
                    venue.city,

                "latitude":
                    venue.latitude,

                "longitude":
                    venue.longitude,
            }

            for venue in venues

        ]

    finally:

        db.close()


# =========================================================
# AWAY DAY REVIEWS
# =========================================================


@app.post(
    "/venues/{venue_id}/away-day-reviews",
    response_model=AwayDayReviewResponse
)
def create_away_day_review(
    venue_id: int,
    data: AwayDayReviewCreate,
    session_id: str | None = Cookie(
        default=None,
        alias="terrace_session"
    )
):

    db = SessionLocal()

    try:

        # -----------------------------------------------------
        # Check anonymous session
        # -----------------------------------------------------

        if not session_id:

            raise HTTPException(
                status_code=401,
                detail="No active session"
            )

        session = (
            db.query(AnonymousSession)
            .filter(
                AnonymousSession.session_id ==
                session_id
            )
            .first()
        )

        if not session:

            raise HTTPException(
                status_code=401,
                detail="Invalid session"
            )

        # -----------------------------------------------------
        # Check venue
        # -----------------------------------------------------

        venue = (
            db.query(Venue)
            .filter(
                Venue.venue_id == venue_id
            )
            .first()
        )

        if not venue:

            raise HTTPException(
                status_code=404,
                detail="Venue not found"
            )

        # -----------------------------------------------------
        # Make sure body venue matches URL venue
        # -----------------------------------------------------

        if data.venue_id != venue_id:

            raise HTTPException(
                status_code=400,
                detail=(
                    "Venue ID in request does not "
                    "match URL"
                )
            )

        # -----------------------------------------------------
        # Check whether user already has this stadium
        # -----------------------------------------------------

        existing_review = (
            db.query(AwayDayReview)
            .filter(
                AwayDayReview.user_id ==
                session.user_id,

                AwayDayReview.venue_id ==
                venue_id
            )
            .first()
        )

        if existing_review:

            raise HTTPException(
                status_code=409,
                detail=(
                    "You have already added "
                    "this stadium"
                )
            )

        # -----------------------------------------------------
        # Check fixture if supplied
        # -----------------------------------------------------

        if data.fixture_id is not None:

            fixture = (
                db.query(Fixture)
                .filter(
                    Fixture.fixture_id ==
                    data.fixture_id
                )
                .first()
            )

            if not fixture:

                raise HTTPException(
                    status_code=404,
                    detail="Fixture not found"
                )

            if fixture.venue_id != venue_id:

                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Fixture was not played "
                        "at this venue"
                    )
                )

        # -----------------------------------------------------
        # Create stadium record
        # -----------------------------------------------------

        review = AwayDayReview(
            user_id=session.user_id,
            venue_id=venue_id,
            fixture_id=data.fixture_id,
            visit_date=data.visit_date,

            # Review fields start empty.
            # They are completed through PATCH.
            recommend=None,
            overall_score=None,
            atmosphere_score=None,
            pubs_score=None,
            getting_there_score=None,
            facilities_score=None,
        )

        db.add(review)

        db.commit()

        db.refresh(review)

        return review

    except HTTPException:

        db.rollback()

        raise

    except Exception:

        db.rollback()

        raise

    finally:

        db.close()

@app.get(
    "/venues/{venue_id}/away-day-score",
    response_model=AwayDayScoreResponse
)
def get_away_day_score(venue_id: int):

    db = SessionLocal()

    reviews = (
        db.query(AwayDayReview)
        .filter(
            AwayDayReview.venue_id == venue_id
        )
        .all()
    )

    db.close()

    review_count = len(reviews)

    if review_count == 0:
        return {
            "away_day_score": None,
            "review_count": 0,
            "recommend_percentage": None,
            "category_scores": {
                "overall_experience": None,
                "atmosphere": None,
                "pubs_restaurants": None,
                "getting_there": None,
                "stadium_food_facilities": None,
            }
        }

    # -----------------------------------------------------
    # Recommendation percentage
    # -----------------------------------------------------

    recommend_values = [
        review.recommend
        for review in reviews
        if review.recommend is not None
    ]

    if recommend_values:
        recommend_count = sum(
            1
            for value in recommend_values
            if value is True
        )

        recommend_percentage = round(
            (
                recommend_count /
                len(recommend_values)
            ) * 100,
            1
        )
    else:
        recommend_percentage = None

    # -----------------------------------------------------
    # Category averages
    # -----------------------------------------------------

    def calculate_average(values):

        valid_values = [
            value
            for value in values
            if value is not None
        ]

        if not valid_values:
            return None

        return round(
            sum(valid_values) /
            len(valid_values),
            1
        )

    overall_score = calculate_average(
        [
            review.overall_score
            for review in reviews
        ]
    )

    atmosphere_score = calculate_average(
        [
            review.atmosphere_score
            for review in reviews
        ]
    )

    pubs_score = calculate_average(
        [
            review.pubs_score
            for review in reviews
        ]
    )

    getting_there_score = calculate_average(
        [
            review.getting_there_score
            for review in reviews
        ]
    )

    facilities_score = calculate_average(
        [
            review.facilities_score
            for review in reviews
        ]
    )

    return {
        "away_day_score": overall_score,
        "review_count": review_count,
        "recommend_percentage": recommend_percentage,
        "category_scores": {
            "overall_experience": overall_score,
            "atmosphere": atmosphere_score,
            "pubs_restaurants": pubs_score,
            "getting_there": getting_there_score,
            "stadium_food_facilities": facilities_score,
        }
    }
# =========================================================
# UPDATE AWAY DAY REVIEW
# =========================================================


@app.patch(
    "/venues/{venue_id}/away-day-reviews",
    response_model=AwayDayReviewResponse
)
def update_away_day_review(
    venue_id: int,
    review_data: AwayDayReviewUpdate,
    session_id: str | None = Cookie(
        default=None,
        alias="terrace_session"
    )
):

    db = SessionLocal()

    try:

        # -------------------------------------------------
        # Check anonymous session
        # -------------------------------------------------

        if not session_id:

            raise HTTPException(
                status_code=401,
                detail="No active session"
            )

        session = (
            db.query(AnonymousSession)
            .filter(
                AnonymousSession.session_id ==
                session_id
            )
            .first()
        )

        if not session:

            raise HTTPException(
                status_code=401,
                detail="Invalid session"
            )

        # -------------------------------------------------
        # Find the user's existing stadium visit
        # -------------------------------------------------

        review = (
            db.query(AwayDayReview)
            .filter(
                AwayDayReview.user_id ==
                session.user_id,

                AwayDayReview.venue_id ==
                venue_id
            )
            .first()
        )

        if not review:

            raise HTTPException(
                status_code=404,
                detail=(
                    "You must add this stadium "
                    "to your stadiums before "
                    "reviewing it"
                )
            )

        # -------------------------------------------------
        # Update review fields
        # -------------------------------------------------

        review.recommend = (
            review_data.recommend
        )

        review.atmosphere_score = (
            review_data.atmosphere_score
        )

        review.pubs_score = (
            review_data.pubs_score
        )

        review.getting_there_score = (
            review_data.getting_there_score
        )

        review.facilities_score = (
            review_data.facilities_score
        )

        # -------------------------------------------------
        # Calculate overall score
        #
        # Overall is the average of the four
        # experience categories.
        # -------------------------------------------------

        category_scores = [
            review.atmosphere_score,
            review.pubs_score,
            review.getting_there_score,
            review.facilities_score,
        ]

        completed_scores = [
            score
            for score in category_scores
            if score is not None
        ]

        if completed_scores:

            review.overall_score = round(
                (
                    sum(completed_scores)
                    / len(completed_scores)
                ) + 1e-9,
                1
            )

        else:

            review.overall_score = None

        print(
            "CATEGORY SCORES:",
            category_scores
        )

        print(
            "COMPLETED SCORES:",
            completed_scores
        )

        print(
            "CALCULATED OVERALL:",
            review.overall_score
        )

        db.commit()

        db.refresh(review)

        return review

    except HTTPException:

        db.rollback()

        raise

    except Exception:

        db.rollback()

        raise

    finally:

        db.close()


@app.get(
    "/venues/{venue_id}/fixtures",
    response_model=list[FixtureResponse]
)
def get_venue_fixtures(
    venue_id: int,
    search: str | None = None
):

    db = SessionLocal()

    try:

        # -----------------------------------------------------
        # Make sure venue exists
        # -----------------------------------------------------

        venue = (
            db.query(Venue)
            .filter(
                Venue.venue_id == venue_id
            )
            .first()
        )

        if not venue:

            raise HTTPException(
                status_code=404,
                detail="Venue not found"
            )

        # -----------------------------------------------------
        # Find fixtures actually played at this venue
        # -----------------------------------------------------

        query = (
            db.query(Fixture)
            .filter(
                Fixture.venue_id == venue_id
            )
        )

        # -----------------------------------------------------
        # Optional team/opponent search
        # -----------------------------------------------------

        if search:

            search_term = (
                f"%{search.lower()}%"
            )

            query = query.filter(

                func.lower(
                    Fixture.home_team
                ).like(search_term)

                |

                func.lower(
                    Fixture.away_team
                ).like(search_term)

            )

        # -----------------------------------------------------
        # Most recent fixtures first
        # -----------------------------------------------------

        fixtures = (
            query
            .order_by(
                Fixture.fixture_date.desc()
            )
            .all()
        )

        # -----------------------------------------------------
        # Build response with Interested count
        # -----------------------------------------------------

        results = []

        for fixture in fixtures:

            interested_count = (
                db.query(
                    InterestedFixture
                )
                .filter(
                    InterestedFixture.fixture_id
                    == fixture.fixture_id
                )
                .count()
            )

            results.append(
                {
                    "fixture_id":
                        fixture.fixture_id,

                    "fixture_date":
                        fixture.fixture_date,

                    "home_team":
                        fixture.home_team,

                    "away_team":
                        fixture.away_team,

                    "league_name":
                        fixture.league_name,

                    "interested_count":
                        interested_count,
                }
            )

        return results

    finally:

        db.close()


# =========================================================
# INTERESTED FIXTURES
# =========================================================


@app.post(
    "/fixtures/{fixture_id}/interested"
)
def mark_fixture_interested(
    fixture_id: int,
    response: Response,
    session_id: str | None = Cookie(
        default=None,
        alias="terrace_session"
    )
):

    db = SessionLocal()

    # -----------------------------------------------------
    # Make sure the user has an anonymous session
    # -----------------------------------------------------

    user = None

    if session_id:

        session = (
            db.query(AnonymousSession)
            .filter(
                AnonymousSession.session_id ==
                session_id
            )
            .first()
        )

        if session:

            user = (
                db.query(User)
                .filter(
                    User.user_id ==
                    session.user_id
                )
                .first()
            )

    # Create anonymous user/session if needed

    if not user:

        user = User(
            is_anonymous=True
        )

        db.add(user)

        db.commit()

        db.refresh(user)

        new_session_id = (
            secrets.token_urlsafe(32)
        )

        session = AnonymousSession(
            session_id=new_session_id,
            user_id=user.user_id,
        )

        db.add(session)

        db.commit()

        response.set_cookie(
            key="terrace_session",
            value=new_session_id,
            httponly=True,
            samesite="lax",
            secure=False,
            max_age=60 * 60 * 24 * 365,
        )

    # -----------------------------------------------------
    # Make sure the fixture exists
    # -----------------------------------------------------

    fixture = (
        db.query(Fixture)
        .filter(
            Fixture.fixture_id ==
            fixture_id
        )
        .first()
    )

    if not fixture:

        db.close()

        return {
            "error": "Fixture not found"
        }

    # -----------------------------------------------------
    # Check whether already interested
    # -----------------------------------------------------

    existing = (
        db.query(InterestedFixture)
        .filter(
            InterestedFixture.user_id ==
            user.user_id,

            InterestedFixture.fixture_id ==
            fixture_id
        )
        .first()
    )

    if existing:

        db.close()

        return {
            "message": "Already interested",
            "fixture_id": fixture_id,
            "interested": True,
        }

    # -----------------------------------------------------
    # Create Interested record
    # -----------------------------------------------------

    interested = InterestedFixture(
        user_id=user.user_id,
        fixture_id=fixture_id,
    )

    db.add(interested)

    db.commit()

    db.refresh(interested)

    db.close()

    return {
        "message": "Fixture added to Interested",
        "fixture_id": fixture_id,
        "interested": True,
    }
@app.delete(
    "/fixtures/{fixture_id}/interested"
)
def remove_fixture_interested(
    fixture_id: int,
    session_id: str | None = Cookie(
        default=None,
        alias="terrace_session"
    )
):

    db = SessionLocal()

    try:

        # -----------------------------------------------------
        # Check anonymous session
        # -----------------------------------------------------

        if not session_id:

            raise HTTPException(
                status_code=401,
                detail="No active session"
            )

        session = (
            db.query(AnonymousSession)
            .filter(
                AnonymousSession.session_id ==
                session_id
            )
            .first()
        )

        if not session:

            raise HTTPException(
                status_code=401,
                detail="Invalid session"
            )

        # -----------------------------------------------------
        # Find user's interested fixture
        # -----------------------------------------------------

        interested = (
            db.query(InterestedFixture)
            .filter(
                InterestedFixture.user_id ==
                session.user_id,

                InterestedFixture.fixture_id ==
                fixture_id
            )
            .first()
        )

        if not interested:

            raise HTTPException(
                status_code=404,
                detail="Fixture is not marked as interested"
            )

        # -----------------------------------------------------
        # Remove Interested record
        # -----------------------------------------------------

        db.delete(interested)

        db.commit()

        return {
            "message": "Fixture removed from Interested",
            "fixture_id": fixture_id,
            "interested": False
        }

    except HTTPException:

        db.rollback()

        raise

    except Exception:

        db.rollback()

        raise

    finally:

        db.close()

@app.get("/interested")
def get_interested_fixtures(
    session_id: str | None = Cookie(
        default=None,
        alias="terrace_session"
    )
):

    db = SessionLocal()

    if not session_id:

        db.close()

        return []

    print(
        "GET INTERESTED SESSION:",
        session_id
    )

    session = (
        db.query(AnonymousSession)
        .filter(
            AnonymousSession.session_id ==
            session_id
        )
        .first()
    )

    print(
        "GET INTERESTED USER:",
        session.user_id
        if session
        else None
    )

    if not session:

        db.close()

        return []

    interested = (
        db.query(InterestedFixture)
        .filter(
            InterestedFixture.user_id ==
            session.user_id
        )
        .order_by(
            InterestedFixture.created_at.desc()
        )
        .all()
    )

    print(
        "GET INTERESTED RECORD COUNT:",
        len(interested)
    )

    results = []

    for item in interested:

        fixture = item.fixture

        if not fixture:
            continue

        results.append({

            "interested_id":
                item.interested_id,

            "fixture_id":
                fixture.fixture_id,

            "fixture_date":
                fixture.fixture_date,

            "home_team":
                fixture.home_team,

            "away_team":
                fixture.away_team,

            "venue_id":
                fixture.venue_id,

            "venue_name": (
                fixture.venue.name
                if fixture.venue
                else None
            ),

            "venue_city": (
                fixture.venue.city
                if fixture.venue
                else None
            ),

        })

    db.close()

    return results


@app.get(
    "/my-reviews",
    response_model=list[MyReviewResponse]
)
def get_my_reviews(
    session_id: str | None = Cookie(
        default=None,
        alias="terrace_session"
    )
):

    db = SessionLocal()

    try:

        if not session_id:

            raise HTTPException(
                status_code=401,
                detail="No active session"
            )

        session = (
            db.query(AnonymousSession)
            .filter(
                AnonymousSession.session_id ==
                session_id
            )
            .first()
        )

        if not session:

            raise HTTPException(
                status_code=401,
                detail="Invalid session"
            )

        reviews = (
            db.query(AwayDayReview)
            .filter(
                AwayDayReview.user_id ==
                session.user_id
            )
            .order_by(
                AwayDayReview.created_at.desc()
            )
            .all()
        )

        results = []

        for review in reviews:

            fixture = review.fixture

            venue = review.venue

            results.append({

                "review_id":
                    review.review_id,

                "venue_id":
                    venue.venue_id,

                "venue_name":
                    venue.name,

                "venue_city":
                    venue.city,

                "fixture_id": (
                    fixture.fixture_id
                    if fixture
                    else None
                ),

                "fixture_date": (
                    fixture.fixture_date
                    if fixture
                    else None
                ),

                "home_team": (
                    fixture.home_team
                    if fixture
                    else None
                ),

                "away_team": (
                    fixture.away_team
                    if fixture
                    else None
                ),

                "visit_date":
                    review.visit_date,

                "recommend":
                    review.recommend,

                "overall_score":
                    review.overall_score,

                "atmosphere_score":
                    review.atmosphere_score,

                "pubs_score":
                    review.pubs_score,

                "getting_there_score":
                    review.getting_there_score,

                "facilities_score":
                    review.facilities_score,

                "created_at":
                    review.created_at,

            })

        return results

    finally:

        db.close()