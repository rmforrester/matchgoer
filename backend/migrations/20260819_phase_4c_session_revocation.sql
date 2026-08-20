BEGIN;

ALTER TABLE anonymous_sessions
    ADD COLUMN revoked_at TIMESTAMPTZ;

CREATE INDEX ix_anonymous_sessions_active_user
    ON anonymous_sessions (user_id)
    WHERE revoked_at IS NULL;

COMMIT;
