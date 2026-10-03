BEGIN;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM ticket_sources WHERE team_id IS NOT NULL) THEN
        RAISE EXCEPTION 'cannot roll back team-owned ticket sources while team-owned rows exist';
    END IF;
END $$;

DROP INDEX IF EXISTS ix_ticket_sources_team;
DROP INDEX IF EXISTS uq_ticket_sources_team_active_primary;
DROP INDEX IF EXISTS uq_ticket_sources_team_url;
ALTER TABLE ticket_sources DROP CONSTRAINT IF EXISTS ck_ticket_sources_exactly_one_owner;
ALTER TABLE ticket_sources ALTER COLUMN club_venue_id SET NOT NULL;
ALTER TABLE ticket_sources DROP COLUMN team_id;

COMMIT;
