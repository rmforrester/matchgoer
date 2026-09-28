BEGIN;
DROP TABLE IF EXISTS fixture_ticket_availability;
DROP TABLE IF EXISTS ticket_availability_observations;
DROP FUNCTION IF EXISTS reject_ticket_observation_mutation();
DROP TABLE IF EXISTS ticket_source_checks;
DROP TABLE IF EXISTS ticket_refresh_runs;
DROP TABLE IF EXISTS ticket_source_legacy_facts;
DROP TABLE IF EXISTS ticket_sources;
COMMIT;
