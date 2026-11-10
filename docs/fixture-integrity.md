# Fixture integrity foundation

Geographic extension: `venue_geography` compares competition/club countries, canonical home context, reviewed fixture binding and coordinates without selecting a replacement. Country/anchor disagreements are review cases, preserving cross-border, neutral, overseas and international events. Spain's reviewed, generous sanity envelope includes Canaries/Ceuta/Melilla; a Spanish-labelled ground with Peru coordinates is suppressed before API counts/pagination, including retained NULL-provider venues. No worldwide boundary coverage is claimed for countries without reviewed envelopes. Geographic disputes enter the existing receipt/digest and can clear after accepted valid data. No ground coordinates or canonical identity are automatically changed. See the implementation package's `geographic-extension/investigation-report.md` for fixture 1618001 and bounded wider findings.

This extends the existing nightly job and API. It neither fetches official websites nor creates a second fixture catalogue. Apply `backend/migrations/20261110_fixture_integrity.sql` through the reviewed migration procedure **before deploying the updated writer**. Never run it automatically at application startup.

## Scheduling and geography

`backend/fixture_integrity.py` supplies the shared eligibility rule. `/nearby` applies it before date filtering, counting and pagination; `/fixtures` and `/venues/{id}/fixtures` retain historical access and exclude inactive future availability. Fixture details and Interested records remain accessible, with effective scheduling and integrity metadata. Ground identity projection remains in `backend/venue_resolution.py`. Editorial records and attendance ownership are not rewritten.

- Active statuses: NS, TBD and live 1H/HT/2H/ET/BT/P. These do not imply an officially confirmed kickoff.
- PST and CANC are excluded from forthcoming availability. SUSP/INT are interrupted play, ABD abandoned, and AWD/WO administrative outcomes: none is a new attendable opportunity.
- FT/AET/PEN are retained for past results, not advertised at erroneous future kickoffs.
- Superseded fixtures, high-confidence scheduling holds and disputed venue decisions have no Discover pin. A disputed venue is also withheld from fixture-detail venue/directions projection; the fixture and uncertainty remain available.

Effective schedule classifications are separate from provider status codes. Raw provider date, status, timestamp and venue survive in sidecar observations/history. API-Football's timestamp is a kickoff timestamp, not last-updated metadata.

Cross-competition detection compares canonical participant IDs, including both teams of an inserted/updated fixture and existing upcoming counterparts. Same/adjacent UTC dates create candidates when local-zone precision is unavailable; they do **not** infer postponement or apply a hold. Holds need explicit fresh timing evidence, canonical senior-team attestations, overlapping 150/180-minute match intervals, and no provisional/friendly/split-squad/multi-match exception. Different reserve/youth/women canonical IDs do not collide. Uncertain category data remains a review candidate. No trusted-source scraping or AI write mechanism is introduced.

Later accepted date/status changes re-evaluate cases and release resolved holds; multiple remaining high-confidence pairs keep a fixture held. An official postponement protects the old date from a stale provider NS echo. A later accepted same-ID active fixture at a genuinely changed provider date resolves that old-slot postponement automatically and retains its evidence in history. Explicit official scheduling otherwise outranks contradictory provider data until reviewed. Cancellation is not inferred from disappearance.

Potential replacement IDs for an unresolved postponed event are held before insertion. Same participants alone never authorise merging replays/legs, migrating personal associations or deleting a fixture. Confirmed supersession can be represented in the schedule sidecar under reviewed operator authority; no automatic replacement-ID alias table is introduced.

## Reviewed venue verification

`set_verified_venue(connection, fixture_id, canonical_venue_id, ...)` is a privileged internal transaction primitive, **not a public endpoint**. Its caller must supply approved source URL, evidence digest, actor, previous provider venue and expected verification revision. It updates only the exact fixture relationship and sidecar, never ground identity/coordinates. Verification and previous provider evidence are retained; repeated identical input is a no-op. Review changes retain prior verification revisions.

The nightly resolver prefers an identity-matching verified fixture venue. A PostgreSQL trigger rejects another writer reverting that binding or changing the guarded competition/participant identity. Unverified automatic canonical conflicts become DISPUTED; unknown provider venue assignments become UNRESOLVED and hide an old pin without deleting its historical relationship. A later valid resolution can release either automatic hold. A missing provider venue alone does not erase an established ground. Official verification is not downgraded because the provider is NULL or stale. No default USL correction or seed data is included in the migration.

`set_schedule_evidence` similarly accepts reviewed internal evidence and revision guards. No endpoint allows supporters or an AI agent to approve these decisions. Operational permission and evidence review remain prerequisites.

## Receipts and independent checking

`fixture_integrity_runs` records a UUID, scheduled UTC occurrence, start/finish, source SHA, attempted/completed provider calls, observed competition/season, payload counts/hashes, changed/unchanged/missing IDs, reasons, errors and coverage outcome. HTTP/validated-response completion differs from an attempted request. Cached responses do not count as new requests. Fixture and integrity decisions commit together; the run-start and request ledger use independent transactions so a fixture rollback cannot erase failure evidence. A hard kill leaves RUNNING and any already committed groups identifiable.

The report includes a prioritised exception digest. Routine fixture updates are counters rather than per-update notifications. Cases carry stable keys and first/last observations; report repetition does not authorise alert spam. Receipt finalisation failure leaves an incomplete/stalled run to be detected independently. If startup validation forbids database access or the database is unavailable, a failed receipt cannot always be written; absence is itself a monitoring failure signal.

The independent read-only command is:

```text
python scripts/check_fixture_integrity.py --database-env DATABASE_URL --grace-hours 2
```

It never runs ingestion. PostgreSQL enforces read-only transactions and bounded query/lock timeouts. Exit 0 means a completed occurrence; exit 1 reports missed, late, failed, stalled or incomplete coverage distinctly; exit 2 means monitoring could not read the receipt store. It does not expose credentials. Schedule this from an independent existing operations monitor only after approval; no monitoring schedule or notification destination is installed by this implementation. Default due time remains 04:20 UTC, with a two-hour completion grace. Off-window invocations cannot satisfy an on-time occurrence.

## Budget and deployment

Preserve **750 requests per daily job**, the **shared 100-request USA/global discovery allowance**, and **50 absent fixture candidates per group**. There is no new 100-request lifecycle ceiling or 50-request discovery ceiling. Status/quota requests count in the existing shared accounting; highlights retains its reserve. All new checks reuse fetched responses and SQL; baseline additional provider calls are zero. Request ceilings still cover attempted calls, including failures.

The implementation package's deployment/rollback runbook covers source pinning, additive migration, reader/writer ordering, schema verification, next-normal-run acceptance and independent rollback. Do not roll back to an unaware writer/reader while active verifications or holds exist. The rollback migration refuses active protections; export receipts/history before considering any drop. Preserve all fixtures and supporter references. No change to Railway command, cron, scopes or discovery activation is required.

## Lifecycle acceptance policy (supersedes earlier home fallback)

Current-home reviews alone no longer assign an unknown event venue. Provider event data or reviewed fixture-specific evidence is required for a new binding. Venue-only uncertainty retains a valid new fixture with NULL ground and an explicit location outcome; fixture/team/scope identity conflicts remain holds. The scheduler retries already-reviewed configured season IDs weekly after readiness expiry or dormant cadence, within existing budgets; no registry ID/season is added. The release gate requires real scheduled-run evidence for new fixtures, statuses, rescheduling, alternative/neutral grounds and safe pins, including FA Cup second round and USL final. Successful deployment alone is not production completion.
