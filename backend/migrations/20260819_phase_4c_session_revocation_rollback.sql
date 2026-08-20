BEGIN;

DROP INDEX IF EXISTS ix_anonymous_sessions_active_user;
ALTER TABLE anonymous_sessions DROP COLUMN IF EXISTS revoked_at;

COMMIT;
