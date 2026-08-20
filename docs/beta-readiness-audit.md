# Phase 5A — MVP readiness and stabilization audit

**Status:** Phase 5B automated stabilization implemented; manual acceptance pending

**Snapshot:** 20 August 2026

**Decision:** **GO for manual acceptance; not yet GO for invitations.** Fixture trust, configuration, false-conflict, dependency and misleading Tip-report blockers have been addressed. Physical-device and deployed-environment acceptance remains mandatory.

See [Trusted beta acceptance](./beta-acceptance.md) for the current gate and minimal analytics contract. The findings below retain the Phase 5A snapshot as historical evidence.

## Phase 5B stabilization addendum — 20 August 2026

- Migrated the reviewed local fixture column to `TIMESTAMPTZ`; representative DB, discovery, fixture, venue, Interested and My Grounds responses resolve to the same UTC instant.
- Added an uncached, dry-run-first mutable fixture refresh. Fresh API-Football data changed exactly 277 existing rows from `NS` to `FT`; post-refresh checks found zero past `NS` beyond six hours and zero future final fixtures.
- Added explicit live/finished/postponed/cancelled presentation; cancelled boards are closed and postponed/cancelled matches are excluded from Worth the Trip.
- Removed read-only telemetry from meaningful anonymous ownership, added its regression test, and retained conflict protection for actual owned activity.
- Added environment-driven public API/CORS/cookie behavior. Production mode defaults private-network origins off and Secure cookies on.
- Removed the unreliable Report Tip action for the trusted beta; fixed missing-tip 404 behavior and centralised relevant frontend API error extraction.
- Reconciled backend dependencies. All 32 backend tests pass.
- Added bounding-box/eager venue filtering to radius discovery. Warm local medians are `/leagues` 7.8ms, 25-mile search 19.5ms, 100-mile search 200.4ms, fixture 14.1ms, Interested 8.8ms and My Grounds 9.8ms. A cold remote-database connection can still add roughly two seconds and must be checked in deployment.
- London is the target geography. One unverified Dave Bryant Stadium coordinate affects three forthcoming matches and remains a reviewed exception rather than an unsafe guess.

This audit assesses the current repository, local API, and loaded PostgreSQL data. It separates observed implementation from recommendations. Counts are a dated snapshot, not architectural constants.

## 1. Executive assessment

Terrace Talk's strongest journey is already coherent:

> DISCOVER → KNOW → CONNECT → ATTEND → REMEMBER → CONTRIBUTE

Discover, fixture, venue, attendance, review, and lightweight social features form a recognisable product rather than a collection of demos. The principal beta risk is not missing scope; it is trust. The same fixture can currently expose different kickoff times on different surfaces, and stale provider statuses leave completed matches looking upcoming. Those defects can undermine every later step in the lifecycle.

Phase 4 identity is suitable for a small, supported cohort once deployment settings and one false-conflict condition are corrected. Match Board authorization is appropriately enforced by the backend. The missing account-merge flow is a broader-beta blocker, but need not block 10 invited testers if onboarding is controlled and support is available.

## 2. Product surface inventory

| Surface | Current purpose | Readiness observation |
|---|---|---|
| `/` | Location/date/radius/multi-league discovery, map, nearby cards, Worth the Trip | Strongest expression of the proposition; query performance and empty/error recovery need hardening. |
| `/fixture/[fixtureId]` | Fixture detail, Interested, Who's Going, Match Board, attendance resolution | End-to-end journey exists; depends critically on correct time/status. |
| `/venue/[venueId]` | Ground information, Terrace Rating, fixtures, tips, visit/review actions | Strong KNOW surface; missing venue handling and fragmented loading can improve. |
| `/my-football?tab=interested` | My Matchdays: future intent, unresolved completed fixtures, attended history | Clear lifecycle concept, but stale statuses prevent correct post-match resolution. |
| `/my-football` | My Grounds, visits, reviews, repeat visits, personal map | Useful personal history; map/statistics can make the product feel tracker-led if overemphasised. |
| `/interested`, `/my-stadiums` | Compatibility redirects | Safe to retain temporarily; document and remove only after link/analytics review. |
| `/signup`, `/signin`, `/auth/*`, `/account/*` | Supabase account UX and in-place anonymous-user claim | Functional Phase 4 foundation; no merge or recovery UX. |
| `/auth-test` | Development acceptance harness | Correctly unavailable outside development; retain only while identity work needs it. |

