BEGIN;

SET LOCAL lock_timeout = '15s';
LOCK TABLE public.pre_match_spots IN ACCESS EXCLUSIVE MODE;

-- After Spain publication, narrowing must fail rather than truncate approved
-- text. Restore/remove that publication through a separately reviewed recovery
-- before attempting this rollback. Never use a truncating USING cast.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM public.pre_match_spots WHERE char_length(supporting_line) > 180) THEN
        RAISE EXCEPTION 'Rollback refused: supporting lines exceed 180 characters';
    END IF;
END $$;

ALTER TABLE public.pre_match_spots
    ALTER COLUMN supporting_line TYPE VARCHAR(180);

COMMIT;
