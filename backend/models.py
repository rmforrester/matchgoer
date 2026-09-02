from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Index,
    String,
    UniqueConstraint,
    ForeignKeyConstraint,
    BigInteger,
    Text,
    text,
)
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func


Base = declarative_base()


class Venue(Base):
    __tablename__ = "venues"

    venue_id = Column(Integer, primary_key=True)
    provider_venue_id = Column(Integer, unique=True, nullable=True)

    name = Column(String)
    address = Column(String)
    city = Column(String)
    country = Column(String)

    capacity = Column(Integer)

    latitude = Column(Float)
    longitude = Column(Float)

    names = relationship("VenueName", back_populates="venue", cascade="all, delete-orphan")
    provider_refs = relationship("VenueProviderRef", back_populates="venue", cascade="all, delete-orphan")
    guide_facts = relationship("VenueGuideFact", back_populates="venue", cascade="all, delete-orphan")


class VenueGuideFact(Base):
    """A small, sourced practical answer; not a generic venue article."""

    __tablename__ = "venue_guide_facts"
    __table_args__ = (
        CheckConstraint(
            "section IN ('getting_there', 'tickets_entry', 'before_match', 'at_ground', 'getting_back')",
            name="ck_venue_guide_facts_section",
        ),
        CheckConstraint(
            "source_type IN ('official', 'matchgoer_research', 'supporter')",
            name="ck_venue_guide_facts_source_type",
        ),
        CheckConstraint(
            "status IN ('current', 'needs_review', 'draft', 'archived')",
            name="ck_venue_guide_facts_status",
        ),
        CheckConstraint(
            "confidence IN ('high', 'medium', 'low')",
            name="ck_venue_guide_facts_confidence",
        ),
        CheckConstraint("btrim(topic) <> ''", name="ck_venue_guide_facts_topic_not_blank"),
        CheckConstraint("btrim(content) <> ''", name="ck_venue_guide_facts_content_not_blank"),
        CheckConstraint(
            "expires_at IS NULL OR reviewed_at IS NULL OR expires_at >= reviewed_at",
            name="ck_venue_guide_facts_expiry_after_review",
        ),
        CheckConstraint(
            "(venue_id IS NULL) <> (club_venue_id IS NULL)",
            name="ck_venue_guide_facts_exactly_one_owner",
        ),
    )

    fact_id = Column(BigInteger, primary_key=True)
    venue_id = Column(Integer, ForeignKey("venues.venue_id", ondelete="CASCADE"), nullable=True, index=True)
    club_venue_id = Column(
        BigInteger,
        ForeignKey("club_venues.club_venue_id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    section = Column(String(30), nullable=False)
    topic = Column(String(80), nullable=False)
    content = Column(Text, nullable=False)
    source_type = Column(String(30), nullable=False)
    source_label = Column(String(160), nullable=True)
    source_url = Column(Text, nullable=True)
    reviewed_at = Column(Date, nullable=True)
    confidence = Column(String(10), nullable=False, default="medium")
    status = Column(String(20), nullable=False, default="draft", index=True)
    review_after = Column(Date, nullable=True)
    expires_at = Column(Date, nullable=True)
    display_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    venue = relationship("Venue", back_populates="guide_facts")
    club_venue = relationship("ClubVenue", back_populates="guide_facts")


class VenueName(Base):
    __tablename__ = "venue_names"
    __table_args__ = (
        UniqueConstraint("venue_id", "normalized_name", name="uq_venue_names_venue_normalized"),
    )

    venue_name_id = Column(BigInteger, primary_key=True)
    venue_id = Column(Integer, ForeignKey("venues.venue_id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    normalized_name = Column(String(255), nullable=False)
    name_type = Column(String(20), nullable=False)
    valid_from = Column(Date, nullable=True)
    valid_to = Column(Date, nullable=True)
    source = Column(String(80), nullable=True)
    observed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    venue = relationship("Venue", back_populates="names")


class VenueProviderRef(Base):
    __tablename__ = "venue_provider_refs"
    __table_args__ = (
        UniqueConstraint("provider", "provider_venue_id", name="uq_venue_provider_refs_provider_id"),
    )

    venue_provider_ref_id = Column(BigInteger, primary_key=True)
    venue_id = Column(Integer, ForeignKey("venues.venue_id", ondelete="CASCADE"), nullable=False)
    provider = Column(String(40), nullable=False)
    provider_venue_id = Column(Integer, nullable=False)
    valid_from = Column(Date, nullable=True)
    valid_to = Column(Date, nullable=True)
    is_primary = Column(Boolean, nullable=False, default=False)
    observed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    venue = relationship("Venue", back_populates="provider_refs")


class Fixture(Base):
    __tablename__ = "fixtures"

    fixture_id = Column(Integer, primary_key=True)

    # Canonical contract: timezone-aware UTC instant stored as PostgreSQL timestamptz.
    fixture_date = Column(DateTime(timezone=True))

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


class DecisionFact(Base):
    """A reviewed reason to consider a team pairing or canonical venue."""

    __tablename__ = "decision_facts"
    __table_args__ = (
        CheckConstraint("subject_type IN ('TEAM_PAIR', 'VENUE')", name="ck_decision_facts_subject_type"),
        CheckConstraint(
            "(subject_type = 'TEAM_PAIR' AND team_a_id IS NOT NULL AND team_b_id IS NOT NULL "
            "AND team_a_id < team_b_id AND venue_id IS NULL) OR "
            "(subject_type = 'VENUE' AND team_a_id IS NULL AND team_b_id IS NULL AND venue_id IS NOT NULL)",
            name="ck_decision_facts_subject_shape",
        ),
        CheckConstraint(
            "(subject_type = 'TEAM_PAIR' AND attribute_key = 'SIGNIFICANT_RIVALRY') OR "
            "(subject_type = 'VENUE' AND attribute_key IN ('FOOTBALL_LANDMARK', 'UNIQUE_SETTING', 'CLASSIC_GROUND'))",
            name="ck_decision_facts_attribute_subject",
        ),
        CheckConstraint("publication_status IN ('DRAFT', 'PUBLISHED', 'REJECTED')", name="ck_decision_facts_publication_status"),
        CheckConstraint("confidence IN ('HIGH', 'MEDIUM', 'LOW')", name="ck_decision_facts_confidence"),
        CheckConstraint("btrim(label) <> ''", name="ck_decision_facts_label_not_blank"),
        CheckConstraint("btrim(explanation) <> ''", name="ck_decision_facts_explanation_not_blank"),
        CheckConstraint("effective_to IS NULL OR effective_from IS NULL OR effective_to >= effective_from", name="ck_decision_facts_effective_dates"),
        Index(
            "uq_decision_facts_team_pair_attribute",
            "team_a_id", "team_b_id", "attribute_key",
            unique=True,
            postgresql_where=text("subject_type = 'TEAM_PAIR'"),
        ),
        Index(
            "uq_decision_facts_venue_attribute",
            "venue_id", "attribute_key",
            unique=True,
            postgresql_where=text("subject_type = 'VENUE'"),
        ),
    )

    fact_id = Column(BigInteger, primary_key=True)
    subject_type = Column(String(20), nullable=False)
    team_a_id = Column(Integer, ForeignKey("teams.team_id", ondelete="RESTRICT"), nullable=True)
    team_b_id = Column(Integer, ForeignKey("teams.team_id", ondelete="RESTRICT"), nullable=True)
    venue_id = Column(Integer, ForeignKey("venues.venue_id", ondelete="RESTRICT"), nullable=True)
    attribute_key = Column(String(40), nullable=False)
    label = Column(String(120), nullable=False)
    explanation = Column(String(300), nullable=False)
    publication_status = Column(String(20), nullable=False, default="DRAFT", index=True)
    confidence = Column(String(10), nullable=False, default="MEDIUM")
    effective_from = Column(Date, nullable=True)
    effective_to = Column(Date, nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    reviewed_by = Column(String(160), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    evidence = relationship("DecisionEvidence", back_populates="fact", cascade="all, delete-orphan")

    def __init__(self, **kwargs):
        if kwargs.get("subject_type") == "TEAM_PAIR" and kwargs.get("team_a_id") is not None and kwargs.get("team_b_id") is not None:
            kwargs["team_a_id"], kwargs["team_b_id"] = sorted((kwargs["team_a_id"], kwargs["team_b_id"]))
        super().__init__(**kwargs)
        from decision import validate_decision_fact
        validate_decision_fact(self.subject_type, self.attribute_key)


class DecisionEvidence(Base):
    __tablename__ = "decision_evidence"
    __table_args__ = (
        CheckConstraint("disposition IN ('SUPPORTS', 'CONTRADICTS')", name="ck_decision_evidence_disposition"),
        CheckConstraint("review_status IN ('PENDING', 'ACCEPTED', 'REJECTED')", name="ck_decision_evidence_review_status"),
        CheckConstraint("btrim(source_title) <> ''", name="ck_decision_evidence_source_title_not_blank"),
        CheckConstraint("btrim(evidence_note) <> ''", name="ck_decision_evidence_note_not_blank"),
    )

    evidence_id = Column(BigInteger, primary_key=True)
    fact_id = Column(BigInteger, ForeignKey("decision_facts.fact_id", ondelete="CASCADE"), nullable=False, index=True)
    source_title = Column(String(200), nullable=False)
    source_url = Column(Text, nullable=True)
    evidence_note = Column(String(500), nullable=False)
    disposition = Column(String(20), nullable=False, default="SUPPORTS")
    retrieved_at = Column(Date, nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    review_status = Column(String(20), nullable=False, default="PENDING")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    fact = relationship("DecisionFact", back_populates="evidence")


class Team(Base):
    """Existing provider-ID keyed teams table used by ingestion."""

    __tablename__ = "teams"

    team_id = Column(Integer, primary_key=True)
    team_name = Column(String)
    venue_id = Column(Integer, ForeignKey("venues.venue_id"))
    active = Column(Boolean)

    venue = relationship("Venue")
    club_venues = relationship("ClubVenue", back_populates="team")


class ClubVenue(Base):
    """A time-bounded relationship between a club and a ground."""

    __tablename__ = "club_venues"
    __table_args__ = (
        CheckConstraint(
            "relationship_type IN ('HOME', 'TEMPORARY_HOME', 'GROUND_SHARE')",
            name="ck_club_venues_relationship_type",
        ),
        CheckConstraint(
            "status IN ('CURRENT', 'HISTORICAL', 'DRAFT')",
            name="ck_club_venues_status",
        ),
        CheckConstraint(
            "valid_until IS NULL OR valid_from IS NULL OR valid_until >= valid_from",
            name="ck_club_venues_valid_dates",
        ),
        UniqueConstraint(
            "team_id", "venue_id", "valid_from", name="uq_club_venues_team_venue_from"
        ),
    )

    club_venue_id = Column(BigInteger, primary_key=True)
    team_id = Column(Integer, ForeignKey("teams.team_id", ondelete="RESTRICT"), nullable=False)
    venue_id = Column(Integer, ForeignKey("venues.venue_id", ondelete="RESTRICT"), nullable=False)
    relationship_type = Column(String(30), nullable=False)
    valid_from = Column(Date, nullable=True)
    valid_until = Column(Date, nullable=True)
    status = Column(String(20), nullable=False, default="DRAFT")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    team = relationship("Team", back_populates="club_venues")
    venue = relationship("Venue")
    pre_match_spots = relationship("PreMatchSpot", back_populates="club_venue")
    guide_facts = relationship("VenueGuideFact", back_populates="club_venue")


class PreMatchSpot(Base):
    __tablename__ = "pre_match_spots"
    __table_args__ = (
        CheckConstraint("btrim(display_name) <> ''", name="ck_pre_match_spots_name_not_blank"),
        CheckConstraint("btrim(supporting_line) <> ''", name="ck_pre_match_spots_line_not_blank"),
        CheckConstraint("btrim(maps_destination) <> ''", name="ck_pre_match_spots_maps_not_blank"),
        CheckConstraint("classification IN ('SUPPORTER_SPOT', 'CLUB_MATCHDAY_VENUE', 'SUPPORTER_AREA')", name="ck_pre_match_spots_classification"),
        CheckConstraint("audience IN ('HOME', 'MIXED')", name="ck_pre_match_spots_audience"),
        CheckConstraint("confidence IN ('HIGH', 'MEDIUM', 'LOW')", name="ck_pre_match_spots_confidence"),
        CheckConstraint("status IN ('DRAFT', 'CURRENT', 'NEEDS_REVIEW', 'ARCHIVED')", name="ck_pre_match_spots_status"),
        CheckConstraint("business_status IN ('OPEN', 'UNKNOWN', 'CLOSED', 'NOT_APPLICABLE')", name="ck_pre_match_spots_business_status"),
        CheckConstraint("display_order BETWEEN 1 AND 3", name="ck_pre_match_spots_display_order"),
        CheckConstraint("review_after IS NULL OR reviewed_at IS NULL OR review_after >= reviewed_at", name="ck_pre_match_spots_review_dates"),
        CheckConstraint("(approved_at IS NULL) = (approved_by IS NULL)", name="ck_pre_match_spots_approval_pair"),
    )

    pre_match_spot_id = Column(BigInteger, primary_key=True)
    club_venue_id = Column(BigInteger, ForeignKey("club_venues.club_venue_id", ondelete="RESTRICT"), nullable=False)
    display_name = Column(String(160), nullable=False)
    classification = Column(String(30), nullable=False)
    audience = Column(String(10), nullable=False)
    supporting_line = Column(String(180), nullable=False)
    maps_destination = Column(String(300), nullable=False)
    confidence = Column(String(10), nullable=False)
    status = Column(String(20), nullable=False, default="DRAFT")
    business_status = Column(String(20), nullable=False, default="UNKNOWN")
    reviewed_at = Column(Date, nullable=True)
    review_after = Column(Date, nullable=True)
    display_order = Column(Integer, nullable=False)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    approved_by = Column(String(160), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    club_venue = relationship("ClubVenue", back_populates="pre_match_spots")
    evidence = relationship("PreMatchSpotEvidence", back_populates="spot", cascade="all, delete-orphan")


class PreMatchSpotEvidence(Base):
    __tablename__ = "pre_match_spot_evidence"
    __table_args__ = (
        CheckConstraint("source_type IN ('OFFICIAL', 'REDDIT', 'FAN_FORUM', 'SUPPORTER_ORGANISATION', 'LOCAL_MEDIA', 'MATCHGOER_SUPPORTER_SUBMISSION', 'MATCHGOER_CORROBORATION', 'EDITORIAL_RESEARCH', 'OTHER')", name="ck_pre_match_spot_evidence_source_type"),
        CheckConstraint("disposition IN ('SUPPORTS', 'CONTRADICTS')", name="ck_pre_match_spot_evidence_disposition"),
        CheckConstraint("review_status IN ('PENDING', 'ACCEPTED', 'REJECTED')", name="ck_pre_match_spot_evidence_review_status"),
        CheckConstraint("btrim(evidence_note) <> ''", name="ck_pre_match_spot_evidence_note_not_blank"),
    )

    evidence_id = Column(BigInteger, primary_key=True)
    pre_match_spot_id = Column(BigInteger, ForeignKey("pre_match_spots.pre_match_spot_id", ondelete="CASCADE"), nullable=False)
    source_type = Column(String(40), nullable=False)
    source_url = Column(Text, nullable=True)
    source_date = Column(Date, nullable=True)
    captured_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    disposition = Column(String(20), nullable=False)
    evidence_note = Column(String(500), nullable=False)
    contributor_user_id = Column(Integer, ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)
    review_status = Column(String(20), nullable=False, default="PENDING")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    spot = relationship("PreMatchSpot", back_populates="evidence")


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

    author_user_id = Column(
        Integer,
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
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

    user = relationship("User", foreign_keys=[user_id])

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


class VenueVisit(Base):
    """Attendance/history record, separate from a user's venue review."""

    __tablename__ = "venue_visits"

    visit_id = Column(BigInteger, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    venue_id = Column(Integer, ForeignKey("venues.venue_id"), nullable=False)
    fixture_id = Column(Integer, ForeignKey("fixtures.fixture_id"), nullable=True)
    visit_date = Column(Date, nullable=True)
    source = Column(String(40), nullable=False, default="manual")
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    user = relationship("User", foreign_keys=[user_id])
    venue = relationship("Venue")

    fixture = relationship("Fixture")

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

    account_status = Column(String(20), nullable=False, default="anonymous")
    registered_at = Column(DateTime(timezone=True), nullable=True)
    merged_into_user_id = Column(
        Integer,
        ForeignKey("users.user_id", ondelete="RESTRICT"),
        nullable=True,
    )

    created_at = Column(
        DateTime,
        server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "account_status IN ('anonymous', 'registered', 'suspended', 'merged', 'deleted')",
            name="ck_users_account_status",
        ),
        CheckConstraint(
            "merged_into_user_id IS NULL OR merged_into_user_id <> user_id",
            name="ck_users_not_merged_into_self",
        ),
    )


class UserIdentity(Base):
    __tablename__ = "user_identities"
    __table_args__ = (
        UniqueConstraint("issuer", "subject", name="uq_user_identities_issuer_subject"),
        CheckConstraint("btrim(issuer) <> ''", name="ck_user_identities_issuer_not_blank"),
        CheckConstraint("btrim(subject) <> ''", name="ck_user_identities_subject_not_blank"),
    )

    user_identity_id = Column(BigInteger, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True)
    issuer = Column(String(255), nullable=False)
    subject = Column(String(255), nullable=False)
    email = Column(String(320), nullable=True)
    email_verified_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_seen_at = Column(DateTime(timezone=True), nullable=True)


class AccountMergeAudit(Base):
    __tablename__ = "account_merge_audits"
    __table_args__ = (
        UniqueConstraint("source_user_id", name="uq_account_merge_audits_source_user"),
        CheckConstraint("source_user_id <> target_user_id", name="ck_account_merge_audits_distinct_users"),
        CheckConstraint("btrim(merge_source) <> ''", name="ck_account_merge_audits_source_not_blank"),
    )

    account_merge_audit_id = Column(BigInteger, primary_key=True)
    source_user_id = Column(Integer, ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=False)
    target_user_id = Column(Integer, ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=False, index=True)
    merge_source = Column(String(40), nullable=False)
    reason = Column(String(255), nullable=True)
    merged_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


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

    revoked_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", foreign_keys=[user_id])


class AccountConversionHandoff(Base):
    __tablename__ = "account_conversion_handoffs"
    __table_args__ = (
        CheckConstraint("token_digest ~ '^[0-9a-f]{64}$'", name="ck_account_conversion_handoff_digest"),
        CheckConstraint("(claimed_issuer IS NULL) = (claimed_subject IS NULL)", name="ck_account_conversion_handoff_claim_pair"),
        CheckConstraint("(consumed_at IS NULL) = (claimed_issuer IS NULL)", name="ck_account_conversion_handoff_consumption"),
    )

    token_digest = Column(String(64), primary_key=True)
    session_id = Column(String, ForeignKey("anonymous_sessions.session_id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    consumed_at = Column(DateTime(timezone=True), nullable=True)
    claimed_issuer = Column(String, nullable=True)
    claimed_subject = Column(String, nullable=True)

    session = relationship("AnonymousSession", foreign_keys=[session_id])
    user = relationship("User", foreign_keys=[user_id])

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

    user = relationship("User", foreign_keys=[user_id])

    fixture = relationship("Fixture")

    __table_args__ = (
            UniqueConstraint(
            "user_id",
            "fixture_id",
            name="unique_user_fixture_interest"
        ),
    )


class UserProfile(Base):
    __tablename__ = "user_profiles"
    user_id = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True)
    display_name = Column(String(40), nullable=False)
    supported_club = Column(String(80), nullable=True)
    username = Column(String(40), nullable=True)
    broad_location = Column(String(100), nullable=True)
    bio = Column(String(280), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)


class FixtureMeetingIntent(Base):
    __tablename__ = "fixture_meeting_intents"
    user_id = Column(Integer, ForeignKey("user_profiles.user_id", ondelete="CASCADE"), primary_key=True)
    fixture_id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id", "fixture_id"],
            ["interested_fixtures.user_id", "interested_fixtures.fixture_id"],
            ondelete="CASCADE",
        ),
    )


class MatchBoardPost(Base):
    __tablename__ = "match_board_posts"
    post_id = Column(BigInteger, primary_key=True)
    fixture_id = Column(Integer, ForeignKey("fixtures.fixture_id", ondelete="CASCADE"), nullable=False)
    author_user_id = Column(Integer, ForeignKey("user_profiles.user_id", ondelete="RESTRICT"), nullable=False)
    parent_post_id = Column(BigInteger, ForeignKey("match_board_posts.post_id", ondelete="RESTRICT"), nullable=True)
    body = Column(String(500), nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, nullable=True)
    deleted_at = Column(DateTime, nullable=True)


class MatchBoardReport(Base):
    __tablename__ = "match_board_reports"
    report_id = Column(BigInteger, primary_key=True)
    reporter_user_id = Column(Integer, ForeignKey("user_profiles.user_id", ondelete="CASCADE"), nullable=False)
    post_id = Column(BigInteger, ForeignKey("match_board_posts.post_id", ondelete="CASCADE"), nullable=False)
    reason = Column(String(30), nullable=False)
    status = Column(String(20), nullable=False, default="pending")
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    __table_args__ = (UniqueConstraint("reporter_user_id", "post_id", name="match_board_reports_reporter_user_id_post_id_key"),)


class SocialEvent(Base):
    __tablename__ = "social_events"
    event_id = Column(BigInteger, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)
    fixture_id = Column(Integer, ForeignKey("fixtures.fixture_id", ondelete="CASCADE"), nullable=False)
    event_type = Column(String(40), nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