`frontend/app/components/ProfilePrompt.tsx` has no detected caller. Legacy review compatibility remains in the backend, including `/my-reviews` and review fields coupled to historical visit creation. These are cleanup candidates, not immediate release blockers.

### Technical-debt disposition

| Item | Disposition |
|---|---|
| Read telemetry counted as meaningful owned activity | **Remove before beta** from the conflict predicate; telemetry itself may remain. |
| `/my-reviews`, review/visit compatibility paths, `AwayDayReview.fixture_id` and `visit_date` | **Safe to defer** while current callers and migration history are documented. |
| Five blank review rows | **Needs investigation** to distinguish valid drafts from migration residue before cleanup. |
| Duplicate page-level `/session` work alongside `AuthProvider` | **Needs investigation** with request tracing; consolidate after preserving anonymous initialization guarantees. |
| Unreferenced `ProfilePrompt.tsx` and possible legacy components/services | **Safe to defer** deletion until import/build history is checked. |
| `/auth-test` | **Safe to defer** because production returns `notFound`; retain only as long as live identity acceptance needs it. |
| Validator CLI behavior and ad-hoc audit scripts/reports | **Needs investigation** and a supported command contract before beta operations. |

## 3. Journey audit

| Journey | What works | Principal risk | Gate |
|---|---|---|---|
| Discover a match | Explicit consolidated search, shared map/card origin, filters, fixture map and cards | Radius discovery does broad ORM work and Python distance calculations; result caps need to remain visible | Should fix/monitor |
| Know the ground | Venue detail, ratings, tips, fixtures, current canonical venue identity | Coordinate gaps omit fixtures from discovery; invalid venue/city examples require review | Must target beta areas |
| Express intent | Anonymous Interested persists; Who's Going is registered-only | Incorrect time/status can misclassify intent; view telemetry can trigger false account conflict | Must fix |
| Connect | Board readable anonymously; registered writes; own-delete/report-other | Tip reporting is unreliable/abusable; no operator moderation surface | Must fix or remove broken control |
| Attend | Fixture-linked attendance is idempotent and independent of review | Past `NS` fixtures never reach the decision state | Must fix |
| Remember | Manual and fixture-linked visits, repeat visits, personal map | Five blank legacy reviews remain; unplottable grounds need transparent handling | Should clean |
| Contribute | One structured review per venue and separate practical tips | Tip abuse controls and error contracts are weak | Must/should fix |

The Phase 3.5 lifecycle remains the correct manual test model. Every beta build should retest one complete new-user journey and one repeat-visit journey, not merely individual endpoints.

## 4. UX clarity and product language

- Page identity is generally clear: Discover plans a matchday, My Matchdays joins intent with attendance, and My Grounds records football history.
- Interested and Who's Going are distinct controls, but testers should still be asked whether they understand **Interested = my plan** and **Who's Going = open to meeting supporters** without explanation.
- My Grounds cards and the score editor remain information-dense on narrow screens. Score buttons are approximately 40px, below the preferred 44px touch target.
- The My Grounds search field relies on placeholder text and needs a programmatic label.
- Match Board's single composer path, separated character count, and closed-board language are suitable for beta.
- Loading and inline errors exist on major surfaces, but several request handlers can pass an object-shaped backend `detail` directly into React text state. Identity/session failures could therefore produce an invalid React child rather than a useful message.
- Empty discovery explains that no fixtures were found, but gives limited recovery guidance. Map tile/network failure has no dedicated state.
- Postponed and cancelled fixtures are not given trustworthy, supporter-facing states; raw provider status risks leaking into presentation.
- Current metadata describes Terrace Talk as tracking visited stadiums. Lead with finding football to attend; keep personal history as the retention layer.

Approved vocabulary remains useful when contextual: **Terrace Rating**, **What the Terrace Says**, **From the Terrace**, and **Make It One of Yours**. Internal terms such as `open_to_meet`, `fixture-linked`, and `visit-derived` should not leak into user copy.

