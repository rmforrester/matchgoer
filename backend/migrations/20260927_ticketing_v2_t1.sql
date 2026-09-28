BEGIN;

CREATE TABLE ticket_sources (
    ticket_source_id BIGSERIAL PRIMARY KEY,
    club_venue_id BIGINT NOT NULL REFERENCES club_venues(club_venue_id) ON DELETE RESTRICT,
    source_url TEXT,
    source_domain VARCHAR(255),
    source_state VARCHAR(60) NOT NULL,
    ticketing_model VARCHAR(40) NOT NULL,
    adapter_type VARCHAR(40) NOT NULL,
    source_label VARCHAR(160),
    source_role VARCHAR(20) NOT NULL DEFAULT 'PRIMARY',
    priority SMALLINT NOT NULL DEFAULT 100,
    operational_status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    verified_at TIMESTAMPTZ,
    last_reviewed_at TIMESTAMPTZ,
    review_due_at TIMESTAMPTZ,
    last_attempted_at TIMESTAMPTZ,
    last_successful_at TIMESTAMPTZ,
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    last_http_status INTEGER,
    adapter_health VARCHAR(20) NOT NULL DEFAULT 'UNKNOWN',
    stale_after_hours INTEGER NOT NULL DEFAULT 48,
    last_failure_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_ticket_sources_state CHECK (source_state IN (
        'VERIFIED_DIRECT_PURCHASE_SOURCE','VERIFIED_OFFICIAL_TICKET_NAVIGATION_SOURCE',
        'PAY_AT_GATE_OR_OFFLINE_SOURCE','FIXTURE_SPECIFIC_TICKETING','NO_ONLINE_SALES',
        'NO_SAFE_TICKET_SOURCE','SOURCE_NEEDS_REVIEW','SOURCE_STALE')),
    CONSTRAINT ck_ticket_sources_model CHECK (ticketing_model IN (
        'ONLINE_DIRECT','ONLINE_NAVIGATION','PAY_AT_GATE','OFFLINE','FIXTURE_SPECIFIC','NONE','UNKNOWN')),
    CONSTRAINT ck_ticket_sources_adapter CHECK (adapter_type IN (
        'STATIC_OFFICIAL_HTML','DYNAMIC_OFFICIAL_HTML','OFFICIAL_TICKETING_VENDOR',
        'JAVASCRIPT_APP','LOGIN_REQUIRED','GUIDANCE_PAGE','ANTI_BOT_OR_UNKNOWN','OTHER')),
    CONSTRAINT ck_ticket_sources_role CHECK (source_role IN ('PRIMARY','SECONDARY','GUIDANCE')),
    CONSTRAINT ck_ticket_sources_operational CHECK (operational_status IN ('ACTIVE','PAUSED','DISABLED','REVIEW')),
    CONSTRAINT ck_ticket_sources_health CHECK (adapter_health IN ('HEALTHY','DEGRADED','FAILING','UNKNOWN')),
    CONSTRAINT ck_ticket_sources_priority CHECK (priority > 0),
    CONSTRAINT ck_ticket_sources_failures CHECK (consecutive_failures >= 0),
    CONSTRAINT ck_ticket_sources_stale_hours CHECK (stale_after_hours > 0),
    CONSTRAINT ck_ticket_sources_http CHECK (last_http_status IS NULL OR last_http_status BETWEEN 100 AND 599),
    CONSTRAINT ck_ticket_sources_review_dates CHECK (review_due_at IS NULL OR last_reviewed_at IS NULL OR review_due_at >= last_reviewed_at),
    CONSTRAINT ck_ticket_sources_attempt_dates CHECK (last_successful_at IS NULL OR last_attempted_at IS NULL OR last_successful_at <= last_attempted_at),
    CONSTRAINT ck_ticket_sources_url_shape CHECK (
        (source_url IS NULL AND source_domain IS NULL) OR
        (source_url ~ '^https://' AND btrim(source_domain) <> '')),
    CONSTRAINT ck_ticket_sources_online_url CHECK (
        source_state NOT IN ('VERIFIED_DIRECT_PURCHASE_SOURCE','VERIFIED_OFFICIAL_TICKET_NAVIGATION_SOURCE','FIXTURE_SPECIFIC_TICKETING')
        OR source_url IS NOT NULL)
);

CREATE UNIQUE INDEX uq_ticket_sources_club_venue_url
    ON ticket_sources (club_venue_id, source_url) WHERE source_url IS NOT NULL;
CREATE UNIQUE INDEX uq_ticket_sources_active_primary
    ON ticket_sources (club_venue_id) WHERE source_role = 'PRIMARY' AND operational_status = 'ACTIVE';
