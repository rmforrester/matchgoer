# Developer runbook

## Phase 4 bearer configuration

Supabase bearer verification is disabled by default. Current anonymous development requires no Supabase settings. Bearer resolution and Phase 4C live-provider claim testing use backend environment variables only:

```text
SUPABASE_AUTH_ENABLED=false
SUPABASE_JWT_ISSUER=
SUPABASE_JWT_AUDIENCE=
SUPABASE_JWKS_URL=
SUPABASE_JWKS_TIMEOUT_SECONDS=3
SUPABASE_JWKS_CACHE_SECONDS=300
SUPABASE_PUBLISHABLE_KEY=
SUPABASE_PROVIDER_USER_TIMEOUT_SECONDS=3
```

For a development project, use the Supabase project URL, issuer `<project URL>/auth/v1`, JWKS URL `<issuer>/.well-known/jwks.json`, the access-token audience (normally `authenticated`) and the public/publishable key. Enable the feature only after these values are known. Never place access tokens, refresh tokens, service-role keys, JWT signing secrets or database credentials in documentation, committed files or diagnostic output.

`POST /account/claim` validates the JWT locally and calls `<issuer>/user` with the public key and bearer to confirm the current permanent, verified provider user. Automated tests use standards-compliant local RSA JWT/JWKS and provider-user fixtures.

The development project was live-tested on 19 August 2026 with:

- Email authentication with confirmation enabled; Google OAuth is not yet enabled/tested.
- Audience `authenticated`.
- EC P-256 / ES256 access-token signing.
- Public JWKS discovery containing the active EC verification key.
- Successful anonymous-to-registered in-place claim, revoked-cookie handling and post-claim bearer reads.
- `409 IDENTITY_ALREADY_LINKED` for a second anonymous user, with no merge or session revocation.

`/auth-test` is a development-only harness and resolves to not-found in production builds. It never renders or logs access tokens, refresh tokens or provider subjects. Use a private window and disposable credentials. It is not product signup/login UI.

The disposable provider user is not removed automatically because cleanup must not require a service-role key. Remove it manually from **Supabase Dashboard → Authentication → Users** when no longer needed.

## Phase 4E product account testing

The product routes are `/signup`, `/signin`, `/auth/callback`, `/account/onboarding`, `/account/ready` and `/account/conflict`. The callback URL, including local query strings, must be permitted by the Supabase development project's redirect configuration. `/auth-test` remains a development-only diagnostic and returns not-found in production.

Use a private browser window and a disposable email identity for acceptance testing:

1. Create meaningful anonymous activity and record its internal owner/counts.
2. Open `/signup?returnTo=<internal path>`, create the account and confirm email in the same browser.
3. Verify automatic claim, profile onboarding and safe return.
4. Refresh and verify bearer restoration; then log out and confirm anonymous identity is created lazily.
5. Separately test existing-account sign-in with an empty anonymous shell and with meaningful anonymous activity. The latter must show `/account/conflict`; Phase 4E must never merge it.

Frontend code uses only `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`. The shared Supabase client owns access-token refresh; the shared Axios client adds the current bearer to FastAPI calls. Never add token logging while debugging.

Username rules are 3–30 ASCII letters, numbers or underscores, with case-insensitive database uniqueness. A lightweight reserved-name policy remains a pre-public-beta requirement.

The Phase 4E live acceptance completed on 20 August 2026: confirmed-email signup claimed anonymous user `339` in place, preserved Interested through onboarding and refresh, enabled Who's Going?, and preserved both states after logout. Existing-account sign-in with meaningful activity correctly stopped at `/account/conflict` without merging users `53` and `339`. JWT verification allows 60 seconds of provider clock skew for `iat`/`nbf`; token expiry remains strict.

Phase 4F live acceptance completed the same day. Verify anonymously that fixture social reads and counts load, then that Who's Going? and Match Board writes open their account prompts. Verify while registered that intent and board posts survive refresh, delete-own succeeds, another user's delete is rejected, duplicate reports are rejected, and a completed fixture returns `409` for new posts while existing content remains readable. Use uniquely identifiable acceptance text and reconcile/remove only those synthetic rows afterward.

