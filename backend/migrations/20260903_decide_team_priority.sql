BEGIN;

ALTER TABLE decision_facts
    ADD COLUMN team_id INTEGER REFERENCES teams(team_id) ON DELETE RESTRICT,
    ADD COLUMN lead_priority VARCHAR(10) NOT NULL DEFAULT 'NORMAL';

ALTER TABLE decision_facts
    DROP CONSTRAINT ck_decision_facts_subject_type,
    DROP CONSTRAINT ck_decision_facts_subject_shape,
    DROP CONSTRAINT ck_decision_facts_attribute_subject;

ALTER TABLE decision_facts
    ADD CONSTRAINT ck_decision_facts_subject_type CHECK (subject_type IN ('TEAM_PAIR', 'VENUE', 'TEAM')),
    ADD CONSTRAINT ck_decision_facts_subject_shape CHECK (
        (subject_type = 'TEAM_PAIR' AND team_a_id IS NOT NULL AND team_b_id IS NOT NULL
         AND team_a_id < team_b_id AND venue_id IS NULL AND team_id IS NULL)
        OR (subject_type = 'VENUE' AND team_a_id IS NULL AND team_b_id IS NULL
            AND venue_id IS NOT NULL AND team_id IS NULL)
        OR (subject_type = 'TEAM' AND team_a_id IS NULL AND team_b_id IS NULL
            AND venue_id IS NULL AND team_id IS NOT NULL)
    ),
    ADD CONSTRAINT ck_decision_facts_attribute_subject CHECK (
        (subject_type = 'TEAM_PAIR' AND attribute_key = 'SIGNIFICANT_RIVALRY')
        OR (subject_type = 'VENUE' AND attribute_key IN ('FOOTBALL_LANDMARK', 'UNIQUE_SETTING', 'CLASSIC_GROUND'))
        OR (subject_type = 'TEAM' AND attribute_key = 'EXCEPTIONAL_SUPPORT')
    ),
    ADD CONSTRAINT ck_decision_facts_lead_priority CHECK (lead_priority IN ('LEAD', 'NORMAL'));

CREATE UNIQUE INDEX uq_decision_facts_team_attribute
    ON decision_facts (team_id, attribute_key)
    WHERE subject_type = 'TEAM';

COMMIT;
