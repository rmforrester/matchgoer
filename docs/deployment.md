# Closed-beta deployment

**Status:** Phase 5C repository preparation complete; external infrastructure and deployed acceptance are not complete.

**Decision:** use **Vercel (Next.js) + Railway (FastAPI, PostgreSQL and scheduled fixture refresh) + existing Supabase Auth**, with the web and API on HTTPS subdomains of one owned parent domain.

Example only:

```text
https://beta.example.com       Vercel frontend
https://api.beta.example.com   Railway FastAPI
```

The actual domain must be selected before dashboard setup. The default provider domains are useful for health checks, but they are not the accepted anonymous-session topology.

## Why this stack

| Option | Fit for this beta | Decision |
|---|---|---|
| Vercel frontend | Native Next.js builds, preview/production rollback and managed HTTPS. Hobby is free only when its eligibility terms fit the project. | Selected |
| Railway API + PostgreSQL | One small project can host the Dockerized API, managed database and cron service; private database networking, logs, health checks and reversible deploys keep operations small. | Selected |
| Render | FastAPI, PostgreSQL, custom domains and cron are suitable, but a free web service sleeps and free PostgreSQL is temporary; the reliable configuration adds more separate baseline services. | Viable fallback |
| Fly.io | Flexible and capable, but its VM/network/database operation is more work than a ten-person beta needs. | Not selected |
| Supabase database | Technically compatible and could consolidate vendors, but moving the application database is not needed to preserve Supabase Auth. Free projects can pause and lack automatic backups. | Viable fallback |

