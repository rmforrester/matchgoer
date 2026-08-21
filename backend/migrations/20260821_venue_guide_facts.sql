BEGIN;

CREATE TABLE venue_guide_facts (
    fact_id BIGSERIAL PRIMARY KEY,
    venue_id INTEGER NOT NULL REFERENCES venues(venue_id) ON DELETE CASCADE,
    section VARCHAR(30) NOT NULL,
    topic VARCHAR(80) NOT NULL,
    content TEXT NOT NULL,
    source_type VARCHAR(30) NOT NULL,
    source_label VARCHAR(160),
    source_url TEXT,
    reviewed_at DATE,
    confidence VARCHAR(10) NOT NULL DEFAULT 'medium',
    status VARCHAR(20) NOT NULL DEFAULT 'draft',
    review_after DATE,
    expires_at DATE,
    display_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_venue_guide_facts_section CHECK (section IN ('getting_there', 'tickets_entry', 'before_match', 'at_ground', 'getting_back')),
    CONSTRAINT ck_venue_guide_facts_source_type CHECK (source_type IN ('official', 'matchgoer_research', 'supporter')),
    CONSTRAINT ck_venue_guide_facts_status CHECK (status IN ('current', 'needs_review', 'draft', 'archived')),
    CONSTRAINT ck_venue_guide_facts_confidence CHECK (confidence IN ('high', 'medium', 'low')),
    CONSTRAINT ck_venue_guide_facts_topic_not_blank CHECK (btrim(topic) <> ''),
    CONSTRAINT ck_venue_guide_facts_content_not_blank CHECK (btrim(content) <> ''),
    CONSTRAINT ck_venue_guide_facts_expiry_after_review CHECK (expires_at IS NULL OR reviewed_at IS NULL OR expires_at >= reviewed_at)
);

CREATE INDEX ix_venue_guide_facts_venue_status
    ON venue_guide_facts (venue_id, status, section, display_order);

COMMIT;
