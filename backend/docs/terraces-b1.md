# From the Terraces B1: disabled backend contracts

Local implementation based on Phase A `3133163a963b9d9c5b80942ede037f41cc977008`. No frontend, public activation, scheduler, email notifications or storage policy changes.

## Configuration and activation

`TERRACES_BACKEND_ENABLED` defaults to false. Only an explicit server value `true` mounts `/terraces` routes. Before a separately approved activation, apply the B1 migration, verify the private bucket and storage permissions, validate the image worker on Railway-compatible Linux, and agree an operational cleanup cadence. Never expose `SUPABASE_SERVICE_ROLE_KEY` to the browser. `SUPABASE_URL` and that key are read only by the backend transport. `TERRACES_MODERATOR_USER_ID` uses the existing protected internal-ID guard and remains unset in hosted configuration.

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

Image processing uses the existing sanitiser in a credential-free child process: two simultaneous workers per API process, 15-second wall timeout, and Linux CPU/memory limits. Stream reading has a 30-second total and five-second chunk timeout. Malformed, oversized and unsafe input receives a safe error. Existing HEIC Linux validation establishes the sanitiser's decoding/orientation/metadata behaviour; the newly added worker limits require a fresh Linux deployment gate.

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
