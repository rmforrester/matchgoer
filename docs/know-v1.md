# Matchgoer KNOW v1

KNOW helps somebody considering or attending a fixture understand the club, its supporters and the recurring home matchday. It is concise football-culture context, not a stadium encyclopedia. Publish a fact only when it passes both tests: a visitor would be glad to know it, and it explains why this club, support or matchday differs from another. Unknown is preferable to filler.

## Product boundary

WHY THIS MATCH / DECIDE remains the first-class fixture-choice feature. It answers why a fixture may be worth choosing. KNOW follows it and explains what the visitor should understand about going. The systems retain separate tables, taxonomies, publishers and API contracts; similar subject matter must not become duplicate copy.

The fixture KNOW modules, in order, are:

1. **KNOW THE CLUB** — persistent, distinctive club identity and local meaning.
2. **THE SUPPORTERS** — meaningful human stories, traditions and supporter institutions. Generic passion/loyalty claims are rejected.
3. **THE MATCHDAY** — recurring experience tied to the club at its current ground.
4. **DON'T MISS** — at most one exceptional ritual, place or moment in a resolved fixture journey.
5. **BEFORE THE MATCH** — existing approved BTM destinations, with the subtitle “Where home supporters gather before the game.”
6. **GOOD TO KNOW** — only unusual practical exceptions that materially improve a visit.

Every module is optional. No placeholder or “not yet confirmed” row is published.

## Ownership and serving

`know_facts` has exactly one canonical subject: `team_id`, `club_venue_id`, `venue_id`, or `fixture_id`. CLUB and SUPPORTERS are team-owned. MATCHDAY is club-venue-owned so moves and ground shares cannot inherit it. DON’T MISS and GOOD TO KNOW can use the subject that accurately describes the claim. Fixture composition matches the exact home team, fixture venue, resolved current club-venue relationship and fixture ID. A reserve is a separate canonical team and cannot inherit its parent’s team facts.

`pre_match_spots` and `pre_match_spot_evidence` remain the only canonical BTM representation. KNOW reads the established serving rules, display order, location context and conditional Directions URL. It never copies BTM into `know_facts`.

Useful existing ticket and practical guide facts remain secondary Ground Essentials. Generic content is not promoted to GOOD TO KNOW. DECIDE, ratings, reviews and historical tips are also retained separately.

## Evidence

`know_fact_evidence` keeps sources separate from published wording and supports multiple sources, supporting or contradicting disposition, review state, source dates, notes and optional contributor attribution. Public responses expose accepted supporting source identity and dates but never internal evidence notes.

Published standard claims require at least one accepted supporting source. Claims marked `SENSITIVE` require at least two distinct accepted supporting sources. Editors apply the sensitive policy to politics, class, religion, violence, hostility, reputation and social identity. Source count is a publication rule rather than a database truth constraint.

## Contributions

New Matchday Tip submissions default to `pending`; historical `active` tips keep serving. Helpful votes and reports remain moderation signals and never establish canonical truth. An editor may use a submission as evidence for a separately reviewed KNOW fact. A submitted tip is never automatically promoted.

## Manifest and publication safety

Frozen KNOW manifests use `artifact_version=matchgoer-know-v1-publication`, `publication_state=FROZEN_PUBLICATION_CANDIDATE`, stable `editorial_key` values and per-row SHA-256 identities. `backend/know_v1_publication.py` checks ownership, evidence policy and hashes, refuses non-local databases, performs a read-only dry run by default, and requires both an explicit operation and `--confirm-local-write` for mutation. Publication uses one serializable transaction. Reruns reconcile as `EXACTLY_PRESENT`. Rollback deletes only exact manifest editorial keys and their cascading evidence.

Before migrating legacy `venue_guide_facts`, run `backend/know_v1_legacy_inventory.py` against a readable local database. Every row is recorded as `MIGRATE_TO_KNOW`, `KEEP_AS_UTILITY`, `ARCHIVE_AFTER_REVIEW`, or `IDENTITY_BLOCKER`. The initial deterministic classifier never promotes a practical fact based on topic wording alone and sends legacy pre-match prose for comparison with canonical BTM.

## Country workflow

For each country: export current canonical teams, venues, fixtures and CURRENT/HOME relationships; research in an editorial ledger; resolve identities; freeze omissions as ledger decisions without database placeholders; freeze the hashed publication manifest; run local read-only preflight; back up and fingerprint; publish locally; reconcile API and UI; rerun for idempotence; then request separate approval for hosted schema/data publication. Roll back only from an exact reconciled manifest state.
