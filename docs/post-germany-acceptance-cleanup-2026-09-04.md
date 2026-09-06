# Post-Germany acceptance cleanup — 2026-09-04

## Directions audit and hosted correction

- Scope checked: all 81 published England and all 17 published Germany Before-the-Match records.
- Already deterministic: 29 England and 16 Germany records. Each already contained a sufficiently distinctive named place plus locality, ground, or full-address context.
- Corrected: 52 England and 1 Germany `maps_destination` values. No recommendation identity, display name, supporting copy, classification, evidence, or other KNOW field changed.
- Exact guarded before/after manifest: `backend/before_match_destination_cleanup.py` (`CORRECTIONS`).
- England spot IDs 36–85 changed exactly from the bare display name to `display name, canonical ground name, canonical ground city`. This preserves each approved on-ground venue/area and supplies deterministic location context.
- AFC Wimbledon spot 4: `The Phoenix, London` → `The Phoenix, Cherry Red Records Stadium, Plough Lane, London SW17 0NR`.
- AFC Wimbledon spot 5: `South Stand Fan Zone, London` → `South Stand Fan Zone, Cherry Red Records Stadium, Plough Lane, London SW17 0NR`.
- 1. FC Köln spot 94: `Stadtwaldgarten, Venloer Straße 1031, 50829 Köln` → `Stadtwaldgarten, Aachener Straße 701, 50933 Köln`.

Fresh backup: `backups/hosted/matchgoer-hosted-pre-directions-cleanup-20260904T072917Z.dump`; 738,587 bytes; SHA-256 `0EA9135D8363E5E3C2EFAF47DE64CD4813DCAD5651EC6F5A57F02F2147AB811A`; PostgreSQL archive listing passed with 266 entries.

The protected transaction updated 53 rows and deleted none. Independent read-only reconciliation returned `EXACTLY_PRESENT`: 53 exact corrected values, 0 pending, unchanged table counts, and 0 unrelated changes. Representative live guide responses produced the corrected encoded destinations for AFC Wimbledon, Burnley, and Köln; Elversberg continued to return an empty Before-the-Match list.

## Fixture-page cleanup

Diagnosis: the standalone KNOW card repeated the header's ground identity and competed with THE GROUND through a second ground-detail link. It also fetched venue coordinates solely to build the removed stadium Directions action.

Implemented change: remove the standalone KNOW card and its extra venue-coordinate request. THE GROUND remains the single route through `Explore the ground →`. When approved Before-the-Match content exists, a compact `Before the match · N place(s)` signal appears within THE GROUND identity block. No signal appears when the list is empty. All Interested, meeting, attendance, review, board, and DECIDE behavior is untouched.

Representative fixtures selected read-only for acceptance coverage:

- Burnley–Southampton, fixture 1563613: one Before-the-Match place; compact signal shown by the implemented conditional.
- 1. FC Köln–SC Paderborn 07, fixture 1575443: one place and corrected Stadtwaldgarten destination.
- SV Elversberg–Werder Bremen, fixture 1575445: zero places; no empty signal/card.

## Verification

- Frontend guide tests: 10 passed.
- Frontend fixture/discovery tests: 42 passed, including the new one-route/no-duplicate-card acceptance assertion.
- Frontend pending-auth tests: 6 passed; auth-flow tests: 4 passed.
- Targeted ESLint: passed.
- Next.js 16 production build with webpack: passed, including TypeScript and all 14 routes. The default Turbopack build was not usable with the temporary cross-worktree dependency junction; this was an environment-only limitation and the junction was removed afterward.
- Backend regression: 60 passed, 2 skipped because optional prior-candidate paths were not supplied.
- The separate legacy England Batch 2 artifact-gate class could not start because its v4 artifact is absent from this worktree; this is unrelated to the cleanup and its shared population contract tests passed in the 60-test run.

No editorial recommendation, Great Support, Tickets/Entry, canonical team/venue identity, club-venue, fixture, schema/migration, THE GROUND page, or unrelated Mapbox changes were made.

## Status

**POST-GERMANY ACCEPTANCE CLEANUP PASSED**
