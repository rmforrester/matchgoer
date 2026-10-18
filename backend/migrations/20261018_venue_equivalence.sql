BEGIN;
ALTER TABLE venues ADD COLUMN IF NOT EXISTS canonical_venue_id integer;
ALTER TABLE venues ADD COLUMN IF NOT EXISTS equivalence_source text;
DO $$ BEGIN
 IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='fk_venue_canonical' AND conrelid='venues'::regclass) THEN
  ALTER TABLE venues ADD CONSTRAINT fk_venue_canonical FOREIGN KEY(canonical_venue_id) REFERENCES venues(venue_id) ON DELETE RESTRICT;
  ALTER TABLE venues ADD CONSTRAINT ck_venue_not_self CHECK(canonical_venue_id IS NULL OR canonical_venue_id <> venue_id);
  ALTER TABLE venues ADD CONSTRAINT ck_venue_equivalence_source CHECK((canonical_venue_id IS NULL AND equivalence_source IS NULL) OR (canonical_venue_id IS NOT NULL AND equivalence_source IS NOT NULL AND length(trim(equivalence_source)) > 0));
 END IF;
END $$;
CREATE INDEX IF NOT EXISTS ix_venues_canonical_venue_id ON venues(canonical_venue_id);
CREATE OR REPLACE FUNCTION guard_venue_equivalence() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 -- Serialise graph edits, including edits of different source/target rows.
 PERFORM pg_advisory_xact_lock(18262, 0);
 IF OLD.canonical_venue_id IS NOT NULL AND NEW.canonical_venue_id IS DISTINCT FROM OLD.canonical_venue_id THEN
  RAISE EXCEPTION 'Existing ground equivalence must be reviewed before reassignment';
 END IF;
 IF NEW.canonical_venue_id IS NOT NULL THEN
  IF EXISTS (SELECT 1 FROM venues WHERE venue_id=NEW.canonical_venue_id AND canonical_venue_id IS NOT NULL)
     OR EXISTS (SELECT 1 FROM venues WHERE canonical_venue_id=NEW.venue_id) THEN
   RAISE EXCEPTION 'Ground equivalence must point directly to a root';
  END IF;
 END IF;
 RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS venue_equivalence_guard ON venues;
CREATE TRIGGER venue_equivalence_guard BEFORE INSERT OR UPDATE OF canonical_venue_id ON venues FOR EACH ROW EXECUTE FUNCTION guard_venue_equivalence();
-- Preserve every existing photo guard; compare fixture physical identity only.
CREATE OR REPLACE FUNCTION terrace_photo_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE attendance venue_visits%ROWTYPE; active_count INTEGER;
BEGIN
 IF TG_OP='INSERT' AND NEW.status<>'PENDING' THEN
  RAISE EXCEPTION 'New photos must be pending';
 END IF;
 IF NEW.display_key !~ '^photos/[0-9a-f]{32}/display[.]jpg$'
  OR NEW.thumbnail_key !~ '^photos/[0-9a-f]{32}/thumbnail[.]jpg$'
  OR split_part(NEW.display_key,'/',2)<>split_part(NEW.thumbnail_key,'/',2)
  OR NEW.source_sha256 !~ '^[0-9a-f]{64}$'
  OR NEW.submission_key !~ '^[0-9a-f-]{36}$'
  OR NEW.consent_version<>'terraces-public-v1' THEN
  RAISE EXCEPTION 'Invalid private photo reservation';
 END IF;
 IF TG_OP='UPDATE' THEN
  IF ROW(NEW.owner_user_id,NEW.venue_id,NEW.fixture_id,NEW.display_key,NEW.thumbnail_key,NEW.source_sha256,NEW.submission_key,NEW.consent_version)
   IS DISTINCT FROM ROW(OLD.owner_user_id,OLD.venue_id,OLD.fixture_id,OLD.display_key,OLD.thumbnail_key,OLD.source_sha256,OLD.submission_key,OLD.consent_version) THEN
   RAISE EXCEPTION 'Photo ownership, context and object keys are immutable';
  END IF;
  IF NEW.visit_id IS DISTINCT FROM OLD.visit_id AND NEW.status<>'REMOVED' THEN
   RAISE EXCEPTION 'Attendance relinking requires explicit review';
  END IF;
  IF OLD.status<>'PENDING' AND NEW.caption IS DISTINCT FROM OLD.caption THEN
   RAISE EXCEPTION 'Reviewed caption is immutable';
  END IF;
  IF NEW.status IS DISTINCT FROM OLD.status AND NOT (
   (OLD.status='PENDING' AND NEW.status IN ('APPROVED','REJECTED','REMOVED')) OR
   (OLD.status IN ('APPROVED','REJECTED') AND NEW.status='REMOVED')
  ) THEN RAISE EXCEPTION 'Invalid moderation transition'; END IF;
 END IF;
 IF NEW.status IN ('PENDING','APPROVED') THEN
  SELECT * INTO attendance FROM venue_visits WHERE visit_id=NEW.visit_id FOR UPDATE;
  IF NOT FOUND OR attendance.user_id<>NEW.owner_user_id OR attendance.venue_id<>NEW.venue_id
   OR attendance.fixture_id IS DISTINCT FROM NEW.fixture_id THEN
   RAISE EXCEPTION 'Photo context must match owned attendance';
  END IF;
  IF NOT EXISTS(SELECT 1 FROM users u JOIN user_identities i ON i.user_id=u.user_id
   WHERE u.user_id=NEW.owner_user_id AND u.account_status='registered' AND NOT u.is_anonymous
    AND u.merged_into_user_id IS NULL AND i.email_verified_at IS NOT NULL) THEN
   RAISE EXCEPTION 'Verified registered ownership is required';
  END IF;
  IF NEW.fixture_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM fixtures f JOIN venues fv ON fv.venue_id=f.venue_id JOIN venues pv ON pv.venue_id=NEW.venue_id WHERE f.fixture_id=NEW.fixture_id AND coalesce(fv.canonical_venue_id,fv.venue_id)=coalesce(pv.canonical_venue_id,pv.venue_id)) THEN
   RAISE EXCEPTION 'Fixture/venue association is disputed';
  END IF;
  SELECT count(*) INTO active_count FROM terrace_photos
   WHERE visit_id=NEW.visit_id AND status IN ('PENDING','APPROVED') AND photo_id IS DISTINCT FROM NEW.photo_id;
  IF active_count>=3 THEN RAISE EXCEPTION 'Three-photo matchday limit exceeded'; END IF;
 END IF;
 RETURN NEW;
END $$;
COMMIT;
