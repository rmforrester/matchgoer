BEGIN;

CREATE SEQUENCE matchgoer_team_id_seq
    AS INTEGER
    START WITH -1
    INCREMENT BY -1
    MINVALUE -2147483648
    MAXVALUE -1
    NO CYCLE;

CREATE TABLE team_identity_overrides (
    team_identity_override_id BIGSERIAL PRIMARY KEY,
    provider VARCHAR(40) NOT NULL,
    provider_team_id INTEGER NOT NULL,
    league_id INTEGER NOT NULL,
    season INTEGER NOT NULL,
    canonical_team_id INTEGER NOT NULL REFERENCES teams(team_id) ON DELETE RESTRICT,
    expected_provider_name VARCHAR(255) NOT NULL,
    review_status VARCHAR(20) NOT NULL,
    reason TEXT NOT NULL,
    provenance TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reviewed_at TIMESTAMPTZ,
    CONSTRAINT uq_team_identity_overrides_scope
        UNIQUE (provider, provider_team_id, league_id, season),
    CONSTRAINT ck_team_identity_overrides_provider_not_blank
        CHECK (btrim(provider) <> ''),
    CONSTRAINT ck_team_identity_overrides_provider_team_positive
        CHECK (provider_team_id > 0),
    CONSTRAINT ck_team_identity_overrides_league_positive
        CHECK (league_id > 0),
    CONSTRAINT ck_team_identity_overrides_season_positive
        CHECK (season > 0),
    CONSTRAINT ck_team_identity_overrides_canonical_nonzero
        CHECK (canonical_team_id <> 0),
    CONSTRAINT ck_team_identity_overrides_name_not_blank
        CHECK (btrim(expected_provider_name) <> ''),
    CONSTRAINT ck_team_identity_overrides_status
        CHECK (review_status IN ('APPROVED', 'REVIEW')),
    CONSTRAINT ck_team_identity_overrides_reason_not_blank
        CHECK (btrim(reason) <> ''),
    CONSTRAINT ck_team_identity_overrides_provenance_not_blank
        CHECK (btrim(provenance) <> ''),
    CONSTRAINT ck_team_identity_overrides_approval_reviewed
        CHECK (review_status <> 'APPROVED' OR reviewed_at IS NOT NULL)
);

CREATE INDEX ix_team_identity_overrides_canonical_team_id
    ON team_identity_overrides (canonical_team_id);

COMMIT;
