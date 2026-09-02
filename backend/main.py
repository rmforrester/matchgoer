from fastapi.middleware.cors import CORSMiddleware
from datetime import date, datetime, timedelta, timezone
import os
import logging
from math import cos, radians

from sqlalchemy import case, cast, Date, func, or_, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload
import re
from geopy.distance import geodesic
from database import SessionLocal
from identity import (
    ResolvedIdentity,
    current_or_new_anonymous_identity,
    optional_current_identity,
    required_current_identity,
    verify_claim_provider_identity,
    anonymous_cookie_options,
)
from account_claim import claim_anonymous_user, issue_account_conversion_handoff
from fixture_time import CANCELLED_STATUSES, FINISHED_STATUSES, fixture_datetime_utc, utc_date_expression
from location_safety import has_usable_coordinates
from club_venue_know import google_maps_search_url, guide_facts_for_relationship, publishable_spots, resolve_club_venue, resolve_unique_home_club
from decision import fixture_decision_leads, fixture_decision_payload

from models import (
    Fixture,
    Venue,
    VenueName,
    VenueGuideFact,
    ClubVenue,
    PreMatchSpot,
    MatchdayTip,
    AwayDayReview,
    VenueVisit,
    User,
    AnonymousSession,
    InterestedFixture,
    UserProfile,
    FixtureMeetingIntent,
    MatchBoardPost,
    MatchBoardReport,
    SocialEvent,
)

from schemas import (
    FixtureResponse,
    FixtureWithVenueResponse,
    VenueResponse,
    VenueGuideResponse,
    MatchdayTipCreate,
    AwayDayReviewCreate,
    AwayDayReviewUpdate,
    AwayDayReviewResponse,
    AwayDayScoreResponse,
    MyReviewResponse,
    VenueVisitCreate,
    VenueVisitResponse,
    MyGroundResponse,
    ProfileCreate,
    ProfileUpdate,
    AccountContextResponse,
    MatchBoardPostCreate,
    MatchBoardReportCreate,
    MeetingIntentUpdate,
    AccountClaimRequest,
    AccountClaimResponse,
    AccountConversionHandoffResponse,
)

from fastapi import Cookie, Depends, FastAPI, Header, Response, HTTPException, Query
from venue_guides import build_venue_guide


app = FastAPI(
    title="Matchgoer API"
)

logger = logging.getLogger(__name__)


