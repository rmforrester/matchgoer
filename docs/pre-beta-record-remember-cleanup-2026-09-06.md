# Pre-beta Record + Remember cleanup — 2026-09-06

## Diagnosis and implementation

- My Matchdays used oversized cards and formal confirmation copy for a binary attendance question. Pending rows are now compact, “Yes, I was there” remains primary, “Didn't go” is secondary, and either answer removes the row optimistically. A yes continues to create/promote the corresponding `venue_visits` row through the existing attendance endpoint.
- My Grounds mixed aggregate history with venue-level database statistics and equal-weight maintenance actions. Aggregate grounds/cities/countries/matchdays remain; cards now show ground, location, “Last there” or “Date not remembered”, one View Ground action, and secondary visit controls. Empty ratings are no longer card furniture.
- Lifetime is the default timeframe. 30 days, 3 months, 1 year, and Lifetime filter the same visit set used by aggregate counts, map, and list. Undated visits remain in Lifetime and are excluded from finite windows rather than receiving invented dates.
- Visited map shields/checks are replaced by small blue dots with the existing usable Leaflet hit target. Popups identify the ground, optionally show the last visit, and retain View Ground.
- Add a Ground is reachable prominently below the page heading. The existing search/record flow remains, with optional date-based nearby-fixture selection.
- Existing visits now expose visit IDs/dates/fixture IDs. A small authenticated PATCH route attaches, changes, or removes a fixture after creation, validating ownership, venue identity, and duplicate attendance. The existing nullable `venue_visits.fixture_id` is sufficient; no migration or schema change is required.
- Ground pages fetch approved venue/team DECIDE facts and show a compact WHY GO treatment only when a genuine published reason exists. Dortmund returns its approved Exceptional Support reason; Bayern returns no reason. KNOW remains ahead of personal/community/upcoming content.
- Empty community states are progressively disclosed: no rating is a small invitation; no tips is a lightweight Add a tip prompt; populated modules retain their full presentation. Zero interested and zero thread counts are suppressed.
- Completed fixtures now say “You were there” with ground/date and direct Rate/Add tip links. Kickoff surfaces explain that times use the current device timezone; JavaScript `Date` continues to provide timezone and DST conversion.

Representative copy changes include “Confirm your recent matchdays” → removal of the instruction, “Attendance recorded” → “You were there”, “This match is in your attended history…” → ground/date, and “No Terrace Rating yet” → a small invitation.

## Verification

- Frontend tests: 67 passed (6 pending-auth, 4 auth-flow, 45 discovery/UX source contracts, 10 guide, 2 timeframe).
- Targeted ESLint: passed.
- Next.js 16 webpack production build: passed; TypeScript passed and all 14 routes built. Webpack is the viable builder in this worktree because Turbopack rejects the temporary cross-worktree dependency junction.
- Backend focused tests: 43 passed. Broader relevant regression: 60 passed, 2 optional candidate-path skips. Python compilation passed.
- Hosted read-only Ground DECIDE path: approved Dortmund reason present; unsupported Bayern state empty. No hosted writes were performed in this task.
- Long ground/city/team content uses existing `min-w-0` and `break-words` protections; the production type/build gate passed.

## Manual mobile acceptance remaining

After deployment, visually exercise: multiple Did You Go rows and yes/no resolution; a dated, undated, single-visit, and multiple-visit ground across all four timeframes; marker popup/View Ground; Add Ground with and without a fixture; retrospective attach/change/remove; populated and empty Ground community states; approved and absent WHY GO; completed and upcoming fixtures; zero social activity; and representative long names. These are visual/interaction acceptance checks, not known blockers.

No KNOW/DECIDE editorial data, Great Support facts, Before-the-Match destinations, canonical identities, fixtures, club venues, or hosted data changed. No migration was added and no unrelated Mapbox work was touched.

## Verdict

**PASS — PRE-BETA UX CLEANUP READY FOR MANUAL ACCEPTANCE**
