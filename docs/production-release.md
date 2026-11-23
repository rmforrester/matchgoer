# Production source and release rule

WORKTREE ? TEST ? FOUNDER APPROVAL ? PROMOTE TO MASTER ? CI ? DEPLOY MASTER COMMIT ? VERIFY.

Worktrees isolate development. They must not be the sole surviving representation of production source. Only code and file-backed configuration belong here. Catalogue/database corrections continue to use their approved manifests and receipts. Never commit .env files, credentials, production receipts, account exports, or build artifacts.

## Canonical source

`ops/production_sources.json` describes the exact source files for each live service. Shared files are reused. `ops/production_sources/` retains only differences between services that currently run different source; they are source files, not deployed artifacts. Text line endings are normalized to LF; original byte hashes and deployment provenance remain in the external preparation report.

The repository root represents the safeguarded writer. Do not deploy this root as another service without selecting its profile. API and monitor currently have different implementations of some shared paths; choosing the newest file for every service would change unapproved production behaviour.

Profiles `writer`, `api`, `monitor`, `backup`, `photo-cleanup`, and `web` reproduce the recorded live services. `backup-approved-test-orphan` contains the separately approved fourth acknowledgement and is NOT yet deployed. `monitor-source-warning` is a NOT DEPLOYED proposal. Build 19 guest discovery, native location changes, JWKS and query-work hardening remain outside this production candidate.

## Before code deployment

1. Refresh canonical tracking: `git fetch origin master`.
2. Obtain the exact approved 40-character commit SHA. Run `python scripts/production_source_guard.py <sha>`.
3. The guard checks the actual origin master tip matches the local tracking ref, then requires `git merge-base --is-ancestor <sha> origin/master`. It refuses stale tracking refs, unpromoted detached commits and missing evidence. There is no production bypass flag.
4. Stage the required service only: `python scripts/stage_production_source.py <profile> <sha> <new-output-directory>`.
5. Use the existing bounded CLI/Docker upload process on that staged context, or an explicitly configured equivalent Git build. Record canonical commit, profile, source hashes, deployment ID and image digest. Do not stage a dirty worktree or run another service's command.
6. Verify source/configuration, health, actual product behaviour and protected controls. Retain rollback to the exact prior image/source. Do not manually run scheduled production jobs merely to validate source.

## Variable-only changes

A Railway dashboard variable change is staged. Applying it can rebuild the configured Git branch; it does not promise to retain the previously deployed commit. For a Git-linked service, apply only after canonical master contains the proven production source and verify the planned exact commit/profile before deploying staged changes. Refuse a variable deployment when that comparison cannot be established. Never solve a source mismatch by changing a key again.

For an existing archive-uploaded service with no Git source, retain its exact verified artifact when applying environment changes, or deliver the approved canonical source via the existing guarded upload process. Verify resulting image/source and settings. Do not attach an arbitrary stale branch. Each service needs its own source/profile selection; no monolithic deployment is authorized by promotion.

## Existing monitor proposal

`monitor-source-warning` adds a read-only source-continuity warning to the existing receipt/email. It compares actual Railway commit metadata with one canonical GitHub master snapshot. Missing CLI commit provenance, API access or ancestry evidence is FAIL/unverified, not PASS. No provider calls, schedules, alert recipients or existing integrity thresholds change.

Cross-service metadata requires approved access to the existing Railway project/environment token through `RAILWAY_TOKEN`. That access is NOT currently configured on the monitor and is NOT added by this preparation. Credential permissions must be reviewed before enabling the proposed profile; do not embed or publish a token. CLI services without a Git commit in their metadata remain explicitly unverified until canonical delivery provenance can be established. This proposal is not claimed as live monitoring acceptance.

## After 0.1.2

Review the identity checker's pinned baseline hash and hardcoded aggregate counts. Keep explicit founder approval and fail-closed handling; never automatically accept new orphans. No redesign is included here.
