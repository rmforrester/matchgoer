BEGIN;

DROP TABLE IF EXISTS account_merge_audits;
DROP INDEX IF EXISTS ix_matchday_tips_author_user_id;
ALTER TABLE matchday_tips DROP COLUMN IF EXISTS author_user_id;
DROP INDEX IF EXISTS uq_user_profiles_username_ci;
ALTER TABLE user_profiles
    DROP COLUMN IF EXISTS bio,
    DROP COLUMN IF EXISTS broad_location,
    DROP COLUMN IF EXISTS username;
DROP TABLE IF EXISTS user_identities;
DROP INDEX IF EXISTS ix_users_merged_into_user_id;
ALTER TABLE users
    DROP COLUMN IF EXISTS merged_into_user_id,
    DROP COLUMN IF EXISTS registered_at,
    DROP COLUMN IF EXISTS account_status;

COMMIT;
