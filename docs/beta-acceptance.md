# Trusted beta acceptance

**Status:** Automated stabilization complete; manual gate pending.

Matchgoer must not be called beta-ready until this script passes on the intended HTTPS deployment and real mobile devices.

## Fixture trust contract

- API-Football supplies ISO 8601 timestamps with an offset.
- PostgreSQL stores `fixtures.fixture_date` as `TIMESTAMPTZ` (an absolute instant).
- SQLAlchemy uses `DateTime(timezone=True)` and backend responses are offset-aware.
- Browsers convert that instant to the supporter's local timezone for display.
- `NS`, live, `FT`, `AET`, `PEN`, postponed and cancelled states remain provider-authored. Matchgoer never infers full time from elapsed time.
- Date filters currently use UTC calendar bounds. This is deterministic; venue-timezone-aware search dates remain a future data-model consideration for rare midnight-edge fixtures.

Apply `backend/migrations/20260820_fixture_datetime_utc.sql` only after its documented timezone/sample preflight. Refresh mutable fixture data with a dry run first:

```powershell
.\backend\venv\Scripts\python.exe refresh_fixture_states.py --from-date 2026-08-13 --to-date 2026-10-19
.\backend\venv\Scripts\python.exe refresh_fixture_states.py --from-date 2026-08-13 --to-date 2026-10-19 --write --confirm-write
```

The refresh bypasses ingestion cache, updates only existing fixture time/status/result/raw venue labels, writes transactionally, and saves a reviewable report. Schedule it at least daily during beta, with an additional matchday run where practical.

## Automated preflight

Require backend compilation/tests, identity/social tests, frontend ESLint/TypeScript/build, fixture parity/status checks, `pip check`, HTTP smokes, database reconciliation and `git diff --check`. Acceptance-only ownership/content rows must be reconciled afterward.

## Manual supporter journey

Run once anonymously and once registered:

1. Search London with dates, radius and multiple leagues; pan and use Search This Area.
2. Confirm map, cards and Worth the Trip share the location and show the same kickoff/status.
3. Mark Interested anonymously, dismiss its prompt, refresh, and confirm preservation.
4. Attempt Who's Going and Match Board posting anonymously; confirm the account gate and return path.
5. Complete signup/confirmation/onboarding in the same browser and confirm in-place ownership preservation.
6. Enable Who's Going, post, refresh, delete the own post, and reject another user's delete.
7. Open a finished fixture; keep board history readable, reject posting, and never infer attendance.
8. Confirm attendance twice and verify one visit, Attended placement, and My Grounds membership.
9. Save and edit one review without requiring a tip; add an optional tip without altering visit/review counts.
10. Add one fixture-linked historical visit and one manual dated visit.
11. Sign out/in and confirm Interested, attendance, grounds, review, profile and social restoration.

## Mobile and accessibility matrix

Repeat the core path at **375px, 390px and 430px**, then on at least one physical iOS or Android browser. Check navigation, search, map gestures/tile failure, carousel snapping, long names, account keyboard behavior, My Matchdays, My Grounds, 44px controls, review/tip forms, board composer/closed state, visible focus, screen-reader labels, 200% zoom and colour-independent states. Record browser/device, viewport, outcome and screenshot for failures. Code inspection does not satisfy this gate.

## Deployment contract

Backend:

```text
TERRACE_ENV=production
TERRACE_ALLOWED_ORIGINS=https://beta.example
TERRACE_ALLOW_PRIVATE_NETWORK_ORIGINS=false
TERRACE_COOKIE_SECURE=true
TERRACE_COOKIE_SAMESITE=lax
TERRACE_ANONYMOUS_SESSION_MAX_AGE_SECONDS=31536000
```

Frontend:

```text
NEXT_PUBLIC_API_BASE_URL=https://api.beta.example
NEXT_PUBLIC_SUPABASE_URL=<public project URL>
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=<public publishable key>
```

Keep database credentials, service-role keys, signing secrets and tokens outside frontend variables and documentation. Confirm Supabase redirects, email confirmation, public JWKS, audience, signup rate controls and recovery/support ownership.

The selected hosting topology, same-site custom-domain requirement, sanitized database migration and exact external setup are defined in [Closed-beta deployment](./deployment.md). Default Vercel and Railway domains are not the accepted anonymous-cookie topology.

## Minimal analytics contract

No provider is installed in Phase 5B.

| Event | Essential properties |
|---|---|
| `discover_opened` | pseudonymous session/user, viewport bucket, timestamp |
| `search_completed` | mode, coarse radius, date-window days, league count, result count, coarse region |
| `fixture_viewed` | fixture ID, source surface |
| `interested_added` | fixture ID, source surface |
| `whos_going_enabled` | fixture ID |
| `attendance_confirmed` | fixture ID, venue ID, source |
| `ground_added` | venue ID, fixture-linked/manual source |
| `review_completed` | venue ID, new/edit flag |
| `tip_contributed` | venue ID |
| `account_created` | anonymous activity yes/no, claim result |

Never capture email, provider subject, tokens, exact coordinates, raw location queries, board text or tip text. Use short anonymous-search retention and pseudonymous identity for D1/D7 return.

Ask voluntarily: **Did Matchgoer help you find or attend a match you otherwise might not have?** Suggested answers: Yes; Maybe; No; Prefer not to say. Do not implement this prompt until timing and consent are approved.

## Focus geography and decision

London/nearby England is the initial QA geography. The 20 August snapshot has 254 mapped fixtures in the approximate region/next-month window, zero unlinked England fixtures, zero invalid England coordinates and zero duplicate natural fixtures. Dave Bryant Stadium is a reviewed exception: three forthcoming Enfield Town fixtures remain outside map/radius discovery until coordinates are independently verified. Do not guess or auto-merge it.

Automated completion is **GO for manual acceptance**, not GO for invitations. Invite 10 supporters only after the manual gate passes and monitoring, backup, moderation contact, support/recovery and rollback owners are named.
