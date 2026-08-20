BEGIN;

CREATE TABLE user_profiles (
    user_id INTEGER PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    display_name VARCHAR(40) NOT NULL CHECK (char_length(btrim(display_name)) BETWEEN 2 AND 40),
    supported_club VARCHAR(80),
    created_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE fixture_meeting_intents (
    user_id INTEGER NOT NULL,
    fixture_id INTEGER NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, fixture_id),
    FOREIGN KEY (user_id) REFERENCES user_profiles(user_id) ON DELETE CASCADE,
    FOREIGN KEY (user_id, fixture_id)
      REFERENCES interested_fixtures(user_id, fixture_id) ON DELETE CASCADE
);

CREATE TABLE match_board_posts (
    post_id BIGSERIAL PRIMARY KEY,
    fixture_id INTEGER NOT NULL REFERENCES fixtures(fixture_id) ON DELETE CASCADE,
    author_user_id INTEGER NOT NULL REFERENCES user_profiles(user_id) ON DELETE RESTRICT,
    parent_post_id BIGINT REFERENCES match_board_posts(post_id) ON DELETE RESTRICT,
    body VARCHAR(500) NOT NULL CHECK (char_length(btrim(body)) BETWEEN 1 AND 500),
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP,
    deleted_at TIMESTAMP
);
CREATE INDEX ix_match_board_posts_fixture_created ON match_board_posts(fixture_id, created_at, post_id);
CREATE INDEX ix_match_board_posts_parent ON match_board_posts(parent_post_id);

CREATE TABLE match_board_reports (
    report_id BIGSERIAL PRIMARY KEY,
    reporter_user_id INTEGER NOT NULL REFERENCES user_profiles(user_id) ON DELETE CASCADE,
    post_id BIGINT NOT NULL REFERENCES match_board_posts(post_id) ON DELETE CASCADE,
    reason VARCHAR(30) NOT NULL CHECK (reason IN ('harassment','spam','unsafe_meetup','offensive','other')),
    status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','reviewed','dismissed')),
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    UNIQUE (reporter_user_id, post_id)
);

CREATE TABLE social_events (
    event_id BIGSERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(user_id) ON DELETE SET NULL,
    fixture_id INTEGER NOT NULL REFERENCES fixtures(fixture_id) ON DELETE CASCADE,
    event_type VARCHAR(40) NOT NULL CHECK (event_type IN ('fixture_view','interested_added','interested_removed','meeting_enabled','meeting_disabled','board_view')),
    created_at TIMESTAMP NOT NULL DEFAULT now()
);
CREATE INDEX ix_social_events_fixture_type_created ON social_events(fixture_id, event_type, created_at);

COMMIT;
