-- Emergency rollback only. This restores the previous representation in the
-- active database timezone; it does not restore the unsafe application contract.
BEGIN;

ALTER TABLE fixtures
    ALTER COLUMN fixture_date TYPE TIMESTAMP WITHOUT TIME ZONE
    USING fixture_date AT TIME ZONE current_setting('TIMEZONE');

COMMIT;