## 5. Mobile and accessibility audit

Code-level responsive review supports 375–430px layouts: primary actions become full-width, horizontal fixture cards snap, maps have list/card alternatives, and the Match Board counter is visually separate from its action. A physical-device pass is still required before invitations.

Must-check on real devices:

- Discovery editing, map gestures, Search This Area, popups, and dense markers.
- Long club, venue, username, and post text at 375, 390, and 430px.
- Keyboard order and visible focus through account gates, dialogs, board controls, and review forms.
- Screen-reader names for marker actions and pressed/selected controls.
- 44px targets for score selectors and other compact controls.
- Zoom at 200%, reduced motion, high contrast, tile failure, and slow-network loading.

State is generally not conveyed by colour alone: selected social actions use explicit labels/checks and marker visits retain a check badge. The non-modal account prompt has dialog semantics but no explicit focus/escape treatment; verify rather than redesign before beta.

## 6. Data integrity and fixture trust

### Critical timestamp inconsistency

`fixtures.fixture_date` is a PostgreSQL `timestamp without time zone`. The database timezone is `America/New_York`; ingested provider-aware values are stored as naive local values. `/nearby` reconstructs UTC in SQL, while fixture social, My Matchdays, venue fixtures, and My Grounds serialize raw ORM timestamps.

Observed examples:

| Fixture | Stored value | Reconstructed UTC |
|---|---:|---:|
| 1564254, England | 20 Aug 15:00 | 20 Aug 19:00 |
| 1494118, Sweden | 20 Aug 09:00 | 20 Aug 13:00 |
| 1490135, USA | 20 Aug 14:30 | 20 Aug 19:30 |

The user can therefore see different kickoff times for one fixture, and near-midnight matches can acquire the wrong attendance date. Establish one UTC storage/serialization contract and add parity tests across every fixture response before beta.

### Status freshness

The snapshot contains 9,117 fixtures. **277 past fixtures still have `NS` status** (12–19 August 2026), including 267 linked to venues. The affected set spans MLS and multiple English and US leagues. Current UI treats only `FT`, `AET`, and `PEN` as completed, so these fixtures remain upcoming and never reach Did You Go.

The importer can update status and score, but no recurring refresh process was identified. Add an operational refresh covering recent past, today, and the useful future window. A short post-kickoff grace is reasonable; old `NS` must fail the beta preflight.

### Dated database snapshot

| Check | Result |
|---|---:|
| Fixtures / venues | 9,117 / 1,092 |
| Users / visits / reviews | 47 / 23 / 19 |
| Interested / board posts / tips | 8 / 1 / 5 |
| Fixtures without linked venue | 277 (Sweden 245; USA 32) |
| Linked fixture rows whose venue lacks coordinates | 1,367 |
| Venues without coordinates / invalid coordinates | 146 / 0 |
| Duplicate provider venue IDs | 0 |
| Duplicate natural fixtures | 0 |
| Duplicate user/venue reviews | 0 |
| Duplicate fixture attendances | 0 |
| Reviews without a visit | 0 |
| Blank legacy reviews | 5 |

Existing country validation reported complete fixture venue linking for England, with gaps concentrated in Sweden and USA. Coordinate coverage remains materially weaker, especially Sweden. This need not block a geographically scoped trusted beta if affected areas and omissions are disclosed.

A specific plausibility concern was found: a venue returned for a London search had `city = London` but coordinates near Shrewsbury. Valid numeric ranges are insufficient; beta cities need coordinate/city plausibility sampling. Do not merge or correct venues using name similarity alone.

## 7. Data-quality gate and refresh process

Before each beta build:

1. Refresh teams, venues, fixture kickoffs/statuses/scores for at least the last 7 days, today, and the next 60–90 days.
2. Run the existing country data-quality validator and save a dated machine-readable report.
3. Fail on duplicate provider IDs, duplicate natural fixtures, orphan references, invalid coordinates, future completed fixtures, or past `NS` beyond the agreed grace period.
4. Report unresolved venue links and missing coordinates by country/league; manually sample intended beta cities.
5. Verify one fixture's timestamp and status across discovery, fixture detail, venue fixtures, My Matchdays, and attendance.
6. Sample postponed/cancelled matches and old/current venue aliases.
7. Record every manual coordinate or venue override as a reviewed exception.

