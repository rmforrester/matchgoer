# Data ingestion playbook

This is the canonical import guide. `ingest_leagues.py` is the main API-Football entry point and is read-only unless both `--write` and `--confirm-write` are supplied.

## Flow

```mermaid
flowchart LR
    Config[Country / league / season profile] --> Cache[Cached API-Football responses]
    AF[API-Football] --> Cache
    Cache --> Teams[Upsert teams]
    Teams --> Refs[Resolve venue_provider_refs]
    Refs --> Venues[Upsert stable canonical venue]
    Venues --> Fixtures[Upsert fixtures]
    Fixtures --> Link{Venue link}
    Link -->|1-2. reviewed scoped override| Override[Reviewed current-season link]
    Link -->|3-4. provider ID / exact canonical identity| Direct[Authoritative link]
    Link -->|5. home-team provider venue| Home[Inferred fallback]
    Link -->|6. no safe link| Unresolved[Unresolved / reviewed exception]
    Override --> Coords[Coordinate validation]
    Direct --> Coords[Coordinate validation]
    Home --> Coords
    Unresolved --> QA[QA report]
    Coords -->|missing only| Nom[Nominatim enrichment]
    Nom --> QA
    QA --> Dry[Dry-run review]
    Dry -->|explicit --write --confirm-write| DB[(PostgreSQL)]
```

## Configuration and safety

League profiles live in `config/leagues.py`. They specify country, provider league, provider season and display-season label; season is never inferred. Credentials belong in `backend/.env` or the process environment:

```text
DATABASE_URL=...
API_FOOTBALL_KEY=...
```

Do not commit values. Raw provider responses are cached in `.cache/api-football`; reports are written to `reports/ingestion`.

## Commands

Run from the repository root with the repository virtual environment.

### Profile dry runs

```powershell
.\.venv\Scripts\python.exe .\ingest_leagues.py --profile england-pyramid
.\.venv\Scripts\python.exe .\ingest_leagues.py --profile usa-priority
.\.venv\Scripts\python.exe .\ingest_leagues.py --profile sweden-priority
```

### One-league dry run and controlled write

```powershell
.\.venv\Scripts\python.exe .\ingest_leagues.py --country USA --league-id 253 --league-name "Major League Soccer" --season 2026 --display-season 2026
.\.venv\Scripts\python.exe .\ingest_leagues.py --country USA --league-id 253 --league-name "Major League Soccer" --season 2026 --display-season 2026 --write --confirm-write
```

Use `--no-geocode` when a reviewed write should apply cached accepted coordinates only and defer new Nominatim queries.

### Coordinate and active-API QA

```powershell
.\.venv\Scripts\python.exe -m ingestion.validate_mvp_data_quality
.\.venv\Scripts\python.exe -m ingestion.apply_reviewed_coordinates
.\.venv\Scripts\python.exe -m ingestion.apply_reviewed_coordinates --write --confirm-write
```

Reviewed manual exceptions use a narrow scoped command:

```powershell
.\.venv\Scripts\python.exe -m ingestion.apply_manual_venue_override --league-id <id> --season 2026 --home-team-id <id>
.\.venv\Scripts\python.exe -m ingestion.apply_manual_venue_override --league-id <id> --season 2026 --home-team-id <id> --write --confirm-write
```

## Linking and coordinate rules

API-Football is Matchgoer's trusted football-data source. It determines **what**
venue a fixture uses when it supplies reliable venue identity; coordinate
enrichment determines **where** that already-identified physical venue is. OSM
and Nominatim do not need to independently prove club association. Venue
identity/linking and coordinate enrichment are separate decisions.

Fixture venue-link precedence is:

1. reviewed fixture-specific override;
2. reviewed season/league/team override;
3. provider fixture venue ID;
4. exact, unambiguous canonical direct venue-name identity;
5. home-team/default venue fallback, reported as inferred;
6. unresolved, with `fixtures.venue_id = NULL`.

Provider IDs must never be invented. Name similarity must never silently merge
venue identities. Reviewed current-season, temporary-ground and groundshare
evidence takes precedence when its scope applies.

`venues.venue_id` is the stable internal identity. `venue_provider_refs` is authoritative for provider-to-canonical resolution and can hold multiple provider references for one venue. The legacy nullable, unique `venues.provider_venue_id` remains for API compatibility during migration. Never invent provider IDs.

For venue names:

1. A trusted name change on an existing provider reference updates `venues.name`, promotes that value to the single current `venue_names` row and retains the former value as historical.
2. A fixture name without a fixture provider venue ID is reported as an observed candidate. It cannot change a canonical venue name or create an alias automatically.
3. A previously unseen provider ID creates a new venue unless reviewed evidence explicitly maps it. Exact metadata similarities may be reported, but name similarity never triggers an automatic merge.

Reviewed aliases are searchable and return the canonical venue once. Fixture rows retain the provider-supplied `venue_name` field, while current discovery, map and venue-page display resolves through the linked canonical venue.

### Coordinate enrichment

