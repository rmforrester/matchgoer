BEGIN;

CREATE TABLE venue_visits (
    visit_id BIGSERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(user_id),
    venue_id INTEGER NOT NULL REFERENCES venues(venue_id),
    fixture_id INTEGER REFERENCES fixtures(fixture_id),
    visit_date DATE,
    source VARCHAR(40) NOT NULL DEFAULT 'manual',
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    CONSTRAINT ck_venue_visits_source_not_blank CHECK (btrim(source) <> '')
);

CREATE UNIQUE INDEX uq_venue_visits_user_fixture
    ON venue_visits (user_id, fixture_id)
    WHERE fixture_id IS NOT NULL;

CREATE UNIQUE INDEX uq_venue_visits_manual_dated
    ON venue_visits (user_id, venue_id, visit_date)
    WHERE fixture_id IS NULL AND visit_date IS NOT NULL;

CREATE UNIQUE INDEX uq_venue_visits_manual_undated
    ON venue_visits (user_id, venue_id)
    WHERE fixture_id IS NULL AND visit_date IS NULL;

CREATE INDEX ix_venue_visits_user_venue
    ON venue_visits (user_id, venue_id);

CREATE INDEX ix_venue_visits_fixture
    ON venue_visits (fixture_id);

CREATE INDEX ix_venue_visits_user_visit_date
    ON venue_visits (user_id, visit_date);

COMMIT;
