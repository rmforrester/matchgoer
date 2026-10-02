BEGIN;
LOCK TABLE public.pre_match_spots IN SHARE ROW EXCLUSIVE MODE;

ALTER TABLE public.pre_match_spots
  ADD COLUMN latitude DOUBLE PRECISION,
  ADD COLUMN longitude DOUBLE PRECISION,
  ADD CONSTRAINT ck_pre_match_spots_coordinate_pair
    CHECK ((latitude IS NULL) = (longitude IS NULL)) NOT VALID,
  ADD CONSTRAINT ck_pre_match_spots_latitude_range
    CHECK (latitude IS NULL OR latitude BETWEEN -90 AND 90) NOT VALID,
  ADD CONSTRAINT ck_pre_match_spots_longitude_range
    CHECK (longitude IS NULL OR longitude BETWEEN -180 AND 180) NOT VALID;

UPDATE public.pre_match_spots
SET latitude = btrim(split_part(maps_destination, ',', 1))::DOUBLE PRECISION,
    longitude = btrim(split_part(maps_destination, ',', 2))::DOUBLE PRECISION
WHERE maps_destination ~ '^[[:space:]]*[+-]?([0-9]+([.][0-9]+)?|[.][0-9]+)[[:space:]]*,[[:space:]]*[+-]?([0-9]+([.][0-9]+)?|[.][0-9]+)[[:space:]]*$'
  AND btrim(split_part(maps_destination, ',', 1))::DOUBLE PRECISION BETWEEN -90 AND 90
  AND btrim(split_part(maps_destination, ',', 2))::DOUBLE PRECISION BETWEEN -180 AND 180;

ALTER TABLE public.pre_match_spots VALIDATE CONSTRAINT ck_pre_match_spots_coordinate_pair;
ALTER TABLE public.pre_match_spots VALIDATE CONSTRAINT ck_pre_match_spots_latitude_range;
ALTER TABLE public.pre_match_spots VALIDATE CONSTRAINT ck_pre_match_spots_longitude_range;
COMMIT;
