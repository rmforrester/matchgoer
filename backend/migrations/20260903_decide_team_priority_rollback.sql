BEGIN;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM decision_facts WHERE subject_type = 'TEAM') THEN
        RAISE EXCEPTION 'Cannot roll back DECIDE TEAM support while TEAM facts exist';
    END IF;
END $$;

DROP INDEX uq_decision_facts_team_attribute;
ALTER TABLE decision_facts
    DROP CONSTRAINT ck_decision_facts_lead_priority,
    DROP CONSTRAINT ck_decision_facts_subject_type,
    DROP CONSTRAINT ck_decision_facts_subject_shape,
    DROP CONSTRAINT ck_decision_facts_attribute_subject,
    DROP COLUMN lead_priority,
    DROP COLUMN team_id;

ALTER TABLE decision_facts
    ADD CONSTRAINT ck_decision_facts_subject_type CHECK (subject_type IN ('TEAM_PAIR', 'VENUE')),
    ADD CONSTRAINT ck_decision_facts_subject_shape CHECK (
        (subject_type = 'TEAM_PAIR' AND team_a_id IS NOT NULL AND team_b_id IS NOT NULL AND team_a_id < team_b_id AND venue_id IS NULL)
        OR (subject_type = 'VENUE' AND team_a_id IS NULL AND team_b_id IS NULL AND venue_id IS NOT NULL)
    ),
    ADD CONSTRAINT ck_decision_facts_attribute_subject CHECK (
        (subject_type = 'TEAM_PAIR' AND attribute_key = 'SIGNIFICANT_RIVALRY')
        OR (subject_type = 'VENUE' AND attribute_key IN ('FOOTBALL_LANDMARK', 'UNIQUE_SETTING', 'CLASSIC_GROUND'))
    );

COMMIT;
