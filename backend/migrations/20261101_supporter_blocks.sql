-- Local candidate only. Requires separately approved hosted migration.
BEGIN;
CREATE TABLE supporter_blocks (
    block_id serial PRIMARY KEY,
    user_id integer NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    blocked_user_id integer NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    created_at timestamptz NOT NULL,
    CONSTRAINT uq_supporter_block UNIQUE(user_id, blocked_user_id),
    CONSTRAINT ck_supporter_block_self CHECK(user_id <> blocked_user_id)
);
COMMIT;
