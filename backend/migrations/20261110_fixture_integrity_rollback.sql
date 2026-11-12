BEGIN;
-- Export receipts first. Never roll readers back while active protections exist.
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM fixture_venue_verifications WHERE state IN ('OFFICIAL_VERIFIED','DISPUTED','UNRESOLVED'))
 OR EXISTS(SELECT 1 FROM fixture_schedule_integrity WHERE schedule_hold OR superseded_by IS NOT NULL
   OR evidence::jsonb ? 'official_schedule') THEN
  RAISE EXCEPTION 'ACTIVE_INTEGRITY_PROTECTION_REQUIRES_REVIEW';
 END IF;
END $$;
DROP TRIGGER fixture_verified_venue_guard ON fixtures;
DROP FUNCTION protect_verified_fixture_venue();
DROP TABLE fixture_venue_verifications;
DROP TABLE fixture_schedule_integrity;
DROP TABLE fixture_integrity_runs;
DROP INDEX IF EXISTS fixture_integrity_home_date;
DROP INDEX IF EXISTS fixture_integrity_away_date;
COMMIT;
