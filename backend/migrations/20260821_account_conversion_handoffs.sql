BEGIN;

CREATE TABLE account_conversion_handoffs (
    token_digest VARCHAR(64) PRIMARY KEY,
    session_id VARCHAR NOT NULL REFERENCES anonymous_sessions(session_id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    consumed_at TIMESTAMPTZ,
    claimed_issuer VARCHAR,
    claimed_subject VARCHAR,
    CONSTRAINT ck_account_conversion_handoff_digest CHECK (token_digest ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_account_conversion_handoff_claim_pair CHECK ((claimed_issuer IS NULL) = (claimed_subject IS NULL)),
    CONSTRAINT ck_account_conversion_handoff_consumption CHECK ((consumed_at IS NULL) = (claimed_issuer IS NULL))
);

CREATE INDEX ix_account_conversion_handoffs_session ON account_conversion_handoffs (session_id);
CREATE INDEX ix_account_conversion_handoffs_user ON account_conversion_handoffs (user_id);
CREATE INDEX ix_account_conversion_handoffs_expires ON account_conversion_handoffs (expires_at);

COMMIT;
