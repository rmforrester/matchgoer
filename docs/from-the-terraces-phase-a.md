# From the Terraces: private foundation

Phase A is local implementation only. No upload/public/moderation endpoints,
storage client, bucket, permission grant or publication UI is enabled. The
existing application does not call these helpers or automatically apply this
migration. Deployment and hosted migration require separate founder approval.

## Identity and transaction boundaries

`require_verified_account` reuses Supabase signature/issuer verification and
confirmed permanent-provider identity checks, then resolves `UserIdentity` to
the active internal registered `user_id`. Names and emails never grant ownership
or moderator permission. `require_moderator` additionally requires one explicit
positive internal user ID supplied by trusted server configuration; unset fails
closed. The default guard and private-read policy now load
`TERRACES_MODERATOR_USER_ID` from the existing backend process environment.
Only canonical positive ASCII decimal values within PostgreSQL INTEGER range
are accepted; whitespace, signs, zero, overflow and identity labels deny access.
An explicit helper argument remains trusted server-only, never request input.
No account has been granted this permission and no environment value was set.

`reserve_photo` derives venue/fixture from the locked owned `VenueVisit`; there
are no caller-supplied venue/fixture arguments. Historical undated/unlinked
visits remain supported. Disputed fixture/venue associations fail closed.
The caller owns BEGIN/COMMIT/ROLLBACK; helpers never commit. UUID retry keys are
idempotent only for identical request content. Duplicate image hashes for the
same attendance are rejected. Three pending/approved slots per matchday are
enforced by both helper and PostgreSQL parent-row lock/trigger. Rejected/removed
rows do not use an active slot, but remain auditable.

## Migration and lifecycle

`20261013_terrace_photo_foundation.sql` adds `terrace_photos` and
`terrace_photo_events`, indexes, constraints and scoped lifecycle triggers.
No existing attendance/identity columns or guest-conversion code change.
Photo owner, canonical context, consent version and object keys are immutable.
Only Pending, Approved, Rejected and Removed states exist. No approval API is
implemented. Publication is a separate nullable timestamp, allowed only on
approved records with an approval timestamp.

Attendance deletion or identity/context replacement removes public eligibility
and detaches the photo from the deleted/changed attendance. Deduplication that
deletes a referenced visit therefore fails closed by unpublishing; it never
guesses a surviving visit or transfers photo ownership. This may require a later
explicit review/resubmission even if another equivalent visit survives. Guest
records cannot own submissions; guest claiming/merging rules are unchanged.

Account deletion cascades photo metadata deletion after the existing account
deletion workflow handles attendance. Opaque object keys remain in minimal
storage-deletion receipts; no captions, emails or ownership identifiers are
copied into those receipts. Physical object deletion is NOT performed in Phase A.

Rejected rows become storage-deletion candidates seven days after rejection;
a nonblank documented dispute holds them. Removed rows are immediately eligible.
The future deletion executor must recheck current state/disputes and record
successful deletion of both variants before acknowledging completion. It must
also consume receipts for already-deleted photo/account records. There is no new
queue, scheduler or cron change; actual cleanup execution remains Phase B work.

Rollback drops only new tables/functions and their attendance trigger. Once
real contributions exist, hosted rollback needs a reviewed metadata and private
asset backup/purge plan; dropping tables alone is not a valid media rollback.

## Private storage plan (not provisioned)

Reuse the existing Supabase project with ONE private supporter-photo bucket.
No public bucket, anonymous uploads, direct client overwrite, frontend service
credential or raw-file publication. Random immutable `photos/<uuid>/display.jpg`
and `thumbnail.jpg` keys contain no user/venue names. Generate variants before
storage; do not retain original raw images as storage objects.

The future existing backend checks `may_read_photo` before issuing narrowly
scoped, short-lived access to sanitised variants. Pending/rejected access is
limited to verified owner/moderator. Anonymous access requires approved AND
published state. Removed/purged content is denied. Supabase RLS cannot read the
Railway approval table; do not pretend a browser flag or folder name enforces
moderation. Server-side storage authority and deny-by-default policies require
separate configuration approval. Signed links/cache expiry and object removal
must be tested; previously downloaded public copies cannot be recalled.

Founder confirms Supabase Free, one private `terraces-photos` bucket, no public
Storage policies, a 10 MB limit and JPEG/PNG/HEIC/HEIF restrictions. Independent
bucket/permission inspection remains unavailable: local configuration has no
Storage administrative credential. Actual Storage bytes/quota and server
authority remain outstanding; database usage is not Storage capacity.
Published Free Storage allowance is 1 GB; review at 70% of the confirmed
applicable quota. Retain private, deny-by-default client access. Server service
credentials bypass RLS and require the existing ownership/moderation guards.
No configuration or credentials were changed to complete this audit.

## Image processing

One HEIC plugin, `pillow-heif==1.8.1`, plus its pinned Pillow runtime
`Pillow==12.3.0`; no image-processing service. Original limit is decimal 10 MB.
Decode actual bytes, accept JPEG/PNG/HEIC stills, reject animation/multi-frame,
cap 24 million pixels and 10,000px on either side before full decode. Very
high-resolution phone originals may need downscaling in a later upload UI.
Orient before creating fresh RGB pixels and JPEG variants (1600px/400px longest
side, no upscaling/cropping). Transparency flattens onto white. Do not propagate
EXIF/GPS/XMP/ICC or embedded thumbnails; raw data is not returned or stored.

Future HTTP upload handling must enforce the 10 MB cap while streaming, bounded
processing concurrency/time/memory, request abuse limits and temporary-file
cleanup. Library utilities alone are not a complete untrusted-upload boundary.
No UI/API is enabled until those controls and real HEIC tests pass.

Windows Application Control still blocks the native HEIC decoder locally.
Linux validation succeeded on the temporary branch at
`89fe0d41f12bdc10e1a2570e1f13705de3a080b2` using the existing Python 3.14 slim
base, pinned codec dependencies and three genuine HEIC fixtures. The validated
test-only fixture construction correction is integrated; exact orientation
and metadata assertions remain intact. Never bypass Windows security policy.
Temporary CI assets and its Vercel deployment guard are not release files.

## Approved Phase B moderation direction (documentation only)

My Account -> Manage Submissions, visible only to the authorised founder
moderator. Use a dedicated private, mobile-first page suitable for iPhone:
pending submissions, published photographs, reported photographs, photo/caption/
reliable fixture context, approve/reject, remove published content and one simple
pending count. Every read/action must enforce moderator permission server-side;
hiding a navigation link is not authorisation. No moderation route/UI is built
in Phase A. Email notifications are deferred; no email approval/rejection,
separate admin service or complex dashboard.

## Later public UX (latest founder scope)

Dedicated From the Terraces page, all approved published photos newest published
first, paginated without age/total cutoff. Permanent canonical venue galleries
and reliable fixture grouping. Discover contains only a compact click-through
after fixture content, and only when an approved published photo exists. No
embedded feed or new primary tab. Postcards remain deferred. These are not built
in Phase A. Rights/consent text corresponding to the reserved version identifier
must be approved before submission controls are enabled.