The validator's current command interface should be made explicit: invoking it with `--help` currently runs the audit rather than showing normal CLI help.

## 8. Performance and operational review

Local timings are directional, not production load tests:

| Request | Observed response |
|---|---:|
| `/leagues` | ~2.17s |
| `/nearby`, London, 25mi, one week | ~295ms |
| `/nearby`, London, 100mi, extended range | ~1.03s; 423 matches, capped response |
| Map viewport | ~229ms; ~101KB / 210 results |
| Venue/tip detail calls | ~13–14ms |

Radius discovery loads matching fixture rows before Python geodesic filtering, accesses `fixture.venue` without an explicit eager load, and casts `fixture_date` to `Date`, reducing index usefulness. `/venues` similarly filters all venues in Python. Prioritise eager loading and range/bounding-box filtering; then measure before pursuing deeper optimisation.

The frontend establishes identity in both its auth provider and page-level flows, and several pages wait for `/session` before fetching otherwise parallel data. Fixture social reads also write `fixture_view` and `board_view` events on every refresh. These add latency, database writes, and distorted activity counts.

No caching/CDN strategy, production health check, structured logging, alerting, backup-restore rehearsal, or fixture-refresh scheduler is documented as operationally active. A 10-person beta needs at minimum uptime/error visibility, database backups, a refresh runbook, and a named responder.

## 9. Authentication and account readiness

Current strengths:

- Supabase bearer verification checks algorithm, issuer, audience, expiry, and blocked/deleted/merged user state.
- New accounts claim the existing anonymous `users.user_id`, preserving owned Terrace Talk data.
- Social writes resolve server-side identity and do not trust client user/profile fields.
- The development acceptance harness is excluded from production.

Pre-beta issues:

- `_has_meaningful_activity` counts `SocialEvent`, while merely reading fixture social writes view events. An anonymous fixture view can therefore produce an alarming account-conflict state on later sign-in despite owning no meaningful data. Exclude read telemetry from the conflict predicate.
- Anonymous session cookies are long-lived, stored server-side without expiry/last-used lifecycle, and set with `secure=False`. Production HTTPS must use Secure cookies and an explicit retention/revocation policy.
- CORS is configured for local/private-network development, while the API client derives `browser-hostname:8000`. Add explicit environment-driven public web/API origins before remote beta.
- No product password-recovery flow was identified. Manual recovery can support 10 invited users; a broader beta needs self-service recovery.
- Account merge is not implemented. For 10 trusted testers, start from clean/in-place claim journeys and provide manual support. Broader recruitment should wait for a safe merge decision and UX.

The live Phase 4 acceptance already demonstrated claim, persistence, sign-out, registered Who's Going and Match Board operations, anonymous gates, and completed-board `409 This Match Board is now closed` enforcement.

## 10. Social safety and moderation baseline

Match Board currently has the right minimum authorization shape: anonymous read, registered-only post, delete-own, report-other, duplicate-report protection, and blocked identity enforcement. Completed boards remain readable and reject writes server-side.

The weak point is tips. Report Tip is known not to work reliably in product UX, and helpful/report mutations lack equivalent authentication, rate, and ownership controls. A missing tip can also return an error object with HTTP 200. Before even a trusted beta, either make reporting truthful and operable or remove/disable the broken report control; do not imply safety tooling exists when it does not.

For 10 invited testers, a named contact and documented database removal/suspension procedure are an acceptable temporary operator path. Broader beta requires a moderation queue, operator actions/audit log, abuse rate limits, username/impersonation rules, and a transparent reporting response process. Do not build reactions, followers, feeds, or general-forum features.

## 11. Error resilience

Priority improvements:

- Centralise frontend extraction of string and `{code, message}` API errors.
- Return `404` for a missing venue rather than a successful null response.
- Return accurate 4xx errors for missing tips and failed helpful/report operations.
- Distinguish offline/backend unavailable, expired identity, no results, and unavailable map tiles.
- Keep the currently useful geolocation distinction: insecure context, denied, unavailable, and timeout, with city search as fallback.
- Preserve loading termination and prevent repeat writes while a request is active.

