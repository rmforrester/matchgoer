from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func


Base = declarative_base()


class Venue(Base):
    __tablename__ = "venues"

    venue_id = Column(Integer, primary_key=True)

    name = Column(String)
    address = Column(String)
    city = Column(String)
    country = Column(String)

    capacity = Column(Integer)

    latitude = Column(Float)
    longitude = Column(Float)


class Fixture(Base):
    __tablename__ = "fixtures"

    fixture_id = Column(Integer, primary_key=True)

    fixture_date = Column(DateTime)

    venue_id = Column(
        Integer,
        ForeignKey("venues.venue_id")
    )

    venue = relationship("Venue")

    venue_name = Column(String)
    venue_city = Column(String)

    league_id = Column(Integer)
    league_name = Column(String)

    country = Column(String)

    season = Column(Integer)

    round = Column(String)

    status = Column(String)

    home_team_id = Column(Integer)
    home_team = Column(String)

    away_team_id = Column(Integer)
    away_team = Column(String)

    home_goals = Column(Integer)
    away_goals = Column(Integer)


class MatchdayTip(Base):
    __tablename__ = "matchday_tips"

    tip_id = Column(
        Integer,
        primary_key=True
    )

    venue_id = Column(
        Integer,
        ForeignKey("venues.venue_id")
    )

    venue = relationship("Venue")

    tip = Column(String)

    helpful_votes = Column(
        Integer,
        default=0
    )

    report_count = Column(
        Integer,
        default=0
    )

    status = Column(
        String,
        default="active"
    )

    created_at = Column(
        DateTime,
        server_default=func.now()
    )


class AwayDayReview(Base):
    __tablename__ = "away_day_reviews"

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "venue_id",
            name="uq_away_day_review_user_venue"
        ),
    )

    review_id = Column(
        Integer,
        primary_key=True
    )

    user_id = Column(
        Integer,
        ForeignKey("users.user_id"),
        nullable=False
    )

    venue_id = Column(
        Integer,
        ForeignKey("venues.venue_id"),
        nullable=False
    )

    fixture_id = Column(
        Integer,
        ForeignKey("fixtures.fixture_id"),
        nullable=True
    )

    visit_date = Column(
        DateTime,
        nullable=True
    )

    user = relationship("User")

    venue = relationship("Venue")

    fixture = relationship("Fixture")

    recommend = Column(
    Boolean,
    nullable=True
)

    overall_score = Column(
    Float,
    nullable=True
)

    atmosphere_score = Column(
        Integer,
        nullable=True
    )

    pubs_score = Column(
        Integer,
        nullable=True
    )

    getting_there_score = Column(
        Integer,
        nullable=True
    )

    facilities_score = Column(
        Integer,
        nullable=True
    )

    created_at = Column(
        DateTime,
        server_default=func.now()
    )

class User(Base):
    __tablename__ = "users"

    user_id = Column(
        Integer,
        primary_key=True
    )

    is_anonymous = Column(
        Boolean,
        nullable=False,
        default=True
    )

    created_at = Column(
        DateTime,
        server_default=func.now()
    )


class AnonymousSession(Base):
    __tablename__ = "anonymous_sessions"

    session_id = Column(
        String,
        primary_key=True
    )

    user_id = Column(
        Integer,
        ForeignKey("users.user_id"),
        nullable=False
    )

    created_at = Column(
        DateTime,
        server_default=func.now()
    )

    user = relationship("User")

class InterestedFixture(Base):
    __tablename__ = "interested_fixtures"

    interested_id = Column(
        Integer,
        primary_key=True
    )

    user_id = Column(
        Integer,
        ForeignKey("users.user_id"),
        nullable=False
    )

    fixture_id = Column(
        Integer,
        ForeignKey("fixtures.fixture_id"),
        nullable=False
    )

    created_at = Column(
        DateTime,
        server_default=func.now()
    )

    user = relationship("User")

    fixture = relationship("Fixture")

    __table_args__ = (
            UniqueConstraint(
            "user_id",
            "fixture_id",
            name="unique_user_fixture_interest"
        ),
    )