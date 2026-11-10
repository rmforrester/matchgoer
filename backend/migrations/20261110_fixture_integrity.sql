BEGIN;
CREATE TABLE fixture_venue_verifications (
 fixture_id integer PRIMARY KEY REFERENCES fixtures(fixture_id) ON DELETE RESTRICT,
 venue_id integer REFERENCES venues(venue_id) ON DELETE RESTRICT,
 identity json NOT NULL,
 state text NOT NULL CHECK (state IN ('OFFICIAL_VERIFIED','PROVIDER_ASSIGNED','UNRESOLVED','DISPUTED')),
 source_url text, evidence_sha256 text, actor text, verified_at timestamptz,
 provider_venue json, previous_provider_venue json, history json NOT NULL DEFAULT '[]',
 revision integer NOT NULL DEFAULT 1 CHECK (revision>0),
 CHECK (state<>'OFFICIAL_VERIFIED' OR (venue_id IS NOT NULL AND source_url LIKE 'https://%'
   AND length(evidence_sha256)=64 AND length(trim(actor))>0 AND verified_at IS NOT NULL))
);
CREATE TABLE fixture_schedule_integrity (
 fixture_id integer PRIMARY KEY REFERENCES fixtures(fixture_id) ON DELETE RESTRICT,
 identity json NOT NULL,
 state text NOT NULL CHECK(state IN ('CONFIRMED_ACTIVE','CONFIRMED_POSTPONED','CONFIRMED_RESCHEDULED','SUSPECTED_CONFLICT','RESOLVED_CONFLICT')),
 provider_observation json NOT NULL, observed_at timestamptz NOT NULL,
 effective_kickoff timestamptz NOT NULL, effective_status text NOT NULL,
 schedule_hold boolean NOT NULL DEFAULT false,
 superseded_by integer REFERENCES fixtures(fixture_id) ON DELETE RESTRICT,
 evidence json NOT NULL DEFAULT '{}', conflicts json NOT NULL DEFAULT '[]', history json NOT NULL DEFAULT '[]',
 revision integer NOT NULL DEFAULT 1 CHECK (revision>0), CHECK (superseded_by IS NULL OR superseded_by<>fixture_id)
);
CREATE TABLE fixture_integrity_runs (
 run_id text PRIMARY KEY, scheduled_for timestamptz NOT NULL, started_at timestamptz NOT NULL,
 completed_at timestamptz, state text NOT NULL CHECK(state IN ('RUNNING','COMPLETED','INCOMPLETE','FAILED')),
 source_sha text, requests_attempted integer NOT NULL DEFAULT 0, requests_completed integer NOT NULL DEFAULT 0,
 receipt json NOT NULL DEFAULT '{}', CHECK(requests_completed>=0 AND requests_attempted>=requests_completed)
);
CREATE INDEX fixture_integrity_runs_scheduled ON fixture_integrity_runs(scheduled_for DESC);
CREATE INDEX fixture_schedule_integrity_holds ON fixture_schedule_integrity(fixture_id) WHERE schedule_hold;
CREATE INDEX fixture_integrity_home_date ON fixtures(home_team_id,fixture_date);
CREATE INDEX fixture_integrity_away_date ON fixtures(away_team_id,fixture_date);
CREATE FUNCTION protect_verified_fixture_venue() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE verification fixture_venue_verifications%ROWTYPE;
BEGIN
 SELECT * INTO verification FROM fixture_venue_verifications WHERE fixture_id=NEW.fixture_id;
 IF FOUND AND verification.state='OFFICIAL_VERIFIED' THEN
  IF NEW.venue_id IS DISTINCT FROM verification.venue_id
    OR (verification.identity->>'home_team_id')::integer IS DISTINCT FROM NEW.home_team_id
    OR (verification.identity->>'away_team_id')::integer IS DISTINCT FROM NEW.away_team_id
    OR (verification.identity->>'league_id')::integer IS DISTINCT FROM NEW.league_id
    OR (verification.identity->>'season')::integer IS DISTINCT FROM NEW.season THEN
   RAISE EXCEPTION 'VERIFIED_FIXTURE_VENUE_CONFLICT' USING ERRCODE='23514';
  END IF;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER fixture_verified_venue_guard BEFORE UPDATE ON fixtures
 FOR EACH ROW EXECUTE FUNCTION protect_verified_fixture_venue();
COMMIT;
