# Italy V1 comprehensive publication report

Status: hosted data published and reconciled; persistent importer commit awaits push authorization.

## Structural

- Senior denominator: expected 78, actual 78.
- Simple repairs: 36 HOME/CURRENT inserts.
- Compound repairs: 2.
- Alcione: canonical Stadio Ferruccio, local venue 24315, hosted venue 24282; API-Football provider venue 2772; team and exactly 19 fixtures corrected.
- Union Brescia: canonical Stadio Mario Rigamonti, venue 23440; team assignment and HOME/CURRENT relationship corrected.
- Remaining blockers: 0.

## BTM

- Serving clubs before: local 34, hosted 33.
- Serving clubs after: expected 35, actual 35.
- Ascoli: preserved locally; inserted hosted.
- Lecco: Bar Stadio inserted locally and hosted as SUPPORTER_SPOT; BTM Directions suppressed.
- Palermo: normalized in place to `SiamoAquile Bar&Store / Stadio Renzo Barbera`, CLUB_MATCHDAY_VENUE; no duplicate destination.
- Avellino: Old Style Pub preserved with business status UNKNOWN and remains non-serving.
- Hosted Directions: 6 active, 31 suppressed/non-serving across 37 stored Italy BTM rows. No ambiguous active Directions identified.

## KNOW

- Existing Atalanta facts: 2, unchanged.
- Approved new facts: 26, published with 26 accepted evidence rows.
- Total facts: expected 28, actual 28.
- Clubs with KNOW: expected 20, actual 20.
- Intentional omission: IT-895-SUPPORTERS-01, EVIDENCE_NOT_RECOVERED. Como retains IT-895-CLUB-01.
- Module counts for the 26 new facts: CLUB 15; SUPPORTERS 7; MATCHDAY 3; DONT_MISS 0; GOOD_TO_KNOW 1.
- BEFORE THE MATCH remains BTM and is not counted in KNOW.

## Hosted acceptance

Read-only API acceptance passed for AS Roma, Atalanta, Como, Napoli, Udinese, Venezia, Avellino, Cesena, Catanzaro, Palermo, Juve Stabia, AlbinoLeffe, Arzignano Valchiampo, Giana Erminio, Trento, Reggiana, Virtus Entella, Livorno, Spezia, Torres, Alcione, Union Brescia, Ascoli, Lecco, and Bologna as an intentional no-KNOW control. Exact modules and BTM visibility matched for every fixture; all responses were HTTP 200.

## Regression and database actions

- DECIDE, WHY THIS MATCH, non-Italy BTM, non-Italy KNOW, Ground Essentials, Discover, user content, and unrelated identities were fingerprint-protected and unchanged.
- Hosted inserts: 38 club_venues; 1 venue; 2 venue_names; 1 venue_provider_ref; 2 pre_match_spots; 2 pre_match_spot_evidence; 26 know_facts; 26 know_fact_evidence.
- Hosted updates: 2 teams; 19 fixtures; 1 pre_match_spot.
- Deletes: 0.
- The post-publication dry run reports zero mutations.
- The immediate first post-commit read briefly observed 12 relationship rows through stale visibility; individual row checks and the subsequent full reconciliation found all 38 and returned zero pending mutations.

## Backups and receipts

- Local backup: `backups/italy-v1-local-before-20260910T195334Z.dump`; SHA-256 `923fef76efab3e49cd86cdc015e6e65ed0f70a60acc84ac0d71354010ad2c7b7`.
- Hosted backup: `backups/italy-v1-hosted-before-20260910T195614Z.dump`; SHA-256 `a8836e6471f1a40e291d0cc874e31fc490df75bd8514ab8ed0e949c0eac36ffe`.
- Local receipt: `reports/italy-v1-publication/local-publication-receipt.json`.
- Local idempotence: `reports/italy-v1-publication/local-idempotence-receipt.json`.
- Hosted preflight: `reports/italy-v1-publication/hosted-preflight.json`.
- Hosted final reconciliation: `reports/italy-v1-publication/hosted-final-reconciliation.json`.
- Hosted API acceptance: `reports/italy-v1-publication/hosted-api-acceptance.json`.

## Tests and Git

- Python compilation: PASS.
- Focused unittest suite: 51 passed/run, 5 skipped because disposable database URLs were not configured.
- `git diff --check`: PASS.
- Starting master: `8ed5512a70153788d71665d4891944e35542aebb`.
- Local publication commit: `850598c`.
- Push/deployment: blocked by automatic approval review; origin/master and Railway have not received the persistent importer override.
- Vercel: no deployment required.

Final verdict pending the authorized Git push: PASS WITH DEPLOYMENT PENDING.