The API/database path fails safely on most social conflicts, but user-facing degradation is inconsistent. Error-shape normalisation should be in the first stabilization sprint.

## 12. Dependency and configuration health

- Frontend production dependency audit reported **0 vulnerabilities**.
- `pip check` failed because SQLAlchemy 2.0.51 declares `greenlet` and it is absent. Reconcile and lock the backend environment before beta even though current synchronous paths run.
- Verify Supabase redirect allowlists, email templates, rate limits, production secrets, public/private environment boundaries, and HTTPS origins without recording secret values.
- Add a deployment smoke check for web, API root, session, leagues, venue, fixture, authenticated ownership, and closed-board rejection.

## 13. Instrumentation for the first 10 users

Use minimal, pseudonymous first-party events rather than a broad analytics suite:

`discover_opened`, `search_completed`, `search_area_completed`, `fixture_viewed`, `venue_viewed`, `interested_added/removed`, `whos_going_enabled/disabled`, `board_post_created`, `attendance_confirmed/removed`, `ground_visit_added`, `review_completed`, `tip_created`, `signup_started`, `account_claimed`, `signed_in`.

Useful properties are internal pseudonymous owner/session, fixture/venue/league/country IDs, source surface, search method, coarse radius/date-window buckets, result count, and viewport class. Do **not** capture email, provider subject, exact coordinates, raw location queries, board text, or tip text. Define short retention for anonymous location/search events and derive D1/D7 return from the pseudonymous identity.

Analytics cannot answer the core causal question alone. Add a brief interview or optional post-attendance prompt:

> Did Terrace Talk help you find a match you would not otherwise have attended?

Record a small categorical outcome only if the supporter chooses to answer.

## 14. USP and scope guardrails

### Strongest USP

Terrace Talk is most distinctive when it helps someone discover a viable live match, understand the ground and matchday, connect only when useful, and preserve the resulting football memory. Discover and ground knowledge should lead; personal history should reward attendance rather than define the whole product.

### Potentially confusing or generic

- A map/stats-first My Grounds presentation can resemble a stadium tracker.
- A Match Board without strong matchday utility can resemble a generic forum.
- Metadata centred on “track stadiums” undersells discovery.
- Similar kicker/panel treatments across every surface can blur purpose even when visual consistency is good.

### Explicitly defer

Account merge implementation until its policy is approved; DMs; followers/friends; reactions; social feeds; bottom navigation; badges, completion mechanics, leaderboards, new tracking/history scope; broad visual redesign; new providers; speculative AI recommendations; and additional Terrace knowledge features. Stabilise the existing loop first.

## 15. Beta blocker matrix

| Finding | Severity | 10 trusted users | Broader beta |
|---|---|---|---|
| Inconsistent fixture timezone contract | Critical | Blocker | Blocker |
| Past fixtures retained as `NS` | Critical | Blocker | Blocker |
| Production API/CORS/cookie configuration not ready | High | Blocker for remote beta | Blocker |
| Anonymous read telemetry triggers account conflict | High | Blocker | Blocker |
| Broken/weak Tip reporting contract | High | Fix or remove control | Blocker |
| Backend dependency inconsistency (`greenlet`) | High | Blocker | Blocker |
| Postponed/cancelled supporter states | High | Should fix | Blocker |
| Object-shaped errors rendered inconsistently | High | Should fix | Blocker |
| Missing account merge | High | Supported workaround | Blocker |
| Radius-query/N+1 inefficiency | Medium | Measure/optimise | Scale blocker |
| Coordinate/link gaps outside target areas | Medium | Scope and disclose | Coverage blocker |
| Missing self-service recovery | Medium | Manual support | Blocker |
| Accessibility/device verification | Medium | Required manual gate | Required |
| Legacy blank reviews/dead compatibility code | Low | Defer | Cleanup |

### Severity summary

- **Critical:** inconsistent fixture timestamps; completed matches retained as upcoming.
- **High:** remote deployment/session hardening, false account conflict, unreliable Tip reporting, backend dependency inconsistency, postponed/cancelled handling, inconsistent error shapes, and missing merge/recovery for a broader beta.
- **Medium:** broad-query performance, geographic coordinate/link gaps, physical-device/accessibility verification, dense My Grounds presentation, map/network empty states, and duplicated identity requests.
- **Low:** tracker-led metadata, minor copy choices such as “Matches you're considering,” blank legacy/dormant compatibility cleanup, and unreferenced components.

