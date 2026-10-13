BEGIN;
CREATE TABLE terrace_photos (
 photo_id BIGSERIAL PRIMARY KEY,
 owner_user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
 visit_id BIGINT REFERENCES venue_visits(visit_id) ON DELETE SET NULL,
 venue_id INTEGER NOT NULL REFERENCES venues(venue_id),
 fixture_id INTEGER REFERENCES fixtures(fixture_id),
 caption VARCHAR(200), submission_key VARCHAR(36) NOT NULL,
 source_sha256 VARCHAR(64) NOT NULL, original_bytes INTEGER NOT NULL,
 display_key VARCHAR(100) NOT NULL UNIQUE, thumbnail_key VARCHAR(100) NOT NULL UNIQUE,
 width INTEGER NOT NULL, height INTEGER NOT NULL,
 thumbnail_width INTEGER NOT NULL, thumbnail_height INTEGER NOT NULL,
 content_type VARCHAR(40) NOT NULL DEFAULT 'image/jpeg',
 status VARCHAR(16) NOT NULL DEFAULT 'PENDING', consent_version VARCHAR(60) NOT NULL,
 submitted_at TIMESTAMPTZ NOT NULL DEFAULT now(), approved_at TIMESTAMPTZ,
 published_at TIMESTAMPTZ, rejected_at TIMESTAMPTZ, removed_at TIMESTAMPTZ,
 dispute_reason VARCHAR(500), storage_deleted_at TIMESTAMPTZ,
 CONSTRAINT uq_terrace_submission UNIQUE(owner_user_id,submission_key),
 CONSTRAINT uq_terrace_visit_image UNIQUE(visit_id,source_sha256),
 CONSTRAINT ck_terrace_status CHECK(status IN ('PENDING','APPROVED','REJECTED','REMOVED')),
 CONSTRAINT ck_terrace_caption CHECK(char_length(caption)<=200),
 CONSTRAINT ck_terrace_bytes CHECK(original_bytes BETWEEN 1 AND 10000000),
 CONSTRAINT ck_terrace_dimensions CHECK(width BETWEEN 1 AND 1600 AND height BETWEEN 1 AND 1600 AND thumbnail_width BETWEEN 1 AND 400 AND thumbnail_height BETWEEN 1 AND 400),
 CONSTRAINT ck_terrace_mime CHECK(content_type='image/jpeg'),
 CONSTRAINT ck_terrace_live_visit CHECK(status NOT IN ('PENDING','APPROVED') OR visit_id IS NOT NULL),
 CONSTRAINT ck_terrace_publication CHECK(published_at IS NULL OR (status='APPROVED' AND approved_at IS NOT NULL)),
 CONSTRAINT ck_terrace_rejection CHECK(status<>'REJECTED' OR rejected_at IS NOT NULL),
 CONSTRAINT ck_terrace_approval CHECK(status<>'APPROVED' OR approved_at IS NOT NULL),
 CONSTRAINT ck_terrace_removal CHECK(status<>'REMOVED' OR removed_at IS NOT NULL),
 CONSTRAINT ck_terrace_dispute CHECK(dispute_reason IS NULL OR char_length(btrim(dispute_reason))>0)
);
CREATE INDEX ix_terrace_publication ON terrace_photos(status,published_at,photo_id);
CREATE INDEX ix_terrace_venue ON terrace_photos(venue_id,status,published_at,photo_id);
CREATE INDEX ix_terrace_visit ON terrace_photos(visit_id);
CREATE TABLE terrace_photo_events (
 event_id BIGSERIAL PRIMARY KEY,
 photo_id BIGINT REFERENCES terrace_photos(photo_id) ON DELETE SET NULL,
 actor_user_id INTEGER REFERENCES users(user_id) ON DELETE SET NULL,
 event_type VARCHAR(40) NOT NULL,
 payload JSON NOT NULL DEFAULT '{}', created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 completed_at TIMESTAMPTZ
);

CREATE FUNCTION terrace_photo_guard() RETURNS trigger LANGUAGE plpgsql AS $$
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
  IF NEW.fixture_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM fixtures WHERE fixture_id=NEW.fixture_id AND venue_id=NEW.venue_id) THEN
   RAISE EXCEPTION 'Fixture/venue association is disputed';
  END IF;
  SELECT count(*) INTO active_count FROM terrace_photos
   WHERE visit_id=NEW.visit_id AND status IN ('PENDING','APPROVED') AND photo_id IS DISTINCT FROM NEW.photo_id;
  IF active_count>=3 THEN RAISE EXCEPTION 'Three-photo matchday limit exceeded'; END IF;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER terrace_photo_guard BEFORE INSERT OR UPDATE ON terrace_photos
 FOR EACH ROW EXECUTE FUNCTION terrace_photo_guard();

CREATE FUNCTION terrace_photo_event() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='DELETE' THEN
  INSERT INTO terrace_photo_events(photo_id,event_type,payload)
   VALUES(OLD.photo_id,'STORAGE_DELETE_REQUIRED',json_build_object('display_key',OLD.display_key,'thumbnail_key',OLD.thumbnail_key));
  RETURN OLD;
 END IF;
 IF TG_OP='INSERT' OR NEW.status IS DISTINCT FROM OLD.status THEN
  INSERT INTO terrace_photo_events(photo_id,event_type,payload)
   VALUES(NEW.photo_id,NEW.status,json_build_object('status',NEW.status));
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER terrace_photo_event AFTER INSERT OR UPDATE ON terrace_photos
 FOR EACH ROW EXECUTE FUNCTION terrace_photo_event();
CREATE TRIGGER terrace_photo_delete_event BEFORE DELETE ON terrace_photos
 FOR EACH ROW EXECUTE FUNCTION terrace_photo_event();

CREATE FUNCTION terrace_attendance_removed() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='DELETE' OR ROW(NEW.user_id,NEW.venue_id,NEW.fixture_id) IS DISTINCT FROM ROW(OLD.user_id,OLD.venue_id,OLD.fixture_id) THEN
  UPDATE terrace_photos SET status='REMOVED', removed_at=COALESCE(removed_at,now()),
   published_at=NULL, visit_id=NULL WHERE visit_id=OLD.visit_id;
 END IF;
 IF TG_OP='DELETE' THEN RETURN OLD; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER terrace_attendance_removed BEFORE DELETE OR UPDATE OF user_id,venue_id,fixture_id ON venue_visits
 FOR EACH ROW EXECUTE FUNCTION terrace_attendance_removed();
COMMIT;
