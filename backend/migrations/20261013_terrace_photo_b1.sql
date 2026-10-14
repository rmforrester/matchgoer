BEGIN;
CREATE OR REPLACE FUNCTION terrace_photo_event() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='DELETE' THEN
  INSERT INTO terrace_photo_events(photo_id,event_type,payload)
   VALUES(OLD.photo_id,'STORAGE_DELETE_REQUIRED',json_build_object('display_key',OLD.display_key,'thumbnail_key',OLD.thumbnail_key,'legal_hold',OLD.dispute_reason IS NOT NULL));
  RETURN OLD;
 END IF;
 IF TG_OP='INSERT' OR NEW.status IS DISTINCT FROM OLD.status THEN
  INSERT INTO terrace_photo_events(photo_id,event_type,payload)
   VALUES(NEW.photo_id,NEW.status,json_build_object('status',NEW.status));
 END IF;
 RETURN NEW;
END $$;
CREATE INDEX ix_terrace_events_photo_type ON terrace_photo_events(photo_id,event_type);
COMMIT;
