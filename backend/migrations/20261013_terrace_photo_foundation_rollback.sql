-- Local rollback test only. Hosted rollback requires explicit data/asset review.
BEGIN;
DROP TRIGGER terrace_attendance_removed ON venue_visits;
DROP TABLE terrace_photo_events;
DROP TABLE terrace_photos;
DROP FUNCTION terrace_attendance_removed();
DROP FUNCTION terrace_photo_event();
DROP FUNCTION terrace_photo_guard();
COMMIT;
