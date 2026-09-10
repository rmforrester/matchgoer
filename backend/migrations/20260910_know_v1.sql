BEGIN;

CREATE TABLE know_facts (
    know_fact_id BIGSERIAL PRIMARY KEY,
    editorial_key VARCHAR(160) NOT NULL UNIQUE,
    team_id INTEGER REFERENCES teams(team_id) ON DELETE RESTRICT,
    club_venue_id BIGINT REFERENCES club_venues(club_venue_id) ON DELETE RESTRICT,
    venue_id INTEGER REFERENCES venues(venue_id) ON DELETE RESTRICT,
    fixture_id INTEGER REFERENCES fixtures(fixture_id) ON DELETE RESTRICT,
    module VARCHAR(30) NOT NULL,
    headline VARCHAR(160),
    content TEXT NOT NULL,
    display_order INTEGER NOT NULL DEFAULT 1,
    publication_status VARCHAR(20) NOT NULL DEFAULT 'DRAFT',
    confidence VARCHAR(10) NOT NULL DEFAULT 'MEDIUM',
    claim_sensitivity VARCHAR(20) NOT NULL DEFAULT 'STANDARD',
    reviewed_at DATE,
    review_after DATE,
    expires_at DATE,
    approved_at TIMESTAMPTZ,
    approved_by VARCHAR(160),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_know_facts_exactly_one_subject CHECK (num_nonnulls(team_id, club_venue_id, venue_id, fixture_id) = 1),
    CONSTRAINT ck_know_facts_module CHECK (module IN ('CLUB', 'SUPPORTERS', 'MATCHDAY', 'DONT_MISS', 'GOOD_TO_KNOW')),
    CONSTRAINT ck_know_facts_module_subject CHECK (
        (module IN ('CLUB', 'SUPPORTERS') AND team_id IS NOT NULL)
        OR (module = 'MATCHDAY' AND club_venue_id IS NOT NULL)
        OR module IN ('DONT_MISS', 'GOOD_TO_KNOW')
    ),
    CONSTRAINT ck_know_facts_publication_status CHECK (publication_status IN ('DRAFT', 'PUBLISHED', 'NEEDS_REVIEW', 'ARCHIVED', 'REJECTED')),
    CONSTRAINT ck_know_facts_confidence CHECK (confidence IN ('HIGH', 'MEDIUM', 'LOW')),
    CONSTRAINT ck_know_facts_claim_sensitivity CHECK (claim_sensitivity IN ('STANDARD', 'SENSITIVE')),
    CONSTRAINT ck_know_facts_content_not_blank CHECK (btrim(content) <> ''),
    CONSTRAINT ck_know_facts_headline_not_blank CHECK (headline IS NULL OR btrim(headline) <> ''),
    CONSTRAINT ck_know_facts_display_order_positive CHECK (display_order > 0),
    CONSTRAINT ck_know_facts_expiry_after_review CHECK (expires_at IS NULL OR reviewed_at IS NULL OR expires_at >= reviewed_at),
    CONSTRAINT ck_know_facts_review_after_review CHECK (review_after IS NULL OR reviewed_at IS NULL OR review_after >= reviewed_at),
    CONSTRAINT ck_know_facts_approval_pair CHECK ((approved_at IS NULL) = (approved_by IS NULL))
);

CREATE INDEX ix_know_facts_team_publication ON know_facts (team_id, publication_status, module, display_order);
CREATE INDEX ix_know_facts_club_venue_publication ON know_facts (club_venue_id, publication_status, module, display_order);
CREATE INDEX ix_know_facts_venue_publication ON know_facts (venue_id, publication_status, module, display_order);
CREATE INDEX ix_know_facts_fixture_publication ON know_facts (fixture_id, publication_status, module, display_order);
CREATE UNIQUE INDEX uq_know_facts_team_dont_miss ON know_facts (team_id) WHERE module='DONT_MISS' AND publication_status='PUBLISHED';
CREATE UNIQUE INDEX uq_know_facts_club_venue_dont_miss ON know_facts (club_venue_id) WHERE module='DONT_MISS' AND publication_status='PUBLISHED';
CREATE UNIQUE INDEX uq_know_facts_venue_dont_miss ON know_facts (venue_id) WHERE module='DONT_MISS' AND publication_status='PUBLISHED';
CREATE UNIQUE INDEX uq_know_facts_fixture_dont_miss ON know_facts (fixture_id) WHERE module='DONT_MISS' AND publication_status='PUBLISHED';

CREATE TABLE know_fact_evidence (
    evidence_id BIGSERIAL PRIMARY KEY,
    know_fact_id BIGINT NOT NULL REFERENCES know_facts(know_fact_id) ON DELETE CASCADE,
    source_type VARCHAR(40) NOT NULL,
    source_title VARCHAR(200) NOT NULL,
    source_url TEXT,
    source_date DATE,
    evidence_note VARCHAR(500) NOT NULL,
    disposition VARCHAR(20) NOT NULL DEFAULT 'SUPPORTS',
    review_status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    contributor_user_id INTEGER REFERENCES users(user_id) ON DELETE SET NULL,
    reviewed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_know_fact_evidence_source_type CHECK (source_type IN ('OFFICIAL', 'SUPPORTER_ORGANISATION', 'LOCAL_MEDIA', 'ACADEMIC', 'BOOK', 'INTERVIEW', 'REDDIT', 'FAN_FORUM', 'MATCHGOER_SUPPORTER_SUBMISSION', 'EDITORIAL_RESEARCH', 'OTHER')),
    CONSTRAINT ck_know_fact_evidence_disposition CHECK (disposition IN ('SUPPORTS', 'CONTRADICTS')),
    CONSTRAINT ck_know_fact_evidence_review_status CHECK (review_status IN ('PENDING', 'ACCEPTED', 'REJECTED')),
    CONSTRAINT ck_know_fact_evidence_source_title_not_blank CHECK (btrim(source_title) <> ''),
    CONSTRAINT ck_know_fact_evidence_note_not_blank CHECK (btrim(evidence_note) <> ''),
    CONSTRAINT uq_know_fact_evidence_source UNIQUE (know_fact_id, source_title, source_url)
);

CREATE INDEX ix_know_fact_evidence_review ON know_fact_evidence (know_fact_id, review_status, disposition);

ALTER TABLE matchday_tips ALTER COLUMN status SET DEFAULT 'pending';

COMMIT;
