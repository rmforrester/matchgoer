BEGIN;

CREATE TABLE venue_names (
    venue_name_id BIGSERIAL PRIMARY KEY,
    venue_id INTEGER NOT NULL REFERENCES venues(venue_id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL CHECK (btrim(name) <> ''),
    normalized_name VARCHAR(255) NOT NULL CHECK (btrim(normalized_name) <> ''),
    name_type VARCHAR(20) NOT NULL CHECK (
        name_type IN ('current', 'historical', 'short', 'sponsored', 'provider')
    ),
    valid_from DATE,
    valid_to DATE,
    source VARCHAR(80),
    observed_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_venue_names_venue_normalized UNIQUE (venue_id, normalized_name),
    CONSTRAINT ck_venue_names_valid_range CHECK (
        valid_from IS NULL OR valid_to IS NULL OR valid_from <= valid_to
    )
);

CREATE UNIQUE INDEX uq_venue_names_one_current
    ON venue_names (venue_id)
    WHERE name_type = 'current';

CREATE INDEX ix_venue_names_normalized_name ON venue_names (normalized_name);

CREATE TABLE venue_provider_refs (
    venue_provider_ref_id BIGSERIAL PRIMARY KEY,
    venue_id INTEGER NOT NULL REFERENCES venues(venue_id) ON DELETE CASCADE,
    provider VARCHAR(40) NOT NULL CHECK (btrim(provider) <> ''),
    provider_venue_id INTEGER NOT NULL,
    valid_from DATE,
    valid_to DATE,
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    observed_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_venue_provider_refs_provider_id UNIQUE (provider, provider_venue_id),
    CONSTRAINT ck_venue_provider_refs_valid_range CHECK (
        valid_from IS NULL OR valid_to IS NULL OR valid_from <= valid_to
    )
);

CREATE UNIQUE INDEX uq_venue_provider_refs_one_primary
    ON venue_provider_refs (venue_id, provider)
    WHERE is_primary;

INSERT INTO venue_names (venue_id, name, normalized_name, name_type, source)
SELECT
    venue_id,
    name,
    lower(regexp_replace(btrim(name), '\s+', ' ', 'g')),
    'current',
    'legacy_backfill'
FROM venues
WHERE name IS NOT NULL AND btrim(name) <> '';

INSERT INTO venue_provider_refs (venue_id, provider, provider_venue_id, is_primary)
SELECT venue_id, 'api_football', provider_venue_id, TRUE
FROM venues
WHERE provider_venue_id IS NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM venues
        WHERE venue_id = 22820 AND provider_venue_id = 1506 AND name = 'Tele2 Arena'
    ) THEN
        RAISE EXCEPTION 'Reviewed Tele2 correction precondition failed';
    END IF;
END $$;

UPDATE venue_names
SET name_type = 'historical',
    valid_to = DATE '2024-12-31',
    source = 'reviewed_rename_2025'
WHERE venue_id = 22820 AND name_type = 'current';

INSERT INTO venue_names (
    venue_id, name, normalized_name, name_type, valid_from, source
)
VALUES (
    22820, '3Arena', '3arena', 'current', DATE '2025-01-01', 'reviewed_rename_2025'
);

UPDATE venues
SET name = '3Arena'
WHERE venue_id = 22820 AND provider_venue_id = 1506;

DO $$
BEGIN
    IF (SELECT count(*) FROM venue_names WHERE name_type = 'current')
       <> (SELECT count(*) FROM venues WHERE name IS NOT NULL AND btrim(name) <> '') THEN
        RAISE EXCEPTION 'Current venue-name backfill is incomplete';
    END IF;
    IF (SELECT count(*) FROM venue_provider_refs WHERE provider = 'api_football')
       <> (SELECT count(*) FROM venues WHERE provider_venue_id IS NOT NULL) THEN
        RAISE EXCEPTION 'Provider-reference backfill is incomplete';
    END IF;
END $$;

COMMIT;
