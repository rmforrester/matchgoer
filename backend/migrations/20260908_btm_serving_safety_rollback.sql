BEGIN;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pre_match_spots WHERE supporting_line IS NULL OR maps_destination IS NULL) THEN
        RAISE EXCEPTION 'Cannot restore NOT NULL while remediated null values exist';
    END IF;
END $$;

ALTER TABLE pre_match_spots
    DROP CONSTRAINT ck_pre_match_spots_location_context_not_blank,
    DROP COLUMN location_context,
    DROP CONSTRAINT ck_pre_match_spots_line_not_blank,
    DROP CONSTRAINT ck_pre_match_spots_maps_not_blank,
    ALTER COLUMN supporting_line SET NOT NULL,
    ALTER COLUMN maps_destination SET NOT NULL,
    ADD CONSTRAINT ck_pre_match_spots_line_not_blank CHECK (btrim(supporting_line) <> ''),
    ADD CONSTRAINT ck_pre_match_spots_maps_not_blank CHECK (btrim(maps_destination) <> '');

COMMIT;
