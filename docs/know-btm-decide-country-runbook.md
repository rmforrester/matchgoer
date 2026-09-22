# KNOW / BTM / DECIDE country runbook

This runbook implements [the editorial standard](editorial-standard.md). Its SHA must be recorded before each country starts.

## Pre-country

1. Freeze the approved competition/population scope.
2. Reconcile team, venue, provider, and club-venue identity. Record unresolved items in a blocker ledger and fail them closed.
3. Select five calibration relationships: one major club, one smaller professional club, one lower-division club, one strong supporter-culture relationship, and one sparse-information relationship.
4. Research and assemble those five pages with the intended workflow. Sparse output may pass.
5. Compare them with `docs/editorial-regression-benchmark.json` and obtain explicit methodology approval before bulk work.

## Research and self-adjudication

Research the whole supporter page by value route, not by category quota. Reuse canonical club/venue content across competitions. Prefer direct official, venue, transport, supporter, and strong local evidence appropriate to the claim. Record omissions rather than fill them.

For every proposed or surviving fact, complete the review metadata in the editorial standard. Assemble the page and check UI, KNOW, BTM, DECIDE, and venue-container duplication. Apply the disappearance test. Self-adjudicate under the established rules; stop only for a genuinely new editorial judgment, identity ambiguity, architecture decision, or failed safety gate without one obvious bounded correction.

## Publication

Freeze the exact candidate, target fingerprint, and SHA. Run deterministic editorial validation, identity reconciliation, module/subject validation, expected-before validation, logical dry-run, rollback-only real SQL proof, restoration verification, and a fresh backup. Publish atomically only after those gates pass. Reconcile, test serving, and prove idempotence.

The default bounded task is:

`research -> self-adjudicate -> candidate -> rollback-only proof -> publish -> acceptance -> closure`

Human review is an exception gate. Do not split established work into separate research, extraction, review, and publication tasks merely as ceremony.

## Country closure

1. Confirm every approved-scope competition is complete or explicitly blocked.
2. Run a survivor sweep over every published KNOW fact: anti-pattern scan, exact duplicates, semantic same-page review, assembled-page review, disappearance test, BTM reconciliation, and DECIDE duplication check.
3. Consolidate identity and venue blockers. A relationship can be `EDITORIALLY_RESEARCHED` and `BLOCKED_FROM_PUBLICATION`. Classified fail-closed blockers do not force filler and do not prevent editorial closure.
4. Publish a closure report with final KNOW/BTM/DECIDE totals, survivor decisions, blocker ledger, tests, and hosted mutation accounting.

Run a post-country retrospective only when material failure or drift occurred.

## Permanent controls

- Scale changes batch size, never the editorial threshold.
- Existing content is never grandfathered into closure.
- Evidence, row presence, HTTP serving, and idempotence are technical gates, not usefulness judgments.
- A new country cannot start bulk publication until the five-relationship calibration is approved.
- Logical dry-run is never a substitute for rollback-only real SQL proof.

