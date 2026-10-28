ï»¿# Matchgoer iOS feasibility spike

Local proof only; do not ship or enable hosted configuration from this directory.

- `npm ci` here installs Capacitor and esbuild tooling. Install the unchanged frontend's locked dependencies in `../frontend` too.
- `npm run build` directly imports existing frontend screens, CSS and public assets into `dist`. Only explicit synthetic API/auth endpoints are compiled. No remote `server.url`, Next server or real credentials.
- `npx cap add ios`, then `npx cap copy ios`, generate a local iOS project. Generation/copy is not compilation, signing, iPhone installation or TestFlight acceptance.
- `node --test native-auth-proof.test.mjs` tests injected/mocked system-auth protocol boundaries; it is not a wired native OAuth plugin.
- `compat/*` implements only the small Next client APIs needed by this proof. These adapters are experimental, not a proposed second general routing framework. Unsupported account setup/recovery routes require shared-screen adapters before production.
- `main.tsx` composes existing providers, navigation and screen components. Business rules, permissions and API implementations stay in shared frontend files.
- Analytics scripts and live Google initiation are intentionally disabled in the spike. Fonts use existing CSS fallbacks rather than Next font optimisation. This is not final branding/UX acceptance.
- Native HTTP-only cookies, system-browser return, keychain storage, file picker and device behaviour remain physical-iPhone gates.

Detailed evidence and build/spending gates: `reports/ios-feasibility-spike-20261028/` in the repository root. No CI workflow is activated, no paid services are used, and the existing website is unchanged.


P0 connectivity correction (28 October 2026, local review only)
----------------------------------------------------------
The TestFlight build 1 packaging proof contains synthetic service origins. It is not a beta-connected application.
Every bundle now requires an explicit target:
  $env:MATCHGOER_NATIVE_TARGET='synthetic'; node build.mjs
For a reviewed beta candidate, set MATCHGOER_NATIVE_TARGET=beta and supply only the existing public NEXT_PUBLIC_API_BASE_URL, NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY and NEXT_PUBLIC_GEOAPIFY_API_KEY through the build process. No server/service-role credentials belong in the app. The build rejects absent settings, synthetic beta values, unexpected API/Auth origins and non-public Supabase keys. Native Google and analytics remain disabled pending their native acceptance work.

Do not upload the old pinned native-input.zip as a connectivity fix: it remains the immutable build-1 proof. After review, regenerate native assets from the configured bundle, retain the location purpose string, verify checksums, and update the existing pipeline's pinned archive hash and build number under separate upload approval. No workflow is run by this correction.

Live Railway CORS currently rejects capacitor://localhost. Adding that exact origin to the existing allowlist requires founder approval before any hosted change. Do not use wildcard credentialed origins or substitute beta.matchgoer.com as the local app origin.

The location purpose string is present in the generated local iOS project, but WKWebView location permission/error behaviour still requires physical-iPhone testing. No geolocation bridge was installed. Guest HTTP-only cookie persistence and guarded transfer are unproven across this cross-site native origin; do not weaken SameSite/CSRF protections or copy cookie values into JavaScript. Native system OAuth/deep-link return is not wired and remains a separate boundary.

Build 2 approval: beta public service configuration was verified against the current hosted JavaScript, regenerated into native-input.zip, and pinned in the existing validation scripts. Only the approved exact native CORS origin was added. The shared web application, Supabase configuration and cookie policy are unchanged. Version remains 0.1.0; build increases to 2. This is a connectivity acceptance build, not proof of native OAuth or guest-cookie continuity.