Preserve valid database coordinates and consider only missing coordinates. The
canonical Nominatim/OSM resolver evaluates its complete bounded query ladder;
an ambiguous weak or address-oriented result does not terminate stronger
venue-name/locality queries. Candidate identity uses structured `name`,
`name:en`, relevant alternate and old names, plus conservative
normalisation/transliteration. It requires a plausible physical sports venue,
compatible country and reasonable locality. Duplicate OSM representations of
the same physical object may be grouped when the evidence supports that.

`AUTO_RESOLVED` requires convergence on one physical venue. Multiple supported
venues remain `AMBIGUOUS`; unsupported candidates remain `UNRESOLVED`. Native-
language primary OSM names are not defects. Never invent a coordinate.

Wrong-city, wrong-country, training-ground/main-stadium mismatches and other
material identity contradictions fail closed. `NULL` coordinates are valid
storage and fixtures without safe coordinates remain absent from radius,
nearby, map-marker and directions surfaces. Coordinate completeness is a QA
and product-readiness metric, not a whole-league ingestion gate. The former
arbitrary 10% unresolved breadth gate is superseded; genuine provider identity
collisions and material venue contradictions remain blockers.

Use representative audit evidence before opening manual-remediation projects.
Where trusted upstream data appears complete but Matchgoer output is missing,
inspect reconciliation and transformation logic before assuming a provider-data
gap.

### Protected coordinate operating model

The reusable flow is:

`Build -> test -> representative proof -> local read-only operational run -> review genuine exceptions -> one protected hosted write -> reconciliation.`

Codex builds and tests tooling. Long-running data operations run from local
PowerShell with deterministic scripts and durable checkpoints. A protected
coordinate write requires a reviewed checkpoint, exact expected-update guard,
null-coordinate-only predicate, captured baseline, identity and row-count
protection, explicit write confirmation and post-write reconciliation.

Hosted coordinates are `NUMERIC(9,6)`. PostgreSQL may return them to Python as
`Decimal`; baseline/report serialization must explicitly use a deterministic,
JSON-safe six-decimal representation, and reconciliation compares at that same
precision.

## Current coverage and dated findings

The 2026 profiles cover England, the USA priority leagues and Sweden. The England provider audit found availability through Step 7-equivalent premier divisions. The Sweden work includes an Allsvenskan audit and the available lower national groups. API-Football venue payloads frequently omit coordinates, which is why the generalized Nominatim and reviewed-coordinate path exists.

Some USA venues remain reviewed exceptions when direct or team provider data is incomplete. Never turn a dated unresolved count into a permanent invariant. The dated machine-readable snapshots under `reports/ingestion`, especially `mvp-data-quality-final-2026.json`, `mvp-coordinate-gaps-2026.json` and `unresolved-link-review-2026.json`, are the evidence for a specific import state.

### European breadth coordinate milestone — 1 September 2026

The completed 30-country breadth cohort contains 4,951 fixtures. The final
structured-Nominatim pass applied 48 reviewed, null-coordinate-only updates and
made 674 additional fixtures location-discoverable. Reconciliation verified
3,293 / 4,951 fixtures (66.5%) as location-discoverable, with zero venue
inserts, deletes or identity changes.

The 66.5% figure is the current safe result, not a target threshold. Remaining
coordinates intentionally fail closed. Provider venue IDs `774`, `1759`,
`2524`, `3512`, `4006`, `11595`, `19583` and `20757` were specifically
withheld. Fixtures with `venue_id = NULL` remain a separate linking issue and
were not changed.

Handoff lesson: the earlier approximately 53% breadth location coverage
substantially reflected coordinate reconciliation/query logic, not simply poor
API-Football venue data. The bounded structured resolver safely increased it to
66.5%. The European breadth coordinate-enrichment workstream is closed; do not
restart unresolved-venue remediation without a new scoped decision.

## Import checklist

1. Confirm the database identity, league/provider season and cached response scope.
2. Run a dry run and review availability, inserts/updates, duplicate provider IDs and unresolved links.
3. Review inferred home-team links, direct/home conflicts and coordinate candidates.
4. Review `observed_venue_name_candidates` and `provider_reference_review_candidates`; neither list is an instruction to merge.
5. Run the explicit controlled write one league at a time.
6. Run database and active API QA, including `/leagues`, `/fixtures`, `/nearby`, `/venues` and venue search.
7. Preserve unresolved records for review; do not guess with fuzzy name matching.

Generate the current non-mutating renamed-stadium candidate report with:

```powershell
.\.venv\Scripts\python.exe .\audit_venue_identity_candidates.py --output .\reports\ingestion\venue-identity-review-candidates-2026-08-14.json
```

## Mutable fixture refresh

Full-season imports use cached provider responses for safe repeatability, so they are not the operational refresh for scores and statuses. During beta, run `refresh_fixture_states.py` at least daily over the recent-past/current/future window. It deliberately bypasses provider cache and updates only existing fixture kickoff, status, score and raw venue-label fields.

```powershell
.\backend\venv\Scripts\python.exe refresh_fixture_states.py --from-date 2026-08-13 --to-date 2026-10-19
.\backend\venv\Scripts\python.exe refresh_fixture_states.py --from-date 2026-08-13 --to-date 2026-10-19 --write --confirm-write
```

Review the dry-run report before the transactional write. Never infer `FT` from a past kickoff. The beta preflight fails past `NS` beyond the agreed grace window and future `FT`/`AET`/`PEN` rows.
