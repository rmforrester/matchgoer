BEGIN;

ALTER TABLE ticket_sources
    ADD COLUMN team_id INTEGER REFERENCES teams(team_id) ON DELETE RESTRICT;

ALTER TABLE ticket_sources
    ALTER COLUMN club_venue_id DROP NOT NULL;

ALTER TABLE ticket_sources
    ADD CONSTRAINT ck_ticket_sources_exactly_one_owner
    CHECK (num_nonnulls(team_id, club_venue_id) = 1);

CREATE UNIQUE INDEX uq_ticket_sources_team_url
    ON ticket_sources (team_id, source_url)
    WHERE team_id IS NOT NULL AND source_url IS NOT NULL;

CREATE UNIQUE INDEX uq_ticket_sources_team_active_primary
    ON ticket_sources (team_id)
    WHERE team_id IS NOT NULL
      AND source_role = 'PRIMARY'
      AND operational_status = 'ACTIVE';

CREATE INDEX ix_ticket_sources_team ON ticket_sources (team_id);

COMMIT;
