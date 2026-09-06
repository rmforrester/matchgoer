BEGIN;

SET LOCAL lock_timeout = '15s';

-- Widen the existing bounded string without a USING cast or content rewrite.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'pre_match_spots'
          AND column_name = 'supporting_line' AND data_type = 'character varying'
          AND character_maximum_length IN (180, 255) AND is_nullable = 'NO'
    ) THEN
        RAISE EXCEPTION 'Unexpected pre_match_spots.supporting_line definition';
    END IF;
END $$;

ALTER TABLE public.pre_match_spots
    ALTER COLUMN supporting_line TYPE VARCHAR(255);

COMMIT;
