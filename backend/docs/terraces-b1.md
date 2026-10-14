# From the Terraces B1: disabled backend contracts

Local implementation based on Phase A `3133163a963b9d9c5b80942ede037f41cc977008`. No frontend, public activation, scheduler, email notifications or storage policy changes.

## Configuration and activation

`TERRACES_BACKEND_ENABLED` defaults to false. Only an explicit server value `true` mounts `/terraces` routes. Before a separately approved activation, apply the B1 migration, verify the private bucket and storage permissions, validate the image worker on Railway-compatible Linux, and agree an operational cleanup cadence. Never expose `SUPABASE_SERVICE_ROLE_KEY` to the browser. `SUPABASE_URL` and that key are read only by the backend transport. `TERRACES_MODERATOR_USER_ID` uses the existing protected internal-ID guard and remains unset in hosted configuration.

Modern credential compatibility: prefer server-only `SUPABASE_SECRET_KEY`; use `SUPABASE_SERVICE_ROLE_KEY` only when the preferred value is absent/empty. Modern `sb_secret_` values travel solely in `apikey`; legacy HS256 service-role JWTs retain `apikey` plus Bearer headers. A malformed nonempty preferred key fails closed rather than silently falling back. Local checks validate modern key shape or legacy JWT shape/role/expiry; they do not establish cryptographic authenticity, project membership or live permissions. Supabase must verify authority during separately approved Storage acceptance. Never expose either credential through NEXT_PUBLIC configuration or logs. Request helpers reject credential-header overrides. No RLS/policy, ownership or moderator checks change.

Modern key suffixes are opaque: accept a nonempty URL-safe suffix within the existing defensive size bound, with no invented minimum length. Empty suffix, whitespace/control characters, quotes, other unsafe characters and publishable keys still fail locally; provider authentication rejects incorrect/revoked keys even when their local shape passes. No credential is trimmed or repaired automatically.

Bucket: `terraces-photos`, private, no public policies. Only sanitised JPEG display/thumbnail variants are written, using random immutable object keys. Raw originals are processed in memory and are not stored. Public/private image URLs are scoped, 90-second bearer URLs; authorised recipients can share those URLs until expiry. Removing a photograph immediately removes it from API publication, but an already-issued URL may remain usable for up to 90 seconds. This limitation requires founder acceptance before activation. No signed URL, credentials, image bytes or supporter identity should be logged.

## API contracts

All authenticated actions use the existing `Authorization: Bearer …` verified Supabase identity mapped to an active registered internal user. Guests and unverified users cannot submit/report; moderator actions additionally require the configured internal ID.

| Method | Route | Contract |
|---|---|---|
| POST | `/terraces/visits/{visit_id}/photos` | Raw image bytes; UUID `Idempotency-Key`; base64url UTF-8 JSON `X-Terraces-Metadata` containing optional `caption`, strict boolean `public_consent`/`rights_acknowledged`, and `consent_version: terraces-public-v1`. One photograph per request. Only owned attendance; canonical venue/fixture are derived, never accepted from client. Returns photo ID and PENDING only after both variants and readiness event persist. |
| GET | `/terraces/visits/{visit_id}/photos` | Owner-only submission status and authorised image delivery. Incomplete reservations are identified as such. |
| GET | `/terraces/photos/{photo_id}` | Public approved/published photo or private owner/moderator access. Never anonymous pending/rejected access. |
| DELETE | `/terraces/photos/{photo_id}` | Verified owner removal; commits unpublication first; physical cleanup complete/pending returned honestly. |
| POST | `/terraces/photos/{photo_id}/reports` | Verified reporter; `{reason}` up to 200 characters; only published photos; one unresolved report per actor/photo. |
| GET | `/terraces/photos` | Approved, published, storage-ready, unpurged only; optional canonical `venue_id`/`fixture_id`; default 12, maximum 24; opaque cursor. |
| GET | `/terraces/moderator/photos` | Pending/approved/rejected filter, bounded ID pagination, pending count. Pending list excludes incomplete uploads. |
| POST | `/terraces/moderator/photos/{photo_id}/approve` | Explicit complete-pending approval and publication timestamp; idempotent approval. |
| POST | `/terraces/moderator/photos/{photo_id}/reject` | `{reason}`; pending only; seven-day retention starts at rejection. |
| DELETE | `/terraces/moderator/photos/{photo_id}` | Immediate unpublication and retryable physical deletion. |
| PUT | `/terraces/moderator/photos/{photo_id}/hold` | `{reason}` creates retention hold; null releases hold on an existing photo; protected audit event. |
| GET / POST | `/terraces/moderator/reports`, `/terraces/moderator/reports/{event_id}/resolve` | Protected bounded pending reports; resolution `{reason}` with audit timestamp. |

