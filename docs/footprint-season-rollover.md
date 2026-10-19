# Football Footprint season rollover — v1.2

Offline proposal workflow. No fetching, database access, publication, credentials,
or application configuration. Replaces the fixed-path orchestration gap in the
18 October v1.0 operating runbook; retains its canonical safeguards.

## Frozen inputs

1. Use the latest accepted `backend/footprint_membership.json`. Record master and
   deployments. Do not use an older research candidate as the publication base.
2. Reuse the existing canonical snapshot shape: `teams`, `venues`, `relationships`.
   Include only canonical public metadata, approved direct venue equivalences and
   CURRENT relationship role/date fingerprints. No attendance or credentials.
   Revalidate relevant facts with existing read-only checks when stale; do not
   relabel an old snapshot as freshly reviewed without evidence.
3. Reuse cached season-specific team rosters from the established reconciliation
   reports/API client. A necessary refresh uses that existing client separately.
   Retain paging/errors/results and exact participant IDs. Never use fixture
   appearance, provider current=true, club names or current divisions as proof.
4. Prepare a reviewed plan, version 1, with `snapshot_as_of` (explicit frozen UTC
   day), `snapshot_sha256` and `scopes`. Calculate the snapshot digest with
   `ingestion.footprint_rollover.digest(snapshot)` (canonical JSON semantic hash).
   Dates/denominator/membership and home evidence require human review; flags are
   review attestations, not facts the tool can independently discover.

Each scope request has this structure (values below are placeholders, not facts):

```json
{
  "competition_id": 123,
  "season": 2027,
  "membership_verified": true,
  "domestic_league": true,
  "scope": {
    "competition_id": 123, "season": 2027,
    "name": "Reviewed league", "country": "Reviewed country",
    "start": "2027-01-01", "end": "2027-11-30", "total": 1,
    "source": "https://official.example/season"
  },
  "roster": {
    "competition_id": 123, "season": 2027,
    "paging": {"current": 1, "total": 1},
    "errors": [], "results": 1, "teams": [{"team": {"id": 456}}]
  },
  "reviewed_members": []
}
```

The small roster envelope adds the exact scope key to the existing cached
`teams`/paging response; it is not another catalogue. Never set verification true
for partial membership. Optional tier fields retain the catalogue's evidence rules.
`reviewed_members`, when needed, contains full existing catalogue member objects
with exact canonical IDs, evidence and expected fingerprints. Explicit reviews
take precedence over reuse; failed explicit reviews cannot silently fall back.

## Run and inspect

Use the existing backend Python environment with repository root and `backend/`
on PYTHONPATH (the existing guard imports the application's models). No packages
need installing. From the implementation worktree:

```text
python -m ingestion.footprint_rollover --catalogue backend/footprint_membership.json --snapshot PATH_TO_SNAPSHOT --plan PATH_TO_PLAN --as-of 2026-10-19 --output PATH_TO_LOCAL_REPORT_DIRECTORY
```

Outputs are `candidate.json`, `changes.json`, `exceptions.json`, `summary.json`.
They are review artifacts, never loaded by the application. Existing runtime JSON
remains the only catalogue. Inputs are never edited. Output cannot overwrite an
input. Exit 0 means no flagged exception, **not permission to publish**; exit 2
means review/capacity failure. Malformed or mismatched inputs fail before output.

`changes.json` records only appended scope postimages, participant additions and
removals relative to the latest earlier season. It never mutates an existing key.
Summary includes semantic hashes and exact input-file byte hashes, active READY
before/after and capacity status. Re-run with identical frozen inputs and compare
all four output byte hashes. Re-run against the candidate: no further scopes may
be appended. No timestamps or random identifiers enter deterministic receipts.

## Identity and calendar rules

- Review each competition's own season dates and promoted/relegated membership;
  do not derive a calendar from its country or extend an expired season.
- Participant changes use canonical IDs, including distinct reserve/senior teams.
  Name similarity never transfers a home. Missing IDs remain unresolved.
- Reuse previously complete reviewed club-home mappings across competitions only
  if current raw-team and role/date fingerprints pass the existing guard.
  Conflicting physical homes, changed roles and expired mappings require review.
- For temporary homes require continuous coverage across the proposed window,
  plus current/as-of validity. Unknown future moves cannot be discovered from
  unchanged metadata; fresh targeted review remains necessary. No historical-home
  interpolation or fixture-derived home is permitted.
- Approved equivalences normalize physical identity only. No name/coordinate
  matching, alias creation or venue merge occurs. Shared grounds keep separate
  member clubs and existing physical-ground deduplication semantics.
- Preserve all old scopes exactly, including expired ones. Same-key differences
  and overlapping seasons are flagged. Future complete scopes do not inflate
  today's READY count. Historical attendance/ratings/photos are never inputs.
- Unknown homes produce incomplete candidates with retained fingerprints and no
  ground credit. Invalid membership produces no appended scope, avoiding a false
  denominator. Inspect all exceptions before proposing a bounded publication.

## Capacity and publication boundary

This prepared runtime permits at most 1,000 scopes and 8 MiB of catalogue input,
of which 274 scopes are occupied. The deployed baseline still has its original
400-scope safeguard until this code release is approved and deployed. The runtime
bounds the file read before JSON parsing; the offline command shares the same
constants/loader and flags oversized proposed output without pruning history.
The 100-member limit and fail-closed identity rules remain unchanged. Tests cover
400/401/1,000/1,001 scopes and the exact byte boundary/one byte over. Existing
owner projections/query counts remain identical with 999 retained old scopes.
Reassess capacity before reaching 1,000; this does not promise unlimited history.

After review, follow the existing bounded catalogue/test publication procedure:
exact preimages, fresh read-only canonical guards, explicit founder approval,
isolated two-file catalogue release, existing deployments and independent
postflight. This command contains no apply, commit, fetch, deploy or publish mode.
Recover source through reviewed reverse commits; never restore or rewrite
attendance or canonical data. Historical progress UI remains deferred.
