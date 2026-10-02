BEGIN;
LOCK TABLE public.pre_match_spots IN ACCESS EXCLUSIVE MODE;
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM public.pre_match_spots
    WHERE latitude IS NOT NULL
      AND (maps_destination IS NULL OR maps_destination !~ '^[[:space:]]*[+-]?([0-9]+([.][0-9]+)?|[.][0-9]+)[[:space:]]*,[[:space:]]*[+-]?([0-9]+([.][0-9]+)?|[.][0-9]+)[[:space:]]*$')
  ) THEN
    RAISE EXCEPTION 'Rollback would discard coordinate fallback after named-destination conversion';
  END IF;
END $$;
ALTER TABLE public.pre_match_spots
  DROP CONSTRAINT ck_pre_match_spots_coordinate_pair,
  DROP CONSTRAINT ck_pre_match_spots_latitude_range,
  DROP CONSTRAINT ck_pre_match_spots_longitude_range,
  DROP COLUMN latitude,
  DROP COLUMN longitude;
COMMIT;
