BEGIN;

CREATE TABLE decision_facts (
    fact_id BIGSERIAL PRIMARY KEY,
    subject_type VARCHAR(20) NOT NULL,
    team_a_id INTEGER REFERENCES teams(team_id) ON DELETE RESTRICT,
    team_b_id INTEGER REFERENCES teams(team_id) ON DELETE RESTRICT,
    venue_id INTEGER REFERENCES venues(venue_id) ON DELETE RESTRICT,
    attribute_key VARCHAR(40) NOT NULL,
    label VARCHAR(120) NOT NULL,
    explanation VARCHAR(300) NOT NULL,
    publication_status VARCHAR(20) NOT NULL DEFAULT 'DRAFT',
    confidence VARCHAR(10) NOT NULL DEFAULT 'MEDIUM',
    effective_from DATE,
    effective_to DATE,
    reviewed_at TIMESTAMPTZ,
    reviewed_by VARCHAR(160),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_decision_facts_subject_type CHECK (subject_type IN ('TEAM_PAIR', 'VENUE')),
    CONSTRAINT ck_decision_facts_subject_shape CHECK (
        (subject_type = 'TEAM_PAIR' AND team_a_id IS NOT NULL AND team_b_id IS NOT NULL AND team_a_id < team_b_id AND venue_id IS NULL)
        OR (subject_type = 'VENUE' AND team_a_id IS NULL AND team_b_id IS NULL AND venue_id IS NOT NULL)
    ),
    CONSTRAINT ck_decision_facts_attribute_subject CHECK (
        (subject_type = 'TEAM_PAIR' AND attribute_key = 'SIGNIFICANT_RIVALRY')
        OR (subject_type = 'VENUE' AND attribute_key IN ('FOOTBALL_LANDMARK', 'UNIQUE_SETTING', 'CLASSIC_GROUND'))
    ),
    CONSTRAINT ck_decision_facts_publication_status CHECK (publication_status IN ('DRAFT', 'PUBLISHED', 'REJECTED')),
    CONSTRAINT ck_decision_facts_confidence CHECK (confidence IN ('HIGH', 'MEDIUM', 'LOW')),
    CONSTRAINT ck_decision_facts_label_not_blank CHECK (btrim(label) <> ''),
    CONSTRAINT ck_decision_facts_explanation_not_blank CHECK (btrim(explanation) <> ''),
    CONSTRAINT ck_decision_facts_effective_dates CHECK (effective_to IS NULL OR effective_from IS NULL OR effective_to >= effective_from)
);

CREATE UNIQUE INDEX uq_decision_facts_team_pair_attribute
    ON decision_facts (team_a_id, team_b_id, attribute_key)
    WHERE subject_type = 'TEAM_PAIR';
CREATE UNIQUE INDEX uq_decision_facts_venue_attribute
    ON decision_facts (venue_id, attribute_key)
    WHERE subject_type = 'VENUE';
CREATE INDEX ix_decision_facts_publication
    ON decision_facts (publication_status, subject_type, effective_from, effective_to);

CREATE TABLE decision_evidence (
    evidence_id BIGSERIAL PRIMARY KEY,
    fact_id BIGINT NOT NULL REFERENCES decision_facts(fact_id) ON DELETE CASCADE,
    source_title VARCHAR(200) NOT NULL,
    source_url TEXT,
    evidence_note VARCHAR(500) NOT NULL,
    disposition VARCHAR(20) NOT NULL DEFAULT 'SUPPORTS',
    retrieved_at DATE,
    reviewed_at TIMESTAMPTZ,
    review_status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_decision_evidence_source_title_not_blank CHECK (btrim(source_title) <> ''),
    CONSTRAINT ck_decision_evidence_note_not_blank CHECK (btrim(evidence_note) <> ''),
    CONSTRAINT ck_decision_evidence_disposition CHECK (disposition IN ('SUPPORTS', 'CONTRADICTS')),
    CONSTRAINT ck_decision_evidence_review_status CHECK (review_status IN ('PENDING', 'ACCEPTED', 'REJECTED'))
);

CREATE INDEX ix_decision_evidence_fact_review
    ON decision_evidence (fact_id, review_status, created_at);

COMMIT;
