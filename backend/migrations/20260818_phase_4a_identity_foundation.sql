BEGIN;

ALTER TABLE users
    ADD COLUMN account_status VARCHAR(20),
    ADD COLUMN registered_at TIMESTAMPTZ,
    ADD COLUMN merged_into_user_id INTEGER;

UPDATE users
SET account_status = CASE WHEN is_anonymous THEN 'anonymous' ELSE 'registered' END;

ALTER TABLE users
    ALTER COLUMN account_status SET DEFAULT 'anonymous',
    ALTER COLUMN account_status SET NOT NULL,
    ADD CONSTRAINT ck_users_account_status
        CHECK (account_status IN ('anonymous', 'registered', 'suspended', 'merged', 'deleted')),
    ADD CONSTRAINT fk_users_merged_into_user
        FOREIGN KEY (merged_into_user_id) REFERENCES users(user_id) ON DELETE RESTRICT,
    ADD CONSTRAINT ck_users_not_merged_into_self
        CHECK (merged_into_user_id IS NULL OR merged_into_user_id <> user_id);

CREATE INDEX ix_users_merged_into_user_id
    ON users (merged_into_user_id) WHERE merged_into_user_id IS NOT NULL;

CREATE TABLE user_identities (
    user_identity_id BIGSERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    issuer VARCHAR(255) NOT NULL,
    subject VARCHAR(255) NOT NULL,
    email VARCHAR(320),
    email_verified_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ,
    CONSTRAINT uq_user_identities_issuer_subject UNIQUE (issuer, subject),
    CONSTRAINT ck_user_identities_issuer_not_blank CHECK (btrim(issuer) <> ''),
    CONSTRAINT ck_user_identities_subject_not_blank CHECK (btrim(subject) <> '')
);

CREATE INDEX ix_user_identities_user_id ON user_identities (user_id);

ALTER TABLE user_profiles
    ADD COLUMN username VARCHAR(40),
    ADD COLUMN broad_location VARCHAR(100),
    ADD COLUMN bio VARCHAR(280),
    ADD CONSTRAINT ck_user_profiles_username_not_blank CHECK (username IS NULL OR btrim(username) <> ''),
    ADD CONSTRAINT ck_user_profiles_broad_location_not_blank CHECK (broad_location IS NULL OR btrim(broad_location) <> ''),
    ADD CONSTRAINT ck_user_profiles_bio_not_blank CHECK (bio IS NULL OR btrim(bio) <> '');

CREATE UNIQUE INDEX uq_user_profiles_username_ci
    ON user_profiles (lower(username)) WHERE username IS NOT NULL;

ALTER TABLE matchday_tips
    ADD COLUMN author_user_id INTEGER REFERENCES users(user_id) ON DELETE SET NULL;

CREATE INDEX ix_matchday_tips_author_user_id
    ON matchday_tips (author_user_id) WHERE author_user_id IS NOT NULL;

CREATE TABLE account_merge_audits (
    account_merge_audit_id BIGSERIAL PRIMARY KEY,
    source_user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE RESTRICT,
    target_user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE RESTRICT,
    merge_source VARCHAR(40) NOT NULL,
    reason VARCHAR(255),
    merged_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_account_merge_audits_source_user UNIQUE (source_user_id),
    CONSTRAINT ck_account_merge_audits_distinct_users CHECK (source_user_id <> target_user_id),
    CONSTRAINT ck_account_merge_audits_source_not_blank CHECK (btrim(merge_source) <> '')
);

CREATE INDEX ix_account_merge_audits_target_user_id
    ON account_merge_audits (target_user_id);

COMMIT;