Authoritative provider references: [Vercel pricing](https://vercel.com/pricing), [Railway pricing](https://railway.com/pricing), [Railway Dockerfiles](https://docs.railway.com/builds/dockerfiles), [Railway cron jobs](https://docs.railway.com/reference/cron-jobs), [Railway PostgreSQL](https://docs.railway.com/databases/postgresql), [Render free limitations](https://render.com/docs/free), [Fly.io pricing](https://fly.io/docs/about/pricing/), and [Supabase billing](https://supabase.com/docs/guides/platform/billing-on-supabase).

## Current runtime and deployment gaps

| Dependency | Current implementation | Deployment finding |
|---|---|---|
| Web | Next.js 16, React/TypeScript, Axios, Leaflet/react-leaflet | `NEXT_PUBLIC_API_BASE_URL` is deployment-ready. Browser-hostname `:8000`, localhost and LAN discovery are development fallbacks only. |
| API | FastAPI/SQLAlchemy/Uvicorn | Environment-driven CORS/cookies exist. `Dockerfile.backend`, Railway config and a DB-aware `/health` endpoint now support hosting. |
| Data | PostgreSQL via `DATABASE_URL` | Must move to managed PostgreSQL. Pool pre-ping/recycle now tolerate stale hosted connections. |
| Identity | Supabase Auth plus internal anonymous cookie/user identity | Existing public bearer configuration remains; anonymous cookies impose the domain requirement below. |
| Fixtures | Import pipeline plus `refresh_fixture_states.py` | Imports and refresh currently run as commands. A hosted daily refresh is required; reports/cache may remain ephemeral. |
| Maps | OpenStreetMap tiles, Nominatim search and browser geolocation | Public HTTPS fixes the LAN insecure-context limitation. No persistent map filesystem is needed. Respect external-service usage policies and monitor failures. |
| Filesystem | Ingestion cache and QA JSON reports | No product request depends on durable local files. Operational reports must be captured in job logs or copied off-container if retention is required. |

Legacy root utilities that contain fixed localhost database settings are not deployment paths and must not be used in beta. A legacy source-controlled database password was removed during this phase; rotate that credential because Git history may still contain it.

## Domain, CORS and cookies

`beta.example.com` and `api.beta.example.com` are different origins but the same HTTPS site. Keep `terrace_session` host-only on the API (do not set a broad `Domain` attribute), `HttpOnly`, `Secure`, `Path=/`, and `SameSite=Lax`. Axios already sends credentials. The API must allow the exact frontend origin and credentials.

This topology lets browser requests from the web subdomain to the API subdomain carry the anonymous cookie while limiting the cookie to the API host. `SameSite` is based on scheme plus registrable domain, not origin. See [MDN cookie guidance](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Cookies) and [Set-Cookie semantics](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie).

Do not use `*.vercel.app` with `*.up.railway.app` for acceptance: those are different sites, so `SameSite=Lax` excludes the cookie from cross-site Axios calls. `SameSite=None; Secure` is configurable as an emergency compatibility test, but it makes the cookie third-party and is not the chosen beta architecture. Registered requests normally use a bearer token; anonymous Interested and in-place account claiming still require reliable cookie ownership.

Beta API environment:

```text
TERRACE_ENV=production
TERRACE_ALLOWED_ORIGINS=https://beta.example.com
TERRACE_ALLOW_PRIVATE_NETWORK_ORIGINS=false
TERRACE_COOKIE_SECURE=true
TERRACE_COOKIE_SAMESITE=lax
TERRACE_ANONYMOUS_SESSION_MAX_AGE_SECONDS=31536000
DATABASE_POOL_RECYCLE_SECONDS=300
DATABASE_URL=<Railway private PostgreSQL URL>
SUPABASE_AUTH_ENABLED=true
SUPABASE_JWT_ISSUER=https://<project-ref>.supabase.co/auth/v1
SUPABASE_JWT_AUDIENCE=authenticated
SUPABASE_JWKS_URL=https://<project-ref>.supabase.co/auth/v1/.well-known/jwks.json
SUPABASE_PUBLISHABLE_KEY=<public publishable key>
API_FOOTBALL_KEY=<secret API key>
```

Beta frontend environment:

```text
NEXT_PUBLIC_API_BASE_URL=https://api.beta.example.com
NEXT_PUBLIC_SUPABASE_URL=https://<project-ref>.supabase.co
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=<public publishable key>
```

Only `NEXT_PUBLIC_*` values are browser-visible. Never add `DATABASE_URL`, API-Football credentials, service-role keys, JWTs or session values to Vercel frontend variables.

## Beta database migration

Use a new Railway PostgreSQL service; never connect testers to the laptop database. Preserve schema, constraints, sequences, provider fixture IDs, provider venue references, teams, fixtures, venues and venue-name history. Exclude all local personal/test ownership data:

```text
users, user_identities, account_merge_audits, anonymous_sessions,
interested_fixtures, user_profiles, fixture_meeting_intents,
match_board_posts, match_board_reports, social_events,
venue_visits, away_day_reviews, matchday_tips
```

From a machine with PostgreSQL client tools, create a portable custom-format dump. Supply URLs through process environment; never paste them into files or shell history shared with others.

```powershell
pg_dump $env:SOURCE_DATABASE_URL --format=custom --no-owner --no-acl `
  --exclude-table-data=users --exclude-table-data=user_identities `
  --exclude-table-data=account_merge_audits --exclude-table-data=anonymous_sessions `
  --exclude-table-data=interested_fixtures --exclude-table-data=user_profiles `
  --exclude-table-data=fixture_meeting_intents --exclude-table-data=match_board_posts `
  --exclude-table-data=match_board_reports --exclude-table-data=social_events `
  --exclude-table-data=venue_visits --exclude-table-data=away_day_reviews `
  --exclude-table-data=matchday_tips --file terrace-talk-beta.dump

pg_restore --dbname $env:TARGET_DATABASE_URL --no-owner --no-acl `
  --single-transaction --exit-on-error terrace-talk-beta.dump
```

The initial dump contains the already-migrated schema. Before every later schema change: take a Railway volume snapshot and offsite logical dump, review and apply exactly the forward SQL file in timestamp order, run reconciliation, then deploy code. The rollback SQL files are emergency aids, not automatic migrations; data-changing rollback requires an explicit review.

Reconcile after import:

- table/fixture/team/venue/venue-name/provider-reference counts match the source subset;
- personal tables above are empty;
- no duplicate provider venue IDs, provider fixture IDs or natural fixtures;
- no orphan fixture/team/venue references or invalid coordinates;
- `fixtures.fixture_date` remains `TIMESTAMPTZ` and representative UTC values match;
- API smoke checks return expected fixture/venue discovery.

Enable daily Railway volume backups and take an offsite logical dump before migrations and fixture imports. Perform a restore drill before invitations. Railway documents snapshot and logical restore behavior in its [backup guide](https://docs.railway.com/guides/postgres-backups-restores).

## Supabase dashboard configuration

Keep the existing project and public publishable-key architecture; no service-role key is required.

In Supabase **Authentication → URL Configuration**:

1. Set **Site URL** to `https://beta.example.com`.
2. Add exact redirect URLs used by the current callback flow, at minimum `https://beta.example.com/auth/callback` and the product return paths exercised by signup/sign-in. Do not add a wildcard production origin.
3. Retain localhost redirects only for deliberate development testing.
4. Verify the confirmed-email template returns to the beta domain, and perform the confirmation in the same browser/device for the in-place anonymous claim journey.
5. Confirm the backend issuer, audience and JWKS values correspond to this same project.

## Fixture operations

Create a second Railway service from the same repository/image, with no public domain. In that service's **Settings → Config as Code**, select the repository-absolute `/railway.cron.toml`; this deliberately omits the API health check and defines the daily 04:20 UTC schedule. It shares the private `DATABASE_URL`, API-Football key and relevant environment. Its command is:

```text
python /app/refresh_fixture_states.py --write --confirm-write
```

The default window is the previous 7 through next 60 days; the job updates existing fixtures only and exits non-zero on failure. Railway cron runs in UTC, requires the task to exit, and skips an invocation if the previous execution is still active. Review cron logs daily during the ten-user beta. Run an additional manual hosted command on busy matchdays and run a dry-run before any expanded import. New competitions/seasons remain a controlled manual ingestion operation, not this refresh job.

Minimum failure signals are: non-zero job/deploy status, missing daily success log, provider error, `past_ns_beyond_six_hours > 0`, future-final fixtures, or database connection failure. Name one operator and escalation contact before invitations.

## Deployment runbook

### One-time external setup (manual)

1. Choose/confirm an owned parent domain and the beta/API hostnames. This is the first blocking decision.
2. Create or select a Vercel account/project; import this repository and set **Root Directory** to `frontend`.
3. Create a Railway project with PostgreSQL and an API service connected to this repository. Railway reads `railway.toml` and `Dockerfile.backend`.
4. Set all API variables listed above, using Railway's private PostgreSQL reference for `DATABASE_URL`. Do not expose the database publicly after the one-time import unless needed for an operator tunnel.
5. Add `api.beta.example.com` to the Railway API service and complete its DNS record; wait for managed TLS.
6. Add `beta.example.com` to Vercel and complete its DNS record; set frontend variables and redeploy because `NEXT_PUBLIC_*` values are build-time inputs.
7. Configure the exact Supabase Site URL and redirects.
8. Create the Railway cron service, select `/railway.cron.toml` as its custom config file, and verify one manual execution before accepting its daily UTC schedule.
9. Enable Railway database backups, make one logical dump and perform a restore drill.

### Data and release

1. Take a source backup and generate the sanitized dump above.
2. Restore it into the empty managed beta database and run reconciliation before the API is shared.
3. Deploy API; require `GET /health` to return `200 {"status":"ok"}`. A database failure must return 503.
4. Deploy web; inspect Vercel build/runtime logs for errors.
5. Confirm response CORS permits only the exact beta frontend and that `Set-Cookie` has `Secure; HttpOnly; SameSite=Lax`.
6. Run the HTTPS smoke path below, then the full [trusted beta acceptance](./beta-acceptance.md) matrix on a phone off Wi-Fi.

Smoke path:

1. Open web home; city search and browser location; map tiles, Search This Area and fixture cards.
2. Open `/health`, `/`, `/session`, `/leagues`, a venue and a fixture through the public API.
3. Anonymously add Interested, refresh and confirm the same internal user owns it.
4. Sign up/confirm or sign in, return to the fixture, and verify in-place claim/account behavior.
5. Exercise Who's Going, My Matchdays, My Grounds and permitted Match Board post/delete.
6. Confirm a completed board remains readable and rejects posting.
7. Check Railway API/cron logs, Vercel logs and database connectivity without logging tokens, email or content.

## Rollback

- **Frontend:** promote the last known-good Vercel deployment; public domain remains unchanged.
- **API:** roll back/redeploy the last known-good Railway deployment. Do not roll code backward across an incompatible schema.
- **Database:** stop writes, preserve the failed state, then restore a verified pre-release Railway snapshot or logical dump. Re-run reconciliation before reopening.
- **Fixture refresh:** disable the cron service, inspect its report/logs and restore only affected data when a reviewed corrective update is safer than a full restore.
- Keep DNS changes stable during ordinary code rollback. If the environment is unsafe, remove tester access rather than redirecting it to the laptop.

## Operations, cost and PWA assessment

For ten testers, provider logs plus deployment/cron notifications and `/health` are sufficient initially. Review Vercel build/runtime errors, Railway API exceptions and restarts, failed auth codes (without tokens/email), cron exit status, and database health. Do not add a large observability product yet. Add an external uptime check only after the beta URL exists.

Likely monthly cost is **about US$5–15 plus a domain**, assuming Vercel Hobby is eligible, Supabase Free remains suitable, and the small Railway API/database/cron usage stays close to its Hobby included usage. Railway Hobby has a monthly minimum/included usage; actual CPU, RAM, storage, backups and egress are metered. If the project is not eligible for Vercel Hobby, budget Vercel Pro separately (currently US$20/month). Render's free cold start and expiring free database are not acceptable for this acceptance gate. Confirm current prices and terms in each dashboard before purchase.

PWA is **not ready yet**: there is no web app manifest, production icon set, service worker/offline policy or validated standalone/safe-area behavior. Responsive metadata is present through Next.js defaults and the app-first layouts are a useful base. After hosted-beta acceptance, add a minimal manifest/icons and test Add to Home Screen/standalone behavior; do not add offline mutation caching or begin native apps in Phase 5C.

## Gate

Repository preparation does not make the beta live. Invitations remain blocked until the external services, same-site custom domains, sanitized database, backups, cron, smoke checks and physical mobile acceptance are complete. Do not begin the Hutnik Test before this gate passes.