Submission guards enforce 10,000,000 original bytes, actual JPEG/PNG/HEIC/HEIF decoding, caption <=200, explicit sharing/rights consent and three active photos per matchday. The existing parent-attendance row lock and database trigger protect concurrent submissions. Rejected/removed photos retain audit history but release active slots. Exact retries use the same key/content/metadata; reusing a key with different content fails. Duplicate content within a matchday fails.

Image processing uses the existing sanitiser in a credential-free child process: two simultaneous workers per API process, 15-second wall timeout, ten-second CPU and 768 MiB address-space limits. Stream reading has a 30-second total and five-second chunk timeout. Malformed, oversized and unsafe input receives a safe error. The unchanged memory-corrected sanitiser and worker passed Linux HEIC/security validation in run 38462613781, including both previously failing genuine fixtures. Peak virtual address space remained near the limit; demanding valid files can safely reject. Check hosted capacity for simultaneous workers before activation. Current opaque-key handling passed 128 local regressions and live private Storage acceptance, including exact deletion and signed-URL expiry. Ordinary authenticated-user direct Storage denial remains untested.

Public payload: photo ID, canonical venue ID, optional canonical fixture ID, caption, display name, publication timestamp, reliable match date and home/away strings, signed variants/expiry. No internal attendance ID, user ID, email, GPS, raw original, hash or storage key is disclosed. Historical dates/fixture context remain null where unknown. All-feed sorting is publication timestamp then photo ID descending, with stable keyset pagination and no age cutoff. Canonical fixture filtering permits future grouping; no guessed groups or new grouping infrastructure.

## Transactions, cleanup and migration

The lifecycle service owns commits. Durable private reservation commits before external storage writes; complete storage readiness commits afterwards. Failed or interrupted uploads cannot enter moderation/public reads; same-key retries and bounded cleanup handle partial variants. An incomplete reservation over five minutes old can be cleaned without publishing or inventing a matchday.

Removal commits REMOVED/publication-null before physical deletion. Attendance deletion uses the existing unpublication trigger. Account deletion cascades photo rows and preserves opaque deletion receipts. B1 updates the existing trigger to retain the legal-hold boolean in those receipts, and adds one event lookup index; no new table or column. Unknown legacy hold state fails closed. Holds do not block unrelated cleanup. A held orphan receipt needs a separately reviewed operator retention decision; no automatic hold release is offered.

`terraces_cleanup.py` is a protected local/operator entrypoint requiring both `--execute` and `--confirm-private-cleanup`; it is not connected to any scheduler. Before live contributions, arrange a separately approved invocation through existing maintenance operations. It purges removed variants, rejected variants after seven days, eligible account-deletion receipts and abandoned partial uploads, with durable retry state. No new cron is created. Account/attendance deletion may require the next cleanup invocation to remove physical variants; API visibility is revoked immediately.

Founder-approved cadence: daily cleanup. Prepared schedule is `0 5 * * *` (05:00 UTC), separate from fixture reconciliation at 04:20 UTC. This spacing is not a guarantee against concurrent runs. The CLI's bounded `--limit` defaults to 50 per category, accepts 1–500, exits nonzero for pending retries or database/storage failures, and logs no private exception details. Seven-day eligibility plus daily execution means normal rejected-image purge between seven and eight days after rejection; failures/holds may delay it. Repeated invocations are safe. No hosted schedule is configured. Existing repository infrastructure contains only the fixture cron: a distinct Railway cron execution context would need explicit founder approval; do not add cleanup to that fixture service or create a permanent service silently. For a small beta, an operator-run daily command is the fallback until that decision. Review run success, retry count and backlog; do not assume a configured schedule proves successful execution.

Release order: approved backup/schema preflight → apply `20261013_terrace_photo_b1.sql` after Phase A → verify trigger/index → validate private storage/LINUX worker → separately approve backend deployment/configuration and moderator identity. Route activation is a distinct approval. Roll back code by leaving/disabling the feature flag and restoring the prior backend release. B1 SQL rollback intentionally refuses when photo/event data exists: retain hold-preserving schema and review retention rather than automatically downgrading it. Never restore production automatically.

## Future interfaces (documented, not implemented)

B2 supporter: My Matchdays → Went → Add Photos; compact mobile selection up to three, optional captions, explicit consent, pending-review confirmation and later uploads to owned Went records. No inferred attendance.

B2 founder: My Account → Manage Submissions; private Pending / Published / Reported, photo/caption/reliable fixture context, approve/reject/remove/report resolution and simple pending count. Every action enforces server authorisation. No email notifications.

C: dedicated From the Terraces page and permanent canonical venue galleries. Discover click-through only after the first approved publication; no embedded feed or new primary navigation tab. Show honest empty states, no fabricated activity.

