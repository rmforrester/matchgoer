# DECIDE V1 proof release

This runbook publishes only the approved four-fact DECIDE proof. It is intentionally separate from fixture ingestion and KNOW publication.

## Single approval gate

Before any hosted mutation, one operator must approve all of the following together:

- a current protected Railway PostgreSQL backup has completed and its archive has been validated;
- the deployed repository commit is the reviewed DECIDE proof commit;
- `backend/migrations/20260902_decide_v1.sql` and `reports/research/decide/v1/decide-v1-proof-publication.sql` are unchanged from that commit;
- the canonical identities are still teams `33`/`40` and venues `23100`/`23114`/`582` with the names asserted by the publication artifact;
- Railway can be held on the previous backend until the additive schema migration succeeds.

If any item fails, stop without applying the migration or publication artifact.

## Protected sequence

1. Record hosted row counts for `teams`, `venues`, and `fixtures`, and verify that `decision_facts` and `decision_evidence` do not yet exist. Do not treat an unexpected pre-existing DECIDE table as an empty baseline.
2. Create and validate the normal protected hosted PostgreSQL backup.
3. Apply only `backend/migrations/20260902_decide_v1.sql`. Its transaction must complete before deploying backend code that queries DECIDE tables.
4. Reconcile the additive schema: both tables exist, both contain zero rows, their constraints/indexes exist, and the pre-migration `teams`/`venues`/`fixtures` counts are unchanged.
5. Deploy the reviewed backend commit to Railway, wait for a healthy deployment, and verify `/health` returns HTTP 200 with `{"status":"ok"}`. Then allow the matching Vercel deployment and verify the ordinary Discover path still serves.
6. Apply only `reports/research/decide/v1/decide-v1-proof-publication.sql`. The artifact runs in one transaction, asserts canonical identities, uses conflict-safe inserts, and raises before commit unless the exact four approved facts and their accepted supporting evidence reconcile.
7. Reconcile hosted DECIDE state: exactly four proof facts and four accepted supporting evidence rows exist; no other table row count changed.
8. Verify the API contract read-only:
   - an ordinary `/nearby` fixture returns `highlight_eligible=false` and `lead_decision_reason=null`;
   - an eligible `/nearby` fixture returns the deterministic lead reason;
   - `/fixtures/{fixture_id}/social` returns all applicable published `decision_reasons` and no evidence payload.
9. Verify beta presentation: ordinary markers/cards are unchanged; eligible groups are gold and initially open the earliest eligible fixture; every grouped fixture remains navigable; the fixture page shows `WHY THIS MATCH` only when reasons exist.

## Failure and rollback posture

- Before the schema transaction commits: no application rollback is required.
- After schema but before publication: keep the additive empty tables and restore/redeploy the previous application version if needed; do not run the proof publication artifact.
- During publication: any guard or reconciliation failure rolls back the whole four-fact transaction. Preserve the failed state/logs and diagnose before retrying.
- After publication: do not run the destructive rollback automatically. Stop application promotion and use the verified backup or a separately reviewed removal transaction.

The schema migration and proof publication are deliberately not executed by repository preparation.
