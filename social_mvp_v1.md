# Terrace Talk Social MVP v1

> **Historical experiment note — superseded as canonical documentation on 14 August 2026.** See [`docs/identity-and-social.md`](docs/identity-and-social.md), [`docs/architecture.md`](docs/architecture.md), and [`docs/mvp.md`](docs/mvp.md).

## Experiment measurement

Directly stored events in `social_events`: fixture page views, Match Board views,
Interested add/remove actions, and Find-a-mate enable/disable actions.

Transactionally stored and therefore derived without duplicate analytics rows:

- posts and replies created: `match_board_posts.parent_post_id`;
- unique board participants: distinct `author_user_id` by fixture;
- fixtures with posts: fixtures with at least one non-reply post;
- fixtures with 2+ participants: distinct post/reply authors by fixture;
- fixtures with 2+ users looking for a mate: grouped `fixture_meeting_intents`;
- profile creation: `user_profiles.created_at`.

Primary metric: among fixtures with at least one post, the percentage with at
least two distinct post/reply authors.

Secondary metric: among users with an Interested row, the percentage who have
either a meeting-intent row for that fixture or authored a post/reply on its
board.

Posting is limited to one post or reply per user every 15 seconds. Boards use
the stored kickoff instant and close for writes on the following UTC calendar
day; historical content remains readable.

The migration rollback is `backend/migrations/20260813_social_mvp_v1_rollback.sql`.

## Approved future account architecture

`users.user_id` remains the permanent owner identity. Registration will convert
the current anonymous user instead of creating an unrelated user, preserving
Interested fixtures, My Stadiums, reviews, profile data, and social activity.
Authentication is intentionally not implemented yet. The preferred future MVP
is managed passwordless email and/or OAuth rather than custom password storage.
