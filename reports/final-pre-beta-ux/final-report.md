# Final pre-beta Fixture / Venue / My Grounds UX sweep

## Verdict

PASS. The bounded Fixture / Venue / My Grounds pre-beta UX sweep is closed.

## KNOW copy

- Serving inventory: 48 published facts.
- Updated: 11 `know_facts.content` values.
- Unchanged: 37 published facts, with identical pre/post fingerprint `2ba394b603b1e8a7e4d777fe21e0f210`.
- Evidence: 63 rows, with identical pre/post fingerprint `ff9382981fcc32e81a1e7b975cc81e25`.
- Inserts/deletes: 0/0.
- Local and hosted post-write dry runs: 0 pending mutations; all 11 rows already correct.
- Palermo public copy no longer contains `COPA90`. Napoli and Udinese copy now states the approved insight directly.

Updated keys: `IT-1687-SUPPORTERS-01`, `IT-492-CLUB-01`, `IT-492-SUPPORTERS-01`, `IT-494-CLUB-01`, `IT-497-MATCHDAY-01`, `IT-509-MATCHDAY-01`, `IT-509-SUPPORTERS-01`, `IT-522-SUPPORTERS-01`, `IT-527-CLUB-01`, `IT-9534-CLUB-01`, `know-v1-proof:real-oviedo:matchday`.

The frozen ledger and manifest retain the exact before/after copy, canonical owner fields, module, evidence binding, and reason for every update. The hosted backup export was explicitly waived; the manifest and pre/post receipts provide exact recovery values.

## Frontend

- Fixture: retained WHY THIS MATCH and KNOW; tightened KNOW body leading on mobile; removed the duplicate BTM place count and its extra guide request; replaced the Terrace Roll Call card with a light count and safety note; simplified Match Board explanatory copy.
- Venue: removed venue-page WHY GO presentation and request; removed the `KNOW BEFORE YOU GO` / `THE ESSENTIALS` wrappers; retained BEFORE THE MATCH with its frozen subtitle, Tickets & Entry, other ground essentials, Your Visit, contribution prompt, and Upcoming Fixtures.
- My Grounds: retained the header, timeframe controls, statistics and map; reduced card heading/action weight; removed per-card Add a visit; made populated state use one toggled top add flow; made empty state use one direct search/add flow and removed optional-review copy.
- Shared header: unchanged.
- My Matchdays: unchanged.

## Validation

- Focused frontend tests: 81/81 passed.
- TypeScript: passed.
- ESLint: passed with zero errors or warnings.
- Production build: passed.
- `git diff --check`: passed.
- Responsive hosted Chrome checks at 320, 375, 390 and 430px: exact viewport widths, document width equal to viewport width, no horizontal overflow.

Representative hosted acceptance used Napoli v Bologna (`fixture_id=1550123`) and Stadio Diego Armando Maradona (`venue_id=23102`). Fixture composition contained two WHY reasons, club and supporter KNOW, one BTM and Ground Essentials. WHY remained prominent; revised KNOW and Match Board copy served; BTM count and Terrace Roll Call were absent. The venue retained BEFORE THE MATCH, Tickets & Entry and Add to My Grounds while WHY GO and redundant wrappers were absent. Anonymous My Grounds showed the single direct empty flow. The populated branch and My Matchdays DID YOU GO / PAST MATCHDAYS branches remain protected by focused deployed-source tests; no account visit data was mutated for acceptance.

## Git and deployment

- Starting `origin/master`: `3f429cdec6a6ea31848cbd774b17b0c9e52523b1`.
- Frontend/tooling commit: `ad716306d4bedfb81004b5d704b56178c1b27863`.
- Push: successful to `origin/master`.
- Vercel beta: HTTP 200, deployed content verified, request/deployment edge identifier `iad1::iad1::5npjs-1789073333427-f5213b0629dc`, status Ready.
- Railway API: HTTP 200 `{"status":"ok"}`, server `railway-hikari`, status healthy. No application backend behavior changed.
- Database changes: exactly 11 hosted and 11 local `know_facts.content` updates; no other database fields or tables changed.