CREATE INDEX ix_ticket_sources_club_venue ON ticket_sources (club_venue_id);
CREATE INDEX ix_ticket_sources_active_verified ON ticket_sources (source_state, priority)
    WHERE operational_status = 'ACTIVE' AND source_state IN ('VERIFIED_DIRECT_PURCHASE_SOURCE','VERIFIED_OFFICIAL_TICKET_NAVIGATION_SOURCE');
CREATE INDEX ix_ticket_sources_due_check ON ticket_sources (last_attempted_at, priority)
    WHERE operational_status = 'ACTIVE';
CREATE INDEX ix_ticket_sources_stale ON ticket_sources (last_successful_at)
    WHERE operational_status = 'ACTIVE';

CREATE TABLE ticket_source_legacy_facts (
    ticket_source_id BIGINT NOT NULL REFERENCES ticket_sources(ticket_source_id) ON DELETE CASCADE,
    legacy_fact_id BIGINT NOT NULL REFERENCES venue_guide_facts(fact_id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (ticket_source_id, legacy_fact_id)
);
CREATE INDEX ix_ticket_source_legacy_facts_fact ON ticket_source_legacy_facts (legacy_fact_id);

CREATE TABLE ticket_refresh_runs (
    ticket_refresh_run_id BIGSERIAL PRIMARY KEY,
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    run_status VARCHAR(20) NOT NULL,
    adapter_version VARCHAR(80),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_ticket_refresh_runs_status CHECK (run_status IN ('RUNNING','SUCCEEDED','PARTIAL','FAILED','CANCELLED')),
    CONSTRAINT ck_ticket_refresh_runs_dates CHECK (completed_at IS NULL OR completed_at >= started_at)
);

CREATE TABLE ticket_source_checks (
    ticket_source_check_id BIGSERIAL PRIMARY KEY,
    ticket_source_id BIGINT NOT NULL REFERENCES ticket_sources(ticket_source_id) ON DELETE RESTRICT,
    ticket_refresh_run_id BIGINT REFERENCES ticket_refresh_runs(ticket_refresh_run_id) ON DELETE SET NULL,
    attempted_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    check_outcome VARCHAR(30) NOT NULL,
    http_status INTEGER,
    response_fingerprint VARCHAR(128),
    failure_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_ticket_source_checks_outcome CHECK (check_outcome IN ('SUCCESS','NO_CHANGE','SOURCE_UNAVAILABLE','ADAPTER_FAILURE','AUTH_REQUIRED','BLOCKED','PARTIAL')),
    CONSTRAINT ck_ticket_source_checks_http CHECK (http_status IS NULL OR http_status BETWEEN 100 AND 599),
    CONSTRAINT ck_ticket_source_checks_dates CHECK (completed_at IS NULL OR completed_at >= attempted_at)
);
CREATE INDEX ix_ticket_source_checks_source_time ON ticket_source_checks (ticket_source_id, attempted_at DESC);

CREATE TABLE ticket_availability_observations (
    ticket_availability_observation_id BIGSERIAL PRIMARY KEY,
    fixture_id INTEGER REFERENCES fixtures(fixture_id) ON DELETE RESTRICT,
    ticket_source_id BIGINT NOT NULL REFERENCES ticket_sources(ticket_source_id) ON DELETE RESTRICT,
    ticket_refresh_run_id BIGINT REFERENCES ticket_refresh_runs(ticket_refresh_run_id) ON DELETE SET NULL,
    observed_state VARCHAR(50) NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    valid_until TIMESTAMPTZ,
    purchase_url TEXT,
    source_listing_id VARCHAR(255),
    source_opponent_label VARCHAR(255),
    source_fixture_at TIMESTAMPTZ,
    matching_outcome VARCHAR(50) NOT NULL,
    matching_evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    adapter_version VARCHAR(80),
    source_response_fingerprint VARCHAR(128),
    supersedes_observation_id BIGINT REFERENCES ticket_availability_observations(ticket_availability_observation_id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_ticket_observations_state CHECK (observed_state IN (
        'ON_SALE','NOT_ON_SALE_YET','SALE_STATUS_UNKNOWN','SOLD_OUT','PAY_AT_GATE',
        'OFFLINE_PURCHASE','FIXTURE_SPECIFIC_GUIDANCE','NO_SAFE_TICKET_INFORMATION',
        'MATCHING_REVIEW_REQUIRED','CANCELLED_OR_NOT_APPLICABLE')),
    CONSTRAINT ck_ticket_observations_match CHECK (matching_outcome IN (
        'MATCHED_CANONICAL_FIXTURE','NO_CANONICAL_MATCH','MULTIPLE_POSSIBLE_MATCHES',
        'DATE_OR_OPPONENT_CONFLICT','FIXTURE_NOT_IN_MATCHGOER','MATCHING_REVIEW_REQUIRED')),
    CONSTRAINT ck_ticket_observations_fixture_match CHECK (
        (matching_outcome = 'MATCHED_CANONICAL_FIXTURE' AND fixture_id IS NOT NULL) OR
        (matching_outcome <> 'MATCHED_CANONICAL_FIXTURE')),
    CONSTRAINT ck_ticket_observations_validity CHECK (valid_until IS NULL OR valid_until >= observed_at),
    CONSTRAINT ck_ticket_observations_purchase_url CHECK (purchase_url IS NULL OR purchase_url ~ '^https://'),
    CONSTRAINT ck_ticket_observations_sale_evidence CHECK (
        observed_state NOT IN ('ON_SALE','NOT_ON_SALE_YET','SOLD_OUT') OR matching_evidence <> '{}'::jsonb),
    CONSTRAINT ck_ticket_observations_not_self_superseding CHECK (
        supersedes_observation_id IS NULL OR supersedes_observation_id <> ticket_availability_observation_id),
    CONSTRAINT uq_ticket_observation_identity UNIQUE
        (ticket_availability_observation_id, fixture_id, ticket_source_id)
);
CREATE UNIQUE INDEX uq_ticket_observations_dedup ON ticket_availability_observations
    (ticket_source_id, COALESCE(source_listing_id, ''), observed_at, COALESCE(source_response_fingerprint, ''));
CREATE INDEX ix_ticket_observations_fixture_time ON ticket_availability_observations (fixture_id, observed_at DESC) WHERE fixture_id IS NOT NULL;
CREATE INDEX ix_ticket_observations_source_time ON ticket_availability_observations (ticket_source_id, observed_at DESC);
CREATE INDEX ix_ticket_observations_30d ON ticket_availability_observations (observed_at, observed_state, matching_outcome);

CREATE FUNCTION reject_ticket_observation_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'ticket availability observations are append-only';
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER ticket_observations_append_only
    BEFORE UPDATE OR DELETE ON ticket_availability_observations
    FOR EACH ROW EXECUTE FUNCTION reject_ticket_observation_mutation();

CREATE TABLE fixture_ticket_availability (
    fixture_ticket_availability_id BIGSERIAL PRIMARY KEY,
    fixture_id INTEGER NOT NULL REFERENCES fixtures(fixture_id) ON DELETE RESTRICT,
    ticket_source_id BIGINT NOT NULL REFERENCES ticket_sources(ticket_source_id) ON DELETE RESTRICT,
    current_observation_id BIGINT NOT NULL,
    availability_state VARCHAR(50) NOT NULL,
    purchase_url TEXT,
    observed_at TIMESTAMPTZ NOT NULL,
    valid_until TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_fixture_ticket_availability_source UNIQUE (fixture_id, ticket_source_id),
    CONSTRAINT uq_fixture_ticket_availability_observation UNIQUE (current_observation_id),
    CONSTRAINT fk_fixture_ticket_availability_observation
        FOREIGN KEY (current_observation_id, fixture_id, ticket_source_id)
        REFERENCES ticket_availability_observations
            (ticket_availability_observation_id, fixture_id, ticket_source_id)
        ON DELETE RESTRICT,
    CONSTRAINT ck_fixture_ticket_availability_state CHECK (availability_state IN (
        'ON_SALE','NOT_ON_SALE_YET','SALE_STATUS_UNKNOWN','SOLD_OUT','PAY_AT_GATE',
        'OFFLINE_PURCHASE','FIXTURE_SPECIFIC_GUIDANCE','NO_SAFE_TICKET_INFORMATION',
        'MATCHING_REVIEW_REQUIRED','CANCELLED_OR_NOT_APPLICABLE')),
    CONSTRAINT ck_fixture_ticket_availability_validity CHECK (valid_until IS NULL OR valid_until >= observed_at),
    CONSTRAINT ck_fixture_ticket_availability_url CHECK (purchase_url IS NULL OR purchase_url ~ '^https://')
);
CREATE INDEX ix_fixture_ticket_availability_fixture ON fixture_ticket_availability (fixture_id, availability_state);
CREATE INDEX ix_fixture_ticket_availability_valid ON fixture_ticket_availability (fixture_id, valid_until, observed_at DESC);

COMMIT;
