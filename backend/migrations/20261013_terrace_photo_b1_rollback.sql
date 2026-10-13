BEGIN;
DO $$ BEGIN IF EXISTS(SELECT 1 FROM terrace_photos) OR EXISTS(SELECT 1 FROM terrace_photo_events) THEN RAISE EXCEPTION 'Photo data requires reviewed retention rollback'; END IF; END $$;
DROP INDEX ix_terrace_events_photo_type;
CREATE OR REPLACE FUNCTION terrace_photo_event() RETURNS trigger LANGUAGE plpgsql AS $$
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
COMMIT;
