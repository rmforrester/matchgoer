BEGIN;

ALTER TABLE pre_match_spots
    ALTER COLUMN supporting_line DROP NOT NULL,
    ALTER COLUMN maps_destination DROP NOT NULL,
    ADD COLUMN location_context varchar(255),
    DROP CONSTRAINT ck_pre_match_spots_line_not_blank,
    DROP CONSTRAINT ck_pre_match_spots_maps_not_blank,
    ADD CONSTRAINT ck_pre_match_spots_line_not_blank
        CHECK (supporting_line IS NULL OR btrim(supporting_line) <> ''),
    ADD CONSTRAINT ck_pre_match_spots_maps_not_blank
        CHECK (maps_destination IS NULL OR btrim(maps_destination) <> ''),
    ADD CONSTRAINT ck_pre_match_spots_location_context_not_blank
        CHECK (location_context IS NULL OR btrim(location_context) <> '');

COMMIT;