Apply the additive Phase 4C session migration before testing claims:

```powershell
cd backend
..\.venv\Scripts\python.exe -c "from database import engine; from pathlib import Path; sql=Path('migrations/20260819_phase_4c_session_revocation.sql').read_text(); c=engine.raw_connection(); c.cursor().execute(sql); c.commit(); c.close()"
```

The migration adds nullable `anonymous_sessions.revoked_at`; existing sessions remain active. Session-token hashing, absolute expiry and last-used tracking remain hardening debt.

## Prerequisites

- PostgreSQL reachable through `DATABASE_URL` in `backend/.env` or the process environment.
- Python dependencies installed in the repository `.venv`.
- Frontend dependencies installed under `frontend/node_modules`.
- Keep API keys and database credentials out of documentation and source control.

## Trusted-beta environment

Production-like deployments must set `NEXT_PUBLIC_API_BASE_URL` explicitly instead of relying on the local browser-hostname/port fallback. Set `TERRACE_ALLOWED_ORIGINS` to comma-separated HTTPS frontend origins, disable private-network development origins, and enable Secure anonymous cookies. The complete non-secret contract is in [Trusted beta acceptance](./beta-acceptance.md).

Fixture timestamps require `backend/migrations/20260820_fixture_datetime_utc.sql`. Review its timezone/sample preflight before applying it. Run `refresh_fixture_states.py` as a dry run before every confirmed write; refreshes bypass cached provider responses so mutable statuses and results cannot remain frozen in the initial import.

## Start the application

From the repository root, the current virtual environment is `.venv` (not `backend/venv`):

```powershell
cd backend
..\.venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

In another terminal:

```powershell
cd frontend
npm run dev -- --hostname 0.0.0.0
```

Desktop URLs:

- `http://localhost:3000`
- `http://127.0.0.1:3000`

## Mobile and LAN development

1. Put the PC and phone on the same Wi-Fi network.
2. Run `ipconfig` and identify the PC's active private IPv4 address.
3. Browse to `http://<IPv4>:3000` from the phone.

`frontend/lib/api.ts` derives the API URL from the browser hostname and port `8000`, so a LAN-loaded frontend calls the same PC over the LAN. FastAPI CORS permits localhost plus `192.168.*.*` and `10.*.*.*` development origins. `frontend/next.config.ts` discovers local IPv4 addresses for Next.js development origins.

## Location behavior

- City/location search and **Use my location** are separate actions that update the same discovery coordinates.
- Browser geolocation works reliably on trustworthy origins such as localhost and deployed HTTPS, subject to permission/device availability.
- A plain HTTP LAN-IP URL is not a secure context, so the browser may block geolocation before application code can receive a position.
- During LAN mobile development, use city search if geolocation is blocked. Do not add IP lookup, hard-coded coordinates or a LAN-only workaround.
- HTTPS deployment should permit real browser geolocation. The UI already distinguishes insecure context, permission denied, unavailable position and timeout.

## Connectivity debugging order

Check one layer at a time:

1. Open frontend `:3000`.
2. Open backend `:8000/`.
3. Open `:8000/session` and confirm a JSON response/cookie.
4. Inspect browser Network requests and their requested hostname.
5. Check `session`, `leagues`, `venues` and `fixtures`/`nearby` statuses.
6. Only then inspect CORS or Next.js development-origin configuration.

Changing between `localhost`, `127.0.0.1` and a LAN hostname creates separate host-scoped cookie contexts. Establish a session on the hostname being tested.

## Checks

```powershell
cd frontend
npx.cmd tsc --noEmit
npm.cmd run build
npx.cmd eslint app/components/InterestedTab.tsx app/components/AccountConversionPrompt.tsx "app/fixture/[fixtureId]/page.tsx"
```

```powershell
cd backend
..\.venv\Scripts\python.exe -m py_compile main.py models.py schemas.py
```

The repository does not yet have a comprehensive automated browser/API regression suite. Test session-sensitive flows with a fresh browser profile and verify Interested, My Stadiums, Who's Going? gating, Match Board reading, city search and location error messages.
