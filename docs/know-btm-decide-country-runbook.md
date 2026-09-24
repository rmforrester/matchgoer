# KNOW / BTM / DECIDE country runbook

This runbook implements [the editorial standard](editorial-standard.md) and the human-approved [Gold Standard teaching corpus](editorial-gold-standard.json). Their SHA-256 values must be recorded before each country starts.

Every future programme must explicitly load and apply the Matchgoer/Copa90 test, Gold Standard corpus, six-question filter, contextual-significance doctrine, research-depth and source standards, no-quota rule and sparse-success rule. The corpus teaches judgment; it is not reusable copy.

Every newly researched or drafted supporter-facing row uses the current canonical voice from its first candidate. Do not publish new copy in the legacy formal/editorial voice with the expectation that a later cleanup will repair it.

## Permanent country workflow

### Phase 0 — country context calibration

Before bulk editorial research, document the country's organised-football history, represented pyramid, regional identities, supporter and matchgoing traditions, relative attendance/support patterns, rivalry structures, ground culture, important football places, distinctive settings, country-specific behaviours and meaningful differences between levels. This is an editorial lens, never a quota.

### Phase 1 — DECIDE landscape calibration

Deliberately inventory and adjudicate potential `SIGNIFICANT_RIVALRY`, `CLASSIC_GROUND`, `FOOTBALL_LANDMARK`, `UNIQUE_SETTING`, and `EXCEPTIONAL_SUPPORT` candidates in the country's own football context. For each candidate record why and at what level it matters, whether it could influence fixture choice, the evidence, and the disappearance loss. Zero requires documented investigation.

### Phase 2 — five-relationship calibration

1. Freeze the approved competition/population scope and reconcile team, venue, provider and club-venue identity. Fail unresolved items closed.
2. Select an approximately five-relationship representative sample spanning relevant levels and types. Normally include a major/high-profile club, ordinary professional club, lower-level club, strong supporter-culture case and sparse-information case; adapt when the country structure requires it.
3. Research complete supporter experiences: CLUB, SUPPORTERS, MATCHDAY, BTM, practical actions and relevant DECIDE. Draft in the canonical knowledgeable-matchgoer voice and assign language strength A–D. Do not use quotas. Sparse output may pass.
4. Compare assembled pages with `docs/editorial-regression-benchmark.json`.

### Phase 3 — mandatory human first-pass review

Stop at `FIRST_PASS_READY_FOR_HUMAN_REVIEW`. Ray/assistant must inspect both content selection and tone of voice: actual supporter-facing copy, rendered hierarchy, language-strength levels and every Level C/D recommendation. Use screenshots or equivalent real-page inspection where practical. Explicit Ray approval is required. Codex cannot auto-approve this gate, and Level D always requires explicit human approval.

### Phase 4 — bulk country research

Begin only after explicit human approval has been recorded. Apply universal quality and country-context significance throughout the pyramid.

Assess every in-scope club/relationship deliberately across applicable modules. Finding one usable source or obvious historical fact does not complete research. Keep digging for the most revealing supported story, while accepting `CORRECTLY_SPARSE` when reasonable research finds none.

### Phase 5 — residual reconciliation

Resolve or explicitly accept identity, venue, coordinate and inventory gaps.

### Phase 6 — country-wide survivor/completeness audit

Review all published content in assembled-page context.

### Phase 7 — country closeout

Record coverage, deliberate absences, exceptions and durable evidence.

## Research and self-adjudication

Research the whole supporter page by value route, not by category quota. Reuse canonical club/venue content across competitions. Prefer direct official, venue, transport, supporter, and strong local evidence appropriate to the claim. Record omissions rather than fill them.

For every proposed or surviving fact, complete the review metadata in the editorial standard. Assemble the page and check UI, KNOW, BTM, DECIDE, and venue-container duplication. Apply the disappearance test. Self-adjudicate under the established rules; stop only for a genuinely new editorial judgment, identity ambiguity, architecture decision, or failed safety gate without one obvious bounded correction.

## Publication

Freeze the exact candidate, target fingerprint, and SHA. Run deterministic editorial validation, identity reconciliation, module/subject validation, expected-before validation, logical dry-run, rollback-only real SQL proof, restoration verification, and a fresh backup. Publish atomically only after those gates pass. Reconcile, test serving, and prove idempotence.

The default bounded task is:

`research -> self-adjudicate -> candidate -> rollback-only proof -> publish -> acceptance -> closure`

After the mandatory first-pass gate, human review returns to being an exception gate for established judgments. Do not split later work into ceremonial review tasks.

## Country closure

1. Confirm every approved-scope competition is complete or explicitly blocked.
2. Run a survivor sweep over every published KNOW fact: anti-pattern scan, exact duplicates, semantic same-page review, assembled-page review, disappearance test, BTM reconciliation, and DECIDE duplication check.
3. Consolidate identity and venue blockers. A relationship can be `EDITORIALLY_RESEARCHED` and `BLOCKED_FROM_PUBLICATION`. Classified fail-closed blockers do not force filler and do not prevent editorial closure.
4. Publish a closure report with final KNOW/BTM/DECIDE totals, survivor decisions, blocker ledger, tests, and hosted mutation accounting.

Run a post-country retrospective only when material failure or drift occurred.

## Permanent controls

- Quality is universal; significance is contextual. Pyramid level changes the comparison context, never evidence or usefulness standards.
- Existing content is never grandfathered into closure.
- Evidence, row presence, HTTP serving, and idempotence are technical gates, not usefulness judgments.
- A new country cannot start bulk research or publication until country-context calibration, deliberate DECIDE calibration, representative-page research and explicit first-pass human product/editorial approval are recorded.
- Practical content cannot stand in for deliberate CLUB, SUPPORTERS or DECIDE investigation.
- Logical dry-run is never a substitute for rollback-only real SQL proof.
- Supporter copy uses football language, never internal editorial/rubric language or unsupported atmosphere.
- Fixture Buy Tickets owns the ordinary purchase route; MATCHDAY retains only non-obvious purchase, receipt and entry guidance.
- Tone must vary naturally rather than applying a repeated module template.
- Drama is not required; discovery is. Find the most revealing story, not the most dramatic story.
- One hundred percent research coverage never implies one hundred percent publication coverage. `PUBLISH` and `CORRECTLY_SPARSE` are both successful outcomes.

## Substantive-research runtime

Ray has removed the normal two-hour ceiling for future **explicitly authorized substantive editorial research programmes**. Such research may run as long as completeness, depth and quality require, with durable checkpoints for resilience. This does not authorize publication, database or hosted mutation, destructive action, deployment or any other protected operation; those retain their normal gates.