## 16. Smallest remediation sprint

1. Define/migrate the fixture UTC contract and add cross-endpoint time/status tests.
2. Refresh mutable fixture data; introduce the dated preflight gate and explicit postponed/cancelled presentation.
3. Add environment-driven web/API origins, production CORS, HTTPS/Secure cookie behavior, and deployment smoke checks.
4. Correct meaningful-activity detection so view telemetry cannot cause account conflict.
5. Make Tip reporting safe and truthful, or temporarily remove its control; document the beta operator path.
6. Lock backend dependencies; normalise API errors and missing-resource status codes.
7. Eager-load/filter discovery efficiently, then record production-like latency and payload baselines.
8. Complete physical 375/390/430px, keyboard, screen-reader, slow-network, and full supporter-journey acceptance.
9. Add only the minimal event schema and optional discovery-outcome question above.

No major visual redesign or feature expansion belongs in this sprint.

The next product-discovery phase after stabilization should be the **“Hutnik Test” / matchday knowledge feasibility spike**: determine whether Terrace Talk can give a supporter in an unfamiliar place enough trustworthy, practical knowledge to choose and attend a less-obvious match. It should be a research/prototype spike after the 10-user gate, not Phase 5A implementation and not a commitment to a broad new content system.

## 17. Readiness scorecard

Scores are out of 10 for the current snapshot, before remediation.

| Dimension | Score | Rationale |
|---|---:|---|
| Core journey completeness | 7 | The full supporter lifecycle exists, including repeat visits and optional contribution. |
| UX clarity | 7 | Product surfaces and actions are mostly coherent; edge/error copy and density remain. |
| Data reliability | 4 | Timezone divergence and stale statuses directly threaten supporter trust. |
| Mobile/app-first usability | 6 | Responsive code is credible; physical accessibility/device acceptance is outstanding. |
| Authentication readiness | 6 | Secure central identity and in-place claim work; conflict false positives, deployment config, recovery, and merge remain. |
| Social safety | 5 | Match Board baseline is sound; tip reporting and operator tooling are weak. |
| Performance | 5 | Small queries are adequate; leagues and broad discovery expose avoidable database/application work. |
| Error resilience | 5 | Many expected states are handled, but error contracts and offline/resource failures are inconsistent. |
| USP clarity | 7 | Discovery-to-memory loop is distinctive; tracker/forum signals need restraint. |
| **Overall MVP readiness** | **5/10** | Coherent product, but two critical trust defects make the current build a no-go. |

## 18. Exit criteria and recommendation

Invite the first 10 trusted users only when:

- all must-fix matrix items are closed;
- the data preflight passes on a fresh provider refresh;
- one fixture has identical time/status across all surfaces;
- intended beta cities pass coordinate/link spot checks;
- registered, anonymous, completed-board, attendance, review, and tip journeys pass on real mobile devices;
- monitoring, backups, moderation contact, recovery/support, and rollback ownership are named;
- synthetic acceptance data is reconciled or clearly tagged.

After that gate, run a small, observed beta with explicit consent for feedback and a short feedback loop. Do not expand the cohort merely because the app stays online: expand when people can reliably discover, understand, attend, and remember real football without staff explaining the product or correcting its data.

### Prioritised disposition

**Must fix before a 10-user beta:** fixture UTC parity; recent fixture status refresh/preflight; production origins/CORS/Secure-cookie configuration; false activity conflict; Tip reporting truthfulness; backend dependency reconciliation.

**Should fix before a 10-user beta:** postponed/cancelled presentation; error normalisation and correct 404/4xx responses; physical mobile/accessibility pass; target-city coordinate QA; measured discovery query improvement; basic monitoring, backup, moderation, and support runbooks.

**Safe to defer:** account merge with a controlled onboarding workaround; self-service recovery with manual trusted-user support; compatibility/dead-code cleanup; blank-review cleanup after investigation; richer moderation administration; analytics provider selection; broad redesign; and every explicitly deferred social/tracker feature.
