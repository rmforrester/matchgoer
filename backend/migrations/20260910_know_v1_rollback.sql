BEGIN;

ALTER TABLE matchday_tips ALTER COLUMN status SET DEFAULT 'active';
DROP TABLE know_fact_evidence;
DROP TABLE know_facts;

COMMIT;
