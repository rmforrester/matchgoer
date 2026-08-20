-- Phase 5B fixture datetime contract migration.
-- Existing values were written from offset-aware provider timestamps into a
-- timestamp-without-time-zone column. PostgreSQL interpreted them in the
-- database session timezone. This conversion preserves the same absolute
-- instant already reconstructed by /nearby before Phase 5B.
--
-- Preflight before applying:
--   SHOW TIMEZONE;
--   SELECT fixture_id, fixture_date,
--          fixture_date AT TIME ZONE current_setting('TIMEZONE') AS proposed_utc
--   FROM fixtures ORDER BY fixture_date DESC LIMIT 20;
--
-- Apply only after confirming the timezone is the one used during ingestion.

BEGIN;

ALTER TABLE fixtures
    ALTER COLUMN fixture_date TYPE TIMESTAMPTZ
    USING fixture_date AT TIME ZONE current_setting('TIMEZONE');

COMMIT;
