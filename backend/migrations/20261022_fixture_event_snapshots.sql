BEGIN;
CREATE TABLE fixture_event_snapshots (
 fixture_id integer PRIMARY KEY REFERENCES fixtures(fixture_id) ON DELETE CASCADE,
 payload json NOT NULL,
 source_sha256 varchar(64) NOT NULL,
 fetched_at timestamptz NOT NULL
);
COMMIT;