configured_origins = [
    origin.strip().rstrip("/")
    for origin in os.getenv("TERRACE_ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",")
    if origin.strip()
]
production_mode = os.getenv("TERRACE_ENV", "development").strip().lower() == "production"

app.add_middleware(
    CORSMiddleware,
    allow_origins=configured_origins,
    allow_origin_regex=(
        r"^http://(192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+):3000$"
        if os.getenv("TERRACE_ALLOW_PRIVATE_NETWORK_ORIGINS", "false" if production_mode else "true").lower() in {"1", "true", "yes", "on"}
        else None
    ),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def home():
    return {
        "message": "Matchgoer API running"
    }


@app.get("/health")
def health():
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok"}
    except Exception:
        db.rollback()
        raise HTTPException(status_code=503, detail="Database unavailable")
    finally:
        db.close()


@app.get("/fixtures", response_model=list[FixtureWithVenueResponse])
def get_fixtures(date: str | None = None):

    db = SessionLocal()

    query = db.query(Fixture).options(
        joinedload(Fixture.venue)
    )

    if date:
        query = query.filter(
            utc_date_expression(Fixture.fixture_date) == date
        )

    fixtures = query.limit(500).all()

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
    limit: int = 100,
    north: float | None = None,
    south: float | None = None,
    east: float | None = None,
    west: float | None = None,
):
    db = SessionLocal()

    bounds = (north, south, east, west)
    if any(value is not None for value in bounds):
        if not all(value is not None for value in bounds):
            db.close()
            raise HTTPException(status_code=422, detail="north, south, east and west are required together")
        if south > north:
            db.close()
            raise HTTPException(status_code=422, detail="south must not exceed north")
        query = db.query(Venue).filter(
            Venue.latitude.is_not(None),
            Venue.longitude.is_not(None),
            Venue.latitude.between(south, north),
        )
        query = query.filter(
            Venue.longitude.between(west, east)
            if west <= east
            else or_(Venue.longitude >= west, Venue.longitude <= east)
        )
        venues = query.order_by(Venue.name, Venue.venue_id).limit(limit).all()
        db.close()
        return venues

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

        if not has_usable_coordinates(venue.latitude, venue.longitude):
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
    if venue is None:
        raise HTTPException(status_code=404, detail="Ground not found")
    return venue


@app.get("/venues/{venue_id}/guide", response_model=VenueGuideResponse)
def get_venue_guide(venue_id: int, team_id: int | None = None):
    db = SessionLocal()
    try:
        if not db.query(Venue.venue_id).filter(Venue.venue_id == venue_id).first():
            raise HTTPException(status_code=404, detail="Ground not found")
        relationships = db.query(ClubVenue).filter(ClubVenue.venue_id == venue_id)
        if team_id is not None:
            explicit_relationships = relationships.filter(ClubVenue.team_id == team_id).all()
            relationship = resolve_club_venue(team_id, venue_id, explicit_relationships)
        else:
            relationship = resolve_unique_home_club(venue_id, relationships.all())
        relationship_id = relationship.club_venue_id if relationship is not None else None
        fact_filter = VenueGuideFact.venue_id == venue_id
        if relationship_id is not None:
            fact_filter = or_(fact_filter, VenueGuideFact.club_venue_id == relationship_id)
        facts = guide_facts_for_relationship(
            venue_id,
            relationship,
            db.query(VenueGuideFact).filter(fact_filter).all(),
        )
        guide = build_venue_guide(venue_id, facts)
        spots = publishable_spots(
            relationship,
            db.query(PreMatchSpot).filter(PreMatchSpot.club_venue_id == relationship_id).all()
            if relationship_id is not None else [],
        )
        guide.update({
            "club_venue_id": relationship_id,
            "club_name": relationship.team.team_name if relationship is not None else None,
            "before_match": [{
                "pre_match_spot_id": spot.pre_match_spot_id,
                "display_name": spot.display_name,
                "classification": spot.classification,
                "audience": spot.audience,
                "supporting_line": spot.supporting_line,
                "directions_url": google_maps_search_url(spot.maps_destination),
            } for spot in spots],
        })
        return guide
    finally:
        db.close()


@app.get("/leagues")
def get_leagues():
    db = SessionLocal()

    leagues = (
        db.query(
            Fixture.country,
            Fixture.league_id,
            Fixture.league_name
        )
        .distinct()
        .order_by(Fixture.country, Fixture.league_id)
        .all()
    )

    db.close()

    grouped = {}
    for league in leagues:
        country = league.country or "Other"
        grouped.setdefault(country, []).append({
            "league_id": league.league_id,
            "league_name": league.league_name,
        })

    return [
        {"country": country, "leagues": grouped[country]}
        for country in sorted(grouped, key=str.casefold)
    ]


# =========================================================
# ANONYMOUS SESSION
# =========================================================


@app.get("/session")
def get_session(
    identity: ResolvedIdentity = Depends(current_or_new_anonymous_identity),
):
    return {
        "user_id": identity.user_id,
        "anonymous": not identity.is_registered,
    }


@app.post("/account/conversion-handoff", response_model=AccountConversionHandoffResponse)
def create_account_conversion_handoff(
    session_id: str | None = Cookie(default=None, alias="terrace_session"),
):
    db = SessionLocal()
    try:
        token, expires_at = issue_account_conversion_handoff(db, session_id=session_id)
        logger.info("account_conversion event=handoff_issued cookie_present=%s outcome=issued", bool(session_id))
        return {"handoff_token": token, "expires_at": expires_at}
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        logger.info(
            "account_conversion event=handoff_issue cookie_present=%s outcome=rejected error_code=%s",
            bool(session_id), detail.get("code", "UNKNOWN"),
        )
        raise
    finally:
        db.close()


@app.post("/account/claim", response_model=AccountClaimResponse)
def claim_account(
    response: Response,
    request: AccountClaimRequest | None = None,
    authorization: str | None = Header(default=None),
    session_id: str | None = Cookie(default=None, alias="terrace_session"),
):
    try:
        provider_identity = verify_claim_provider_identity(authorization)
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        logger.info(
            "account_conversion event=claim cookie_present=%s handoff_present=%s outcome=rejected continuity=unverified error_code=%s",
            bool(session_id), bool(request and request.handoff_token), detail.get("code", "UNKNOWN"),
        )
        raise
    db = SessionLocal()
    try:
        result = claim_anonymous_user(
            db,
            session_id=session_id,
            handoff_token=request.handoff_token if request else None,
            provider_identity=provider_identity,
        )
        logger.info(
            "account_conversion event=claim cookie_present=%s handoff_present=%s outcome=claimed user_id=%s continuity=preserved idempotent=%s",
            bool(session_id), bool(request and request.handoff_token), result.user_id, result.idempotent,
        )
        response.delete_cookie(
            key="terrace_session",
            **anonymous_cookie_options(),
        )
        return result
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        logger.info(
            "account_conversion event=claim cookie_present=%s handoff_present=%s outcome=rejected continuity=unverified error_code=%s",
            bool(session_id), bool(request and request.handoff_token), detail.get("code", "UNKNOWN"),
        )
        raise
    finally:
        db.close()


def _has_meaningful_activity(db, user_id: int) -> bool:
    ownership_checks = (
        db.query(InterestedFixture.interested_id).filter(InterestedFixture.user_id == user_id).first(),
        db.query(VenueVisit.visit_id).filter(VenueVisit.user_id == user_id).first(),
        db.query(AwayDayReview.review_id).filter(AwayDayReview.user_id == user_id).first(),
        db.query(UserProfile.user_id).filter(UserProfile.user_id == user_id).first(),
        db.query(FixtureMeetingIntent.user_id).filter(FixtureMeetingIntent.user_id == user_id).first(),
        db.query(MatchBoardPost.post_id).filter(MatchBoardPost.author_user_id == user_id).first(),
        db.query(MatchBoardReport.report_id).filter(MatchBoardReport.reporter_user_id == user_id).first(),
        db.query(MatchdayTip.tip_id).filter(MatchdayTip.author_user_id == user_id).first(),
    )
    return any(record is not None for record in ownership_checks)


@app.get("/account/context", response_model=AccountContextResponse)
def get_account_context(
    identity: ResolvedIdentity = Depends(required_current_identity),
    session_id: str | None = Cookie(default=None, alias="terrace_session"),
):
    if not identity.is_registered:
        raise HTTPException(status_code=403, detail={"code": "REGISTERED_ACCOUNT_REQUIRED", "message": "A registered account is required"})
    db = SessionLocal()
    try:
        profile = db.query(UserProfile).filter(UserProfile.user_id == identity.user_id).first()
        profile_complete = bool(profile and profile.username and profile.username.strip() and profile.display_name.strip())
        candidate_session = (
            db.query(AnonymousSession)
            .filter(AnonymousSession.session_id == session_id, AnonymousSession.revoked_at.is_(None))
            .first()
            if session_id
            else None
        )
        distinct_candidate = bool(candidate_session and candidate_session.user_id != identity.user_id)
        candidate_user = db.get(User, candidate_session.user_id) if distinct_candidate else None
        anonymous_session_present = bool(candidate_user and candidate_user.account_status == "anonymous")
        return {
            "registered": True,
            "profile_complete": profile_complete,
            "anonymous_session_present": anonymous_session_present,
            "anonymous_activity": bool(
                anonymous_session_present and _has_meaningful_activity(db, candidate_user.user_id)
            ),
        }
    finally:
        db.close()


@app.get("/nearby")
def get_nearby(
    response: Response,
    latitude: float,
    longitude: float,
    radius: float = 50,
    date: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    league_id: list[int] | None = Query(default=None),
    season: int | None = None,
    limit: int = Query(default=20, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    north: float | None = None,
    south: float | None = None,
    east: float | None = None,
    west: float | None = None,
):

    db = SessionLocal()

    query = db.query(Fixture)
    bounds = (north, south, east, west)
    viewport_mode = any(value is not None for value in bounds)
    if viewport_mode:
        if not all(value is not None for value in bounds):
            db.close()
            raise HTTPException(status_code=422, detail="north, south, east and west are required together")
        if south > north:
            db.close()
            raise HTTPException(status_code=422, detail="south must not exceed north")
        query = query.join(Venue, Fixture.venue_id == Venue.venue_id).filter(
            Venue.latitude.is_not(None),
            Venue.longitude.is_not(None),
            Venue.latitude.between(south, north),
        )
        query = query.filter(
            Venue.longitude.between(west, east)
            if west <= east
            else or_(Venue.longitude >= west, Venue.longitude <= east)
        )
    else:
        latitude_delta = radius / 69.0
        longitude_scale = max(abs(cos(radians(latitude))), 0.01)
        longitude_delta = radius / (69.0 * longitude_scale)
        query = query.join(Venue, Fixture.venue_id == Venue.venue_id).filter(
            Venue.latitude.between(latitude - latitude_delta, latitude + latitude_delta),
            Venue.longitude.between(longitude - longitude_delta, longitude + longitude_delta),
        )

    # Exact date

    if date:

        query = query.filter(
            Fixture.fixture_date >= datetime.fromisoformat(f"{date}T00:00:00+00:00"),
            Fixture.fixture_date < datetime.fromisoformat(f"{date}T00:00:00+00:00") + timedelta(days=1),
        )

    # Date range

    if start_date:

        query = query.filter(
            Fixture.fixture_date >= datetime.fromisoformat(f"{start_date}T00:00:00+00:00")
        )

    if end_date:

        query = query.filter(
            Fixture.fixture_date < datetime.fromisoformat(f"{end_date}T00:00:00+00:00") + timedelta(days=1)
        )

    # League

    if league_id:

        query = query.filter(
            Fixture.league_id.in_(league_id)
        )

    # Season

    if season:

        query = query.filter(
            Fixture.season == season
        )

    fixtures = query.options(joinedload(Fixture.venue)).all()

    results = []

    user_location = (
        latitude,
        longitude
    )

    for fixture in fixtures:

        if not fixture.venue:
            continue

        if not has_usable_coordinates(fixture.venue.latitude, fixture.venue.longitude):
            continue

        venue_location = (
            fixture.venue.latitude,
            fixture.venue.longitude
        )

        distance = geodesic(
            user_location,
            venue_location
        ).miles

        if viewport_mode or distance <= radius:

            results.append({

                "fixture_id":
                    fixture.fixture_id,

                "fixture_date":
                    fixture_datetime_utc(fixture.fixture_date),

                "home_team":
                    fixture.home_team,

                "away_team":
                    fixture.away_team,

                "league_id":
                    fixture.league_id,

                "league_name":
                    fixture.league_name,

                "status":
                    fixture.status,

                "home_goals":
                    fixture.home_goals,

                "away_goals":
                    fixture.away_goals,

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

    venue_ids = {
        result["venue_id"]
        for result in results
    }

    ratings = {}

    if venue_ids:
        ratings = {
            venue_id: {
                "away_day_score": (
                    round(float(score), 1)
                    if score is not None
                    else None
                ),
                "atmosphere_score": (
                    round(float(atmosphere_score), 1)
                    if atmosphere_score is not None
                    else None
                ),
                "review_count": review_count,
                "recommend_percentage": (
                    round((float(recommend_count) / recommend_total) * 100, 1)
                    if recommend_total
                    else None
                ),
            }
            for venue_id, score, atmosphere_score, review_count, recommend_count, recommend_total in (
                db.query(
                    AwayDayReview.venue_id,
                    func.avg(AwayDayReview.overall_score),
                    func.avg(AwayDayReview.atmosphere_score),
                    func.count(AwayDayReview.review_id),
                    func.sum(case((AwayDayReview.recommend.is_(True), 1), else_=0)),
                    func.count(AwayDayReview.recommend),
                )
                .filter(AwayDayReview.venue_id.in_(venue_ids))
                .group_by(AwayDayReview.venue_id)
                .all()
            )
        }

    for result in results:
        rating = ratings.get(result["venue_id"], {})
        result["away_day_score"] = rating.get("away_day_score")
        result["atmosphere_score"] = rating.get("atmosphere_score")
        result["review_count"] = rating.get("review_count", 0)
        result["recommend_percentage"] = rating.get("recommend_percentage")

    fixture_by_id = {fixture.fixture_id: fixture for fixture in fixtures}
    decision_leads = fixture_decision_leads(
        db,
        [fixture_by_id[result["fixture_id"]] for result in results],
    )
    for result in results:
        result.update(decision_leads.get(result["fixture_id"], {
            "highlight_eligible": False,
            "lead_decision_reason": None,
        }))

    meeting_counts = dict(
        db.query(
            FixtureMeetingIntent.fixture_id,
            func.count(FixtureMeetingIntent.user_id),
        )
        .filter(FixtureMeetingIntent.fixture_id.in_([result["fixture_id"] for result in results]))
        .group_by(FixtureMeetingIntent.fixture_id)
        .all()
    ) if results else {}

    for result in results:
        result["open_to_meet_count"] = meeting_counts.get(result["fixture_id"], 0)

    db.close()

    # Distance is presentation data and must not decide which qualifying
    # fixtures survive the discovery result cap.

    results.sort(
        key=lambda fixture: (
            fixture["fixture_date"],
            fixture["fixture_id"],
        )
    )

    total_matches = len(results)
    response.headers["X-Total-Matches"] = str(total_matches)
    response.headers["X-Results-Limited"] = "true" if offset + limit < total_matches else "false"

    return results[
        offset:
        offset + limit
    ]


# =========================================================
# MATCHDAY TIPS
# =========================================================


@app.post("/tips")
def create_tip(
    data: MatchdayTipCreate,
    identity: ResolvedIdentity | None = Depends(optional_current_identity),
):

    db = SessionLocal()

    tip = MatchdayTip(
        venue_id=data.venue_id,
        tip=data.tip,
        author_user_id=identity.user_id if identity else None,
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
        raise HTTPException(status_code=404, detail="Tip not found")

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
        raise HTTPException(status_code=404, detail="Tip not found")

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
            .outerjoin(VenueName, VenueName.venue_id == Venue.venue_id)
            .filter(
                or_(
                    func.lower(Venue.name).like(search_term),
                    func.lower(Venue.city).like(search_term),
                    func.lower(VenueName.name).like(search_term),
                )
            )
            .distinct()
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


def _review_state(review: AwayDayReview | None) -> str:
    if review is None:
        return "none"
    values = (
        review.recommend,
        review.overall_score,
        review.atmosphere_score,
        review.pubs_score,
        review.getting_there_score,
        review.facilities_score,
    )
    if all(value is None for value in values):
        return "blank"
    if all(value is not None for value in values):
        return "completed"
    return "partial"


def _ensure_venue_visit(
    db,
    *,
    user_id: int,
    venue_id: int,
    fixture_id: int | None,
    visit_date,
    source: str,
) -> VenueVisit:
    normalized_date = visit_date.date() if isinstance(visit_date, datetime) else visit_date
    db.execute(
        pg_insert(VenueVisit)
        .values(
            user_id=user_id,
            venue_id=venue_id,
            fixture_id=fixture_id,
            visit_date=normalized_date,
            source=source,
        )
        .on_conflict_do_nothing()
    )
    query = db.query(VenueVisit).filter(VenueVisit.user_id == user_id)
    if fixture_id is not None:
        query = query.filter(VenueVisit.fixture_id == fixture_id)
    elif normalized_date is not None:
        query = query.filter(
            VenueVisit.venue_id == venue_id,
            VenueVisit.fixture_id.is_(None),
            VenueVisit.visit_date == normalized_date,
        )
    else:
        query = query.filter(
            VenueVisit.venue_id == venue_id,
            VenueVisit.fixture_id.is_(None),
            VenueVisit.visit_date.is_(None),
        )
    visit = query.first()
    if visit is None:
        raise RuntimeError("Venue visit could not be created or resolved")
    if visit.venue_id != venue_id:
        raise HTTPException(status_code=409, detail="Attendance already exists for a different venue")
    return visit


@app.post(
    "/venues/{venue_id}/away-day-reviews",
    response_model=AwayDayReviewResponse
)
def create_away_day_review(
    venue_id: int,
    data: AwayDayReviewCreate,
    identity: ResolvedIdentity = Depends(required_current_identity),
):

    db = SessionLocal()

    try:

        # -----------------------------------------------------
        # Check anonymous session
        # -----------------------------------------------------

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
                identity.user_id,

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

        fixture = None
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
        # Transitional compatibility: ensure attendance/history
        # before creating the legacy My Grounds/review row.
        # -----------------------------------------------------

        existing_venue_visit = db.query(VenueVisit.visit_id).filter(
            VenueVisit.user_id == identity.user_id,
            VenueVisit.venue_id == venue_id,
        ).first()
        if data.fixture_id is not None or existing_venue_visit is None:
            _ensure_venue_visit(
                db,
                user_id=identity.user_id,
                venue_id=venue_id,
                fixture_id=data.fixture_id,
                visit_date=(data.visit_date or fixture_datetime_utc(fixture.fixture_date).date()) if fixture else data.visit_date,
                source="fixture_confirmation" if fixture else "manual",
            )

        # -----------------------------------------------------
        # Create stadium record
        # -----------------------------------------------------

        review = AwayDayReview(
            user_id=identity.user_id,
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
    identity: ResolvedIdentity = Depends(required_current_identity),
):

    db = SessionLocal()

    try:

        # -------------------------------------------------
        # Check anonymous session
        # -------------------------------------------------

        # -------------------------------------------------
        # Find the user's existing stadium visit
        # -------------------------------------------------

        review = (
            db.query(AwayDayReview)
            .filter(
                AwayDayReview.user_id ==
                identity.user_id,

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
    search: str | None = None,
    around_date: str | None = None,
    days: int = Query(default=3, ge=0, le=31),
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

        target_date = None
        if around_date:
            try:
                target_date = date.fromisoformat(around_date)
            except ValueError:
                raise HTTPException(status_code=422, detail="around_date must be YYYY-MM-DD")
            query = query.filter(
                utc_date_expression(Fixture.fixture_date) >= target_date - timedelta(days=days),
                utc_date_expression(Fixture.fixture_date) <= target_date + timedelta(days=days),
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

        if target_date is not None:
            def historical_fixture_rank(fixture):
                day_difference = abs((fixture_datetime_utc(fixture.fixture_date).date() - target_date).days)
                priority = 0 if day_difference == 0 else 1 if day_difference == 1 else 2 if day_difference <= 3 else 3
                return priority, fixture.fixture_date, fixture.fixture_id

            fixtures.sort(key=historical_fixture_rank)

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
                        fixture_datetime_utc(fixture.fixture_date),

                    "home_team":
                        fixture.home_team,

                    "away_team":
                        fixture.away_team,

                    "league_name":
                        fixture.league_name,

                    "status":
                        fixture.status,

                    "home_goals":
                        fixture.home_goals,

                    "away_goals":
                        fixture.away_goals,

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
    identity: ResolvedIdentity = Depends(current_or_new_anonymous_identity),
):

    db = SessionLocal()

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
            identity.user_id,

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
        user_id=identity.user_id,
        fixture_id=fixture_id,
    )

    db.add(interested)

    db.add(SocialEvent(
        user_id=identity.user_id,
        fixture_id=fixture_id,
        event_type="interested_added",
    ))

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
    identity: ResolvedIdentity = Depends(required_current_identity),
):

    db = SessionLocal()

    try:

        # -----------------------------------------------------
        # Check anonymous session
        # -----------------------------------------------------

        # -----------------------------------------------------
        # Find user's interested fixture
        # -----------------------------------------------------

        interested = (
            db.query(InterestedFixture)
            .filter(
                InterestedFixture.user_id ==
                identity.user_id,

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

        meeting_intent = (
            db.query(FixtureMeetingIntent)
            .filter(
                FixtureMeetingIntent.user_id == identity.user_id,
                FixtureMeetingIntent.fixture_id == fixture_id,
            )
            .first()
        )

        if meeting_intent:
            db.delete(meeting_intent)
            db.add(SocialEvent(
                user_id=identity.user_id,
                fixture_id=fixture_id,
                event_type="meeting_disabled",
            ))

        db.delete(interested)
        db.add(SocialEvent(
            user_id=identity.user_id,
            fixture_id=fixture_id,
            event_type="interested_removed",
        ))

        db.commit()

        return {
            "message": "Fixture removed from Interested",
            "fixture_id": fixture_id,
            "interested": False,
            "open_to_meet": False,
            "open_to_meet_count": db.query(func.count(FixtureMeetingIntent.user_id)).filter(FixtureMeetingIntent.fixture_id == fixture_id).scalar(),
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
    identity: ResolvedIdentity | None = Depends(optional_current_identity),
):

    db = SessionLocal()

    if identity is None:

        db.close()

        return []

    interested = (
        db.query(InterestedFixture)
        .filter(
            InterestedFixture.user_id ==
            identity.user_id
        )
        .order_by(
            InterestedFixture.created_at.desc()
        )
        .all()
    )

    fixture_ids = [item.fixture_id for item in interested]
    meeting_counts = dict(
        db.query(FixtureMeetingIntent.fixture_id, func.count(FixtureMeetingIntent.user_id))
        .filter(FixtureMeetingIntent.fixture_id.in_(fixture_ids))
        .group_by(FixtureMeetingIntent.fixture_id)
        .all()
    ) if fixture_ids else {}
    own_meeting_ids = {
        fixture_id for fixture_id, in db.query(FixtureMeetingIntent.fixture_id)
        .filter(
            FixtureMeetingIntent.user_id == identity.user_id,
            FixtureMeetingIntent.fixture_id.in_(fixture_ids),
        ).all()
    } if fixture_ids else set()

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
                fixture_datetime_utc(fixture.fixture_date),

            "home_team":
                fixture.home_team,

            "away_team":
                fixture.away_team,

            "status":
                fixture.status,

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

            "open_to_meet_count": meeting_counts.get(fixture.fixture_id, 0),
            "open_to_meet": fixture.fixture_id in own_meeting_ids,

        })

    db.close()

    return results


@app.get(
    "/my-reviews",
    response_model=list[MyReviewResponse]
)
def get_my_reviews(
    identity: ResolvedIdentity = Depends(required_current_identity),
):

    db = SessionLocal()

    try:

        reviews = (
            db.query(AwayDayReview)
            .filter(
                AwayDayReview.user_id ==
                identity.user_id
            )
            .order_by(
                AwayDayReview.created_at.desc()
            )
            .all()
        )

        venue_ids = {review.venue_id for review in reviews}
        venue_aggregates = {}

        if venue_ids:
            venue_aggregates = {
                venue_id: (
                    round((float(recommend_count) / recommend_total) * 100, 1)
                    if recommend_total
                    else None
                )
                for venue_id, recommend_count, recommend_total in (
                    db.query(
                        AwayDayReview.venue_id,
                        func.sum(case((AwayDayReview.recommend.is_(True), 1), else_=0)),
                        func.count(AwayDayReview.recommend),
                    )
                    .filter(AwayDayReview.venue_id.in_(venue_ids))
                    .group_by(AwayDayReview.venue_id)
                    .all()
                )
            }

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
                    fixture_datetime_utc(fixture.fixture_date)
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

                "recommend_percentage":
                    venue_aggregates.get(review.venue_id),

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


# =========================================================
# SOCIAL MVP V1
# =========================================================

REPORT_REASONS = {"harassment", "spam", "unsafe_meetup", "offensive", "other"}
POST_COOLDOWN_SECONDS = 15


def _require_profile(db, user_id: int):
    profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    if not profile:
        raise HTTPException(status_code=403, detail="Create a profile first")
    return profile


def _require_registered_social(identity: ResolvedIdentity):
    if not identity.is_registered or identity.account_status != "registered":
        raise HTTPException(
            status_code=403,
            detail={
                "code": "REGISTERED_ACCOUNT_REQUIRED",
                "message": "Create a Matchgoer account to join in",
            },
        )


def _require_social_profile(db, user_id: int):
    profile = _require_profile(db, user_id)
    if not profile.username or not profile.username.strip():
        raise HTTPException(
            status_code=403,
            detail={
                "code": "PROFILE_REQUIRED",
                "message": "Complete your Matchgoer profile before joining in",
            },
        )
    return profile


def _board_closed(fixture: Fixture):
    if fixture.status in FINISHED_STATUSES | CANCELLED_STATUSES:
        return True
    kickoff = fixture_datetime_utc(fixture.fixture_date)
    return datetime.now(timezone.utc).date() > kickoff.astimezone(timezone.utc).date()


def _post_payload(post, profile, current_user_id, current_user_registered):
    return {
        "post_id": post.post_id,
        "fixture_id": post.fixture_id,
        "parent_post_id": post.parent_post_id,
        "author": {
            "user_id": post.author_user_id,
            "username": profile.username,
            "display_name": profile.display_name,
            "supported_club": profile.supported_club,
        },
        "body": "Post deleted" if post.deleted_at else post.body,
        "deleted": post.deleted_at is not None,
        "can_delete": current_user_registered and post.author_user_id == current_user_id and post.deleted_at is None,
        "can_report": current_user_registered and post.author_user_id != current_user_id and post.deleted_at is None,
        "created_at": post.created_at,
        "updated_at": post.updated_at,
    }


@app.post("/fixtures/{fixture_id}/attendance", response_model=VenueVisitResponse)
def record_fixture_attendance(
    fixture_id: int,
    identity: ResolvedIdentity = Depends(required_current_identity),
):
    db = SessionLocal()
    try:
        user_id = identity.user_id
        fixture = db.query(Fixture).filter(Fixture.fixture_id == fixture_id).first()
        if not fixture:
            raise HTTPException(status_code=404, detail="Fixture not found")
        if fixture.venue_id is None:
            raise HTTPException(status_code=409, detail="Fixture is not linked to a canonical venue")
        visit = _ensure_venue_visit(
            db,
            user_id=user_id,
            venue_id=fixture.venue_id,
            fixture_id=fixture.fixture_id,
            visit_date=fixture_datetime_utc(fixture.fixture_date).date(),
            source="fixture_confirmation",
        )
        db.commit()
        db.refresh(visit)
        return visit
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@app.delete("/fixtures/{fixture_id}/attendance")
def remove_fixture_attendance(
    fixture_id: int,
    identity: ResolvedIdentity = Depends(required_current_identity),
):
    db = SessionLocal()
    try:
        user_id = identity.user_id
        visit = db.query(VenueVisit).filter(
            VenueVisit.user_id == user_id,
            VenueVisit.fixture_id == fixture_id,
        ).first()
        if visit is None:
            return {"fixture_id": fixture_id, "attended": False, "removed": False}
        visit_id = visit.visit_id
        venue_id = visit.venue_id
        db.delete(visit)
        db.commit()
        return {
            "fixture_id": fixture_id,
            "venue_id": venue_id,
            "visit_id": visit_id,
            "attended": False,
            "removed": True,
        }
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@app.post("/venues/{venue_id}/visits", response_model=VenueVisitResponse)
def record_manual_venue_visit(
    venue_id: int,
    data: VenueVisitCreate,
    identity: ResolvedIdentity = Depends(required_current_identity),
):
    db = SessionLocal()
    try:
        user_id = identity.user_id
        venue = db.query(Venue).filter(Venue.venue_id == venue_id).first()
        if not venue:
            raise HTTPException(status_code=404, detail="Venue not found")
        fixture = None
        if data.fixture_id is not None:
            fixture = db.query(Fixture).filter(Fixture.fixture_id == data.fixture_id).first()
            if not fixture:
                raise HTTPException(status_code=404, detail="Fixture not found")
            if fixture.venue_id != venue_id:
                raise HTTPException(status_code=400, detail="Fixture was not played at this venue")
        visit = _ensure_venue_visit(
            db,
            user_id=user_id,
            venue_id=venue_id,
            fixture_id=data.fixture_id,
            visit_date=(data.visit_date or fixture_datetime_utc(fixture.fixture_date).date()) if fixture else data.visit_date,
            source="fixture_confirmation" if fixture else "manual",
        )
        db.commit()
        db.refresh(visit)
        return visit
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@app.get("/my-grounds", response_model=list[MyGroundResponse])
def get_my_grounds(
    identity: ResolvedIdentity = Depends(required_current_identity),
):
    db = SessionLocal()
    try:
        user_id = identity.user_id
        visits = db.query(VenueVisit).options(
            joinedload(VenueVisit.venue),
            joinedload(VenueVisit.fixture),
        ).filter(VenueVisit.user_id == user_id).order_by(
            VenueVisit.visit_date,
            VenueVisit.created_at,
            VenueVisit.visit_id,
        ).all()
        if not visits:
            return []
        venue_ids = {visit.venue_id for visit in visits}
        reviews = {
            review.venue_id: review
            for review in db.query(AwayDayReview).filter(
                AwayDayReview.user_id == user_id,
                AwayDayReview.venue_id.in_(venue_ids),
            ).all()
        }
        community = {
            venue_id: (average, review_count, recommend_count, recommend_total)
            for venue_id, average, review_count, recommend_count, recommend_total in db.query(
                AwayDayReview.venue_id,
                func.avg(AwayDayReview.overall_score),
                func.count(AwayDayReview.review_id),
                func.sum(case((AwayDayReview.recommend.is_(True), 1), else_=0)),
                func.count(AwayDayReview.recommend),
            ).filter(AwayDayReview.venue_id.in_(venue_ids)).group_by(AwayDayReview.venue_id).all()
        }
        grouped = {}
        for visit in visits:
            grouped.setdefault(visit.venue_id, []).append(visit)
        results = []
        for venue_id, venue_visits in grouped.items():
            venue = venue_visits[0].venue
            dated = [visit.visit_date for visit in venue_visits if visit.visit_date is not None]
            review = reviews.get(venue_id)
            state = _review_state(review)
            average, review_count, recommend_count, recommend_total = community.get(
                venue_id, (None, 0, 0, 0)
            )
            results.append({
                "venue_id": venue_id,
                "venue_name": venue.name,
                "venue_city": venue.city,
                "venue_country": venue.country,
                "capacity": venue.capacity,
                "latitude": venue.latitude,
                "longitude": venue.longitude,
                "visit_count": len(venue_visits),
                "first_visit_date": min(dated) if dated else None,
                "latest_visit_date": max(dated) if dated else None,
                "has_undated_visit": any(visit.visit_date is None for visit in venue_visits),
                "attended_fixtures": [
                    {
                        "fixture_id": visit.fixture.fixture_id,
                        "fixture_date": fixture_datetime_utc(visit.fixture.fixture_date),
                        "home_team": visit.fixture.home_team,
                        "away_team": visit.fixture.away_team,
                    }
                    for visit in venue_visits if visit.fixture is not None
                ],
                "review": ({
                    "review_id": review.review_id,
                    "state": state,
                    "completed": state == "completed",
                    "overall_score": review.overall_score,
                    "recommend": review.recommend,
                    "atmosphere_score": review.atmosphere_score,
                    "pubs_score": review.pubs_score,
                    "getting_there_score": review.getting_there_score,
                    "facilities_score": review.facilities_score,
                } if review else None),
                "community_terrace_rating": round(float(average), 1) if average is not None else None,
                "community_review_count": int(review_count or 0),
                "community_recommend_percentage": (
                    round((float(recommend_count) / recommend_total) * 100, 1)
                    if recommend_total else None
                ),
            })
        return sorted(results, key=lambda item: (item["venue_name"] or "").casefold())
    finally:
        db.close()


@app.get("/profile")
def get_profile(identity: ResolvedIdentity | None = Depends(optional_current_identity)):
    db = SessionLocal()
    try:
        user_id = identity.user_id if identity else None
        if user_id is None:
            return None
        profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
        if not profile:
            return None
        visited_count = db.query(func.count(func.distinct(VenueVisit.venue_id))).filter(VenueVisit.user_id == user_id).scalar()
        return {
            "user_id": user_id,
            "display_name": profile.display_name,
            "username": profile.username,
            "supported_club": profile.supported_club,
            "broad_location": profile.broad_location,
            "bio": profile.bio,
            "profile_complete": bool(profile.username and profile.username.strip() and profile.display_name.strip()),
            "grounds_visited": visited_count,
            "created_at": profile.created_at,
        }
    finally:
        db.close()


@app.post("/profile", status_code=201)
def create_profile(data: ProfileCreate, identity: ResolvedIdentity = Depends(required_current_identity)):
    db = SessionLocal()
    try:
        user_id = identity.user_id
        if db.query(UserProfile).filter(UserProfile.user_id == user_id).first():
            raise HTTPException(status_code=409, detail="Profile already exists")
        name = data.display_name.strip()
        club = data.supported_club.strip() if data.supported_club else None
        if not 2 <= len(name) <= 40:
            raise HTTPException(status_code=422, detail="Display name must be 2 to 40 characters")
        profile = UserProfile(user_id=user_id, display_name=name, supported_club=club or None)
        db.add(profile)
        db.commit()
        db.refresh(profile)
        return {"user_id": user_id, "display_name": profile.display_name, "supported_club": profile.supported_club, "created_at": profile.created_at}
    except HTTPException:
        db.rollback()
        raise
    finally:
        db.close()


@app.patch("/profile")
def update_registered_profile(
    data: ProfileUpdate,
    identity: ResolvedIdentity = Depends(required_current_identity),
):
    if not identity.is_registered:
        raise HTTPException(
            status_code=403,
            detail={"code": "REGISTERED_ACCOUNT_REQUIRED", "message": "Create an account before choosing a username"},
        )
    username = data.username.strip()
    display_name = data.display_name.strip()
    if not re.fullmatch(r"[A-Za-z0-9_]{3,30}", username):
        raise HTTPException(
            status_code=422,
            detail={"code": "INVALID_USERNAME", "message": "Use 3 to 30 letters, numbers or underscores"},
        )
    if not 2 <= len(display_name) <= 40:
        raise HTTPException(status_code=422, detail={"code": "INVALID_DISPLAY_NAME", "message": "Display name must be 2 to 40 characters"})

    optional_values = {
        "supported_club": data.supported_club.strip() if data.supported_club else None,
        "broad_location": data.broad_location.strip() if data.broad_location else None,
        "bio": data.bio.strip() if data.bio else None,
    }
    db = SessionLocal()
    try:
        profile = db.query(UserProfile).filter(UserProfile.user_id == identity.user_id).first()
        if profile is None:
            profile = UserProfile(user_id=identity.user_id, display_name=display_name)
            db.add(profile)
        profile.username = username
        profile.display_name = display_name
        profile.supported_club = optional_values["supported_club"] or None
        profile.broad_location = optional_values["broad_location"] or None
        profile.bio = optional_values["bio"] or None
        db.commit()
        db.refresh(profile)
        return {
            "user_id": identity.user_id,
            "username": profile.username,
            "display_name": profile.display_name,
            "supported_club": profile.supported_club,
            "broad_location": profile.broad_location,
            "bio": profile.bio,
            "profile_complete": True,
            "created_at": profile.created_at,
        }
    except IntegrityError as exc:
        db.rollback()
        if "uq_user_profiles_username_ci" in str(exc.orig):
            raise HTTPException(
                status_code=409,
                detail={"code": "USERNAME_UNAVAILABLE", "message": "That username is unavailable"},
            ) from exc
        raise
    finally:
        db.close()


@app.get("/fixtures/{fixture_id}/social")
def get_fixture_social(fixture_id: int, identity: ResolvedIdentity | None = Depends(optional_current_identity)):
    db = SessionLocal()
    try:
        fixture = db.query(Fixture).options(joinedload(Fixture.venue)).filter(Fixture.fixture_id == fixture_id).first()
        if not fixture:
            raise HTTPException(status_code=404, detail="Fixture not found")
        user_id = identity.user_id if identity else None
        profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first() if user_id else None
        own_review = (
            db.query(AwayDayReview)
            .filter(AwayDayReview.user_id == user_id, AwayDayReview.venue_id == fixture.venue_id)
            .first()
            if user_id and fixture.venue_id
            else None
        )
        own_attendance = (
            db.query(VenueVisit)
            .filter(VenueVisit.user_id == user_id, VenueVisit.fixture_id == fixture_id)
            .first()
            if user_id
            else None
        )
        interested = bool(user_id and db.query(InterestedFixture).filter(InterestedFixture.user_id == user_id, InterestedFixture.fixture_id == fixture_id).first())
        open_to_meet = bool(user_id and db.query(FixtureMeetingIntent).filter(FixtureMeetingIntent.user_id == user_id, FixtureMeetingIntent.fixture_id == fixture_id).first())
        open_count = db.query(func.count(FixtureMeetingIntent.user_id)).filter(FixtureMeetingIntent.fixture_id == fixture_id).scalar()
        rating = db.query(
            func.avg(AwayDayReview.overall_score),
            func.sum(case((AwayDayReview.recommend.is_(True), 1), else_=0)),
            func.count(AwayDayReview.recommend),
        ).filter(AwayDayReview.venue_id == fixture.venue_id).one()
        posts = db.query(MatchBoardPost).filter(MatchBoardPost.fixture_id == fixture_id).order_by(MatchBoardPost.created_at, MatchBoardPost.post_id).all()
        author_ids = {post.author_user_id for post in posts}
        profiles = {item.user_id: item for item in db.query(UserProfile).filter(UserProfile.user_id.in_(author_ids)).all()} if author_ids else {}
        roots = []
        replies = {}
        for post in posts:
            payload = _post_payload(post, profiles[post.author_user_id], user_id, bool(identity and identity.is_registered))
            if post.parent_post_id is None:
                roots.append(payload)
            else:
                replies.setdefault(post.parent_post_id, []).append(payload)
        for root in roots:
            root["replies"] = replies.get(root["post_id"], [])
        recommend_percentage = round((float(rating[1]) / rating[2]) * 100, 1) if rating[2] else None
        decision = fixture_decision_payload(db, fixture)
        db.add(SocialEvent(user_id=user_id, fixture_id=fixture_id, event_type="fixture_view"))
        db.add(SocialEvent(user_id=user_id, fixture_id=fixture_id, event_type="board_view"))
        db.commit()
        return {
            "fixture": {
                "fixture_id": fixture.fixture_id, "fixture_date": fixture_datetime_utc(fixture.fixture_date),
                "home_team": fixture.home_team, "home_team_id": fixture.home_team_id,
                "away_team": fixture.away_team,
                "status": fixture.status, "home_goals": fixture.home_goals,
                "away_goals": fixture.away_goals,
                "league_name": fixture.league_name, "venue_id": fixture.venue_id,
                "venue_name": fixture.venue.name if fixture.venue else fixture.venue_name,
                "venue_city": fixture.venue.city if fixture.venue else fixture.venue_city,
            },
            "terrace_rating": round(float(rating[0]), 1) if rating[0] is not None else None,
            "recommend_percentage": recommend_percentage,
            **decision,
            "interested": interested, "open_to_meet": open_to_meet,
            "open_to_meet_count": open_count, "profile": ({"username": profile.username, "display_name": profile.display_name, "supported_club": profile.supported_club} if profile else None),
            "own_review": ({
                "review_id": own_review.review_id,
                "fixture_id": own_review.fixture_id,
                "state": _review_state(own_review),
                "completed": _review_state(own_review) == "completed",
            } if own_review else None),
            "own_attendance": ({
                "attended": True,
                "visit_id": own_attendance.visit_id,
                "venue_id": own_attendance.venue_id,
                "visit_date": own_attendance.visit_date,
            } if own_attendance else {"attended": False, "visit_id": None}),
            "board_closed": _board_closed(fixture), "posts": roots,
        }
    finally:
        db.close()


@app.put("/fixtures/{fixture_id}/open-to-meet")
def update_meeting_intent(fixture_id: int, data: MeetingIntentUpdate, identity: ResolvedIdentity = Depends(required_current_identity)):
    _require_registered_social(identity)
    db = SessionLocal()
    try:
        user_id = identity.user_id
        user = db.query(User).filter(User.user_id == user_id).with_for_update().first()
        if not user:
            raise HTTPException(status_code=401, detail="Invalid session")
        _require_social_profile(db, user_id)
        interest = db.query(InterestedFixture).filter(InterestedFixture.user_id == user_id, InterestedFixture.fixture_id == fixture_id).first()
        if data.open_to_meet and not interest:
            fixture_exists = db.query(Fixture.fixture_id).filter(Fixture.fixture_id == fixture_id).first()
            if not fixture_exists:
                raise HTTPException(status_code=404, detail="Fixture not found")
            db.add(InterestedFixture(user_id=user_id, fixture_id=fixture_id))
            db.add(SocialEvent(user_id=user_id, fixture_id=fixture_id, event_type="interested_added"))
            db.flush()
        intent = db.query(FixtureMeetingIntent).filter(FixtureMeetingIntent.user_id == user_id, FixtureMeetingIntent.fixture_id == fixture_id).first()
        changed = False
        if data.open_to_meet and not intent:
            db.add(FixtureMeetingIntent(user_id=user_id, fixture_id=fixture_id))
            changed = True
        elif not data.open_to_meet and intent:
            db.delete(intent)
            changed = True
        if changed:
            db.add(SocialEvent(user_id=user_id, fixture_id=fixture_id, event_type="meeting_enabled" if data.open_to_meet else "meeting_disabled"))
        db.commit()
        count = db.query(func.count(FixtureMeetingIntent.user_id)).filter(FixtureMeetingIntent.fixture_id == fixture_id).scalar()
        interested = db.query(InterestedFixture).filter(InterestedFixture.user_id == user_id, InterestedFixture.fixture_id == fixture_id).first() is not None
        open_to_meet = db.query(FixtureMeetingIntent).filter(FixtureMeetingIntent.user_id == user_id, FixtureMeetingIntent.fixture_id == fixture_id).first() is not None
        return {"fixture_id": fixture_id, "interested": interested, "open_to_meet": open_to_meet, "open_to_meet_count": count}
    except HTTPException:
        db.rollback()
        raise
    finally:
        db.close()


@app.post("/fixtures/{fixture_id}/board/posts", status_code=201)
def create_board_post(fixture_id: int, data: MatchBoardPostCreate, identity: ResolvedIdentity = Depends(required_current_identity)):
    _require_registered_social(identity)
    db = SessionLocal()
    try:
        user_id = identity.user_id
        _require_social_profile(db, user_id)
        fixture = db.query(Fixture).filter(Fixture.fixture_id == fixture_id).first()
        if not fixture:
            raise HTTPException(status_code=404, detail="Fixture not found")
        if _board_closed(fixture):
            raise HTTPException(status_code=409, detail="This Match Board is now closed")
        body = data.body.strip()
        if not body or len(body) > 500:
            raise HTTPException(status_code=422, detail="Post must be 1 to 500 characters")
        recent = db.query(MatchBoardPost).filter(
            MatchBoardPost.author_user_id == user_id,
            MatchBoardPost.created_at > func.now() - text(f"INTERVAL '{POST_COOLDOWN_SECONDS} seconds'"),
        ).first()
        if recent:
            raise HTTPException(status_code=429, detail=f"Wait {POST_COOLDOWN_SECONDS} seconds before posting again")
        parent = None
        if data.parent_post_id is not None:
            parent = db.query(MatchBoardPost).filter(MatchBoardPost.post_id == data.parent_post_id).first()
            if not parent or parent.fixture_id != fixture_id:
                raise HTTPException(status_code=400, detail="Reply must belong to this fixture")
            if parent.parent_post_id is not None:
                raise HTTPException(status_code=400, detail="Replies cannot be nested")
        post = MatchBoardPost(fixture_id=fixture_id, author_user_id=user_id, parent_post_id=parent.post_id if parent else None, body=body)
        db.add(post)
        db.commit()
        db.refresh(post)
        return {"post_id": post.post_id, "fixture_id": fixture_id, "parent_post_id": post.parent_post_id, "body": post.body, "created_at": post.created_at}
    except HTTPException:
        db.rollback()
        raise
    finally:
        db.close()


@app.delete("/board/posts/{post_id}")
def delete_board_post(post_id: int, identity: ResolvedIdentity = Depends(required_current_identity)):
    _require_registered_social(identity)
    db = SessionLocal()
    try:
        user_id = identity.user_id
        post = db.query(MatchBoardPost).filter(MatchBoardPost.post_id == post_id).first()
        if not post:
            raise HTTPException(status_code=404, detail="Post not found")
        if post.author_user_id != user_id:
            raise HTTPException(status_code=403, detail="You can only delete your own content")
        if post.deleted_at is None:
            post.deleted_at = datetime.now(timezone.utc)
            db.commit()
        return {"post_id": post_id, "deleted": True}
    except HTTPException:
        db.rollback()
        raise
    finally:
        db.close()


@app.post("/board/posts/{post_id}/reports", status_code=201)
def report_board_post(post_id: int, data: MatchBoardReportCreate, identity: ResolvedIdentity = Depends(required_current_identity)):
    _require_registered_social(identity)
    db = SessionLocal()
    try:
        user_id = identity.user_id
        _require_social_profile(db, user_id)
        if data.reason not in REPORT_REASONS:
            raise HTTPException(status_code=422, detail="Invalid report reason")
        post = db.query(MatchBoardPost).filter(MatchBoardPost.post_id == post_id, MatchBoardPost.deleted_at.is_(None)).first()
        if not post:
            raise HTTPException(status_code=404, detail="Post not found")
        if post.author_user_id == user_id:
            raise HTTPException(status_code=400, detail="You cannot report your own content")
        if db.query(MatchBoardReport).filter(MatchBoardReport.reporter_user_id == user_id, MatchBoardReport.post_id == post_id).first():
            raise HTTPException(status_code=409, detail="You already reported this content")
        report = MatchBoardReport(reporter_user_id=user_id, post_id=post_id, reason=data.reason)
        db.add(report)
        db.commit()
        db.refresh(report)
        return {"report_id": report.report_id, "status": report.status}
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError as exc:
        db.rollback()
        if "match_board_reports_reporter_user_id_post_id_key" in str(exc.orig):
            raise HTTPException(status_code=409, detail="You already reported this content") from exc
        raise
    finally:
        db.close()
