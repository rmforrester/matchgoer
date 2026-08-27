BEGIN;

CREATE TABLE club_venues (
    club_venue_id BIGSERIAL PRIMARY KEY,
    team_id INTEGER NOT NULL REFERENCES teams(team_id) ON DELETE RESTRICT,
    venue_id INTEGER NOT NULL REFERENCES venues(venue_id) ON DELETE RESTRICT,
    relationship_type VARCHAR(30) NOT NULL,
    valid_from DATE,
    valid_until DATE,
    status VARCHAR(20) NOT NULL DEFAULT 'DRAFT',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_club_venues_relationship_type CHECK (relationship_type IN ('HOME', 'TEMPORARY_HOME', 'GROUND_SHARE')),
    CONSTRAINT ck_club_venues_status CHECK (status IN ('CURRENT', 'HISTORICAL', 'DRAFT')),
    CONSTRAINT ck_club_venues_valid_dates CHECK (valid_until IS NULL OR valid_from IS NULL OR valid_until >= valid_from),
    CONSTRAINT uq_club_venues_team_venue_from UNIQUE NULLS NOT DISTINCT (team_id, venue_id, valid_from)
);

CREATE INDEX ix_club_venues_fixture_resolution ON club_venues (team_id, venue_id, status);

CREATE TABLE pre_match_spots (
    pre_match_spot_id BIGSERIAL PRIMARY KEY,
    club_venue_id BIGINT NOT NULL REFERENCES club_venues(club_venue_id) ON DELETE RESTRICT,
    display_name VARCHAR(160) NOT NULL,
    classification VARCHAR(30) NOT NULL,
    audience VARCHAR(10) NOT NULL,
    supporting_line VARCHAR(180) NOT NULL,
    maps_destination VARCHAR(300) NOT NULL,
    confidence VARCHAR(10) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'DRAFT',
    business_status VARCHAR(20) NOT NULL DEFAULT 'UNKNOWN',
    reviewed_at DATE,
    review_after DATE,
    display_order SMALLINT NOT NULL,
    approved_at TIMESTAMPTZ,
    approved_by VARCHAR(160),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_pre_match_spots_name_not_blank CHECK (btrim(display_name) <> ''),
    CONSTRAINT ck_pre_match_spots_line_not_blank CHECK (btrim(supporting_line) <> ''),
    CONSTRAINT ck_pre_match_spots_maps_not_blank CHECK (btrim(maps_destination) <> ''),
    CONSTRAINT ck_pre_match_spots_classification CHECK (classification IN ('SUPPORTER_SPOT', 'CLUB_MATCHDAY_VENUE', 'SUPPORTER_AREA')),
    CONSTRAINT ck_pre_match_spots_audience CHECK (audience IN ('HOME', 'MIXED')),
    CONSTRAINT ck_pre_match_spots_confidence CHECK (confidence IN ('HIGH', 'MEDIUM', 'LOW')),
    CONSTRAINT ck_pre_match_spots_status CHECK (status IN ('DRAFT', 'CURRENT', 'NEEDS_REVIEW', 'ARCHIVED')),
    CONSTRAINT ck_pre_match_spots_business_status CHECK (business_status IN ('OPEN', 'UNKNOWN', 'CLOSED', 'NOT_APPLICABLE')),
    CONSTRAINT ck_pre_match_spots_display_order CHECK (display_order BETWEEN 1 AND 3),
    CONSTRAINT ck_pre_match_spots_review_dates CHECK (review_after IS NULL OR reviewed_at IS NULL OR review_after >= reviewed_at),
    CONSTRAINT ck_pre_match_spots_approval_pair CHECK ((approved_at IS NULL) = (approved_by IS NULL))
);

CREATE UNIQUE INDEX uq_pre_match_spots_current_order
    ON pre_match_spots (club_venue_id, display_order) WHERE status = 'CURRENT';
CREATE INDEX ix_pre_match_spots_publication
    ON pre_match_spots (club_venue_id, status, display_order);

CREATE TABLE pre_match_spot_evidence (
    evidence_id BIGSERIAL PRIMARY KEY,
    pre_match_spot_id BIGINT NOT NULL REFERENCES pre_match_spots(pre_match_spot_id) ON DELETE CASCADE,
    source_type VARCHAR(40) NOT NULL,
    source_url TEXT,
    source_date DATE,
    captured_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    disposition VARCHAR(20) NOT NULL,
    evidence_note VARCHAR(500) NOT NULL,
    contributor_user_id INTEGER REFERENCES users(user_id) ON DELETE SET NULL,
    review_status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_pre_match_spot_evidence_source_type CHECK (source_type IN ('OFFICIAL', 'REDDIT', 'FAN_FORUM', 'SUPPORTER_ORGANISATION', 'LOCAL_MEDIA', 'MATCHGOER_SUPPORTER_SUBMISSION', 'MATCHGOER_CORROBORATION', 'EDITORIAL_RESEARCH', 'OTHER')),
    CONSTRAINT ck_pre_match_spot_evidence_disposition CHECK (disposition IN ('SUPPORTS', 'CONTRADICTS')),
    CONSTRAINT ck_pre_match_spot_evidence_review_status CHECK (review_status IN ('PENDING', 'ACCEPTED', 'REJECTED')),
    CONSTRAINT ck_pre_match_spot_evidence_note_not_blank CHECK (btrim(evidence_note) <> '')
);

CREATE INDEX ix_pre_match_spot_evidence_review
    ON pre_match_spot_evidence (pre_match_spot_id, review_status, captured_at);

ALTER TABLE venue_guide_facts ADD COLUMN club_venue_id BIGINT;
ALTER TABLE venue_guide_facts
    ADD CONSTRAINT fk_venue_guide_facts_club_venue
    FOREIGN KEY (club_venue_id) REFERENCES club_venues(club_venue_id) ON DELETE RESTRICT;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM venue_guide_facts WHERE venue_id IS NULL) THEN
        RAISE EXCEPTION 'Legacy venue_guide_facts ownership is incompatible: venue_id is null';
    END IF;
END $$;

ALTER TABLE venue_guide_facts ALTER COLUMN venue_id DROP NOT NULL;
ALTER TABLE venue_guide_facts
    ADD CONSTRAINT ck_venue_guide_facts_exactly_one_owner
    CHECK ((venue_id IS NULL) <> (club_venue_id IS NULL));
CREATE INDEX ix_venue_guide_facts_club_venue_status
    ON venue_guide_facts (club_venue_id, status, section, display_order);

COMMIT;