The previously founder-approved From the Terraces visual mockup remains the B2 UI reference. Do not substitute a new design during this backend release. The original visual asset was not located in the bounded local report inspection; confirm its authoritative attachment/path with the founder before B2 UI work. No B2/C interface or frontend asset is included here.

## Protected release configuration

| Variable | Purpose | Disabled-foundation release state |
|---|---|---|
| `SUPABASE_URL` | Existing exact project HTTPS root | Protected backend setting only, configured under later approval if needed. |
| `SUPABASE_SECRET_KEY` | Preferred existing modern server credential | Protected backend secret only; never NEXT_PUBLIC, source, logs, reports or CI. Missing key does not activate routes. |
| `SUPABASE_SERVICE_ROLE_KEY` | Optional legacy fallback | Do not introduce a legacy key for this release; retain existing compatibility only. |
| `TERRACES_MODERATOR_USER_ID` | Founder stable internal Matchgoer user ID | Unset. Missing/invalid value denies moderator access. No email/display-name authority. |
| `TERRACES_BACKEND_ENABLED` | Mounts all B1 `/terraces` routes | Absent or `false`. Only explicit `true` enables routes; later activation approval required. |

No other B1 activation flags, frontend dependencies, SMTP settings or storage policies are required. `DATABASE_URL` reuses the existing governed Railway PostgreSQL configuration. Keep fixture cron/configuration and API-Football behaviour unchanged. The photo cleanup CLI is independent of route mounting and must never be invoked merely because the backend is deployed.

Safe rotation is a future authorised operation: inventory all consumers of the current key, obtain founder approval, create/choose an approved replacement server secret without revoking the old one first, update protected backend configuration and any separately approved DPAPI operator copy, verify exact-project authentication and approved synthetic upload/sign/delete/cleanup under the replacement, then revoke the old key only after all consumers migrate. Preserve disabled routes/unset moderator during foundation setup. Never rotate automatically, expose key values, change RLS/policies, or weaken ownership guards to test rotation. If replacement fails, retain/restore the previous valid configuration under the controlled rollback plan; do not revoke it prematurely. Previously issued signed URLs may retain their short expiry window.

## Controlled deployment sequence (not executed)

1. Obtain explicit founder release approval before push, merge, migration or deployment. Verify the exact release commit/files against the receipt and current master; stop on drift. Freshly identify Railway project/environment/API service, current source/release and rollback target. Treat the historical Phase A release as a candidate until confirmed live. Check cron deployment behaviour without triggering reconciliation.
2. Fresh read-only PostgreSQL schema/trigger/index preflight: Phase A tables/function match the expected base; B1 migration is not already partially applied. Review existing photo/event rows and hold receipts. Verify existing supporter/attendance counts, keys and relationships for preservation. No automatic repair or identity edits.
3. Verify a recent encrypted/restorable backup and restoration procedure. Refresh under explicit backup approval if meaningful changes occurred; never export supporter data into the repository or restore production automatically. Retain before-state schema/count evidence and rollback proof.
4. Under explicit migration approval, apply `20261013_terrace_photo_b1.sql` after Phase A using the existing controlled SQL transaction convention. Set bounded transaction-local lock/statement controls in the governed wrapper before executing the migration; no global setting changes. Confirm hold-preserving function and exact index, no new tables/columns or supporter/attendance mutations. Stop/rollback on unexpected schema or locks; no blind repeats of index creation.
5. Under separate configuration approval, provision protected server variables as needed. Reverify exact private bucket, retain founder policy evidence and independently verify effective access when a dedicated user session is available. Moderator stays unset and routes absent/false. Daily cleanup is not scheduled; any separate cron context needs explicit approval.
6. Deploy only the approved backend through the established Railway flow. No frontend release, Supabase policy changes, new keys, cron execution or upload activation. Verify dependency/build compatibility with unchanged Phase A pins. Stop if a configuration/deployment action unexpectedly starts reconciliation or public photo routes.
7. Non-mutating smoke checks: `/health`, current API release/source, existing read-only public routes, and absence of `/terraces` routes/OpenAPI entries. No fixture-detail view-recording endpoints, account actions, uploads, moderator grants or fake attendance. Hosted authenticated persistence is not claimed without separately approved dedicated acceptance.
8. Later B2/activation: confirm original mockup, build the approved supporter/moderator UI, complete rights/consent and owned-account acceptance, ordinary-user denial, capacity and daily cleanup monitoring; then request explicit activation approval. Phase C remains separate.

Rollback: disable/leave the route flag false, stop any separately activated photo cleanup under approval, restore the freshly verified previous backend release/configuration. Keep the B1 hold-preserving schema if contributions/events exist: its rollback SQL intentionally refuses nonempty photo/event tables. Empty-schema rollback needs explicit reviewed approval and verification; do not downgrade legal-hold receipts, delete real contributions or restore the production backup automatically. Keep moderation fail-closed and privacy unchanged throughout.
