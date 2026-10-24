-- Export snapshots first if retaining enrichment evidence is required.
-- Does not modify fixtures, supporter history or canonical identities.
BEGIN;
DROP TABLE fixture_event_snapshots;
COMMIT;
