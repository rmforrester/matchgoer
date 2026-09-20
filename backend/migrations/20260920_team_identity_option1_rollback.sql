BEGIN;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM team_identity_overrides) THEN
        RAISE EXCEPTION 'cannot roll back team identity Option 1 while overrides exist';
    END IF;
    IF EXISTS (SELECT 1 FROM teams WHERE team_id < 0) THEN
        RAISE EXCEPTION 'cannot roll back team identity Option 1 while internal teams exist';
    END IF;
END
$$;

DROP TABLE team_identity_overrides;
DROP SEQUENCE matchgoer_team_id_seq;

COMMIT;
