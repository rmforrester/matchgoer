BEGIN;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM venue_guide_facts WHERE club_venue_id IS NOT NULL) THEN
        RAISE EXCEPTION 'Rollback refused: CLUB_VENUE-owned guide facts exist';
    END IF;
END $$;

DROP INDEX IF EXISTS ix_venue_guide_facts_club_venue_status;
ALTER TABLE venue_guide_facts DROP CONSTRAINT IF EXISTS ck_venue_guide_facts_exactly_one_owner;
ALTER TABLE venue_guide_facts DROP CONSTRAINT IF EXISTS fk_venue_guide_facts_club_venue;
ALTER TABLE venue_guide_facts DROP COLUMN IF EXISTS club_venue_id;
ALTER TABLE venue_guide_facts ALTER COLUMN venue_id SET NOT NULL;

DROP TABLE IF EXISTS pre_match_spot_evidence;
DROP TABLE IF EXISTS pre_match_spots;
DROP TABLE IF EXISTS club_venues;

COMMIT;
