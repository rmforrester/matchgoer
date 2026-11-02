-- LOCAL PREPARATION ONLY: hosted application requires separate release approval.
BEGIN;
CREATE TABLE account_deletion_requests (
    request_id varchar(36) PRIMARY KEY,
    user_id integer REFERENCES users(user_id) ON DELETE SET NULL,
    request_type varchar(16) NOT NULL CHECK (request_type IN ('account','guest_history')),
    record_scope json NOT NULL CHECK (json_typeof(record_scope) = 'object'),
    transfer_lineage json NOT NULL DEFAULT '[]' CHECK (json_typeof(transfer_lineage) = 'array'),
    status varchar(16) NOT NULL CHECK (status IN ('pending','processing','completed')),
    requested_at timestamptz NOT NULL,
    due_at timestamptz NOT NULL CHECK (due_at = requested_at + interval '168 hours'),
    apple_revocation varchar(16) NOT NULL DEFAULT 'pending' CHECK (apple_revocation IN ('pending','not_required','complete')),
    apple_revoked_at timestamptz,
    receipt_hash varchar(64) UNIQUE,
    completed_at timestamptz,
    confirmed_at timestamptz,
    CHECK ((status = 'completed') = (completed_at IS NOT NULL)),
    CHECK (confirmed_at IS NULL OR completed_at IS NOT NULL),
    CONSTRAINT ck_deletion_before_completion CHECK (status <> 'completed' OR apple_revocation IN ('not_required','complete'))
);
CREATE UNIQUE INDEX uq_account_deletion_open ON account_deletion_requests(user_id, request_type)
WHERE status IN ('pending','processing');
CREATE INDEX ix_account_deletion_due ON account_deletion_requests(due_at)
WHERE status IN ('pending','processing');
COMMIT;
