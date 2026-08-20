# Terrace Talk league import playbook

> **Historical detail — superseded as the canonical guide on 14 August 2026.** Use [`docs/data-ingestion.md`](docs/data-ingestion.md). This file is retained for dated audit history and detailed import lessons.

`ingest_leagues.py` is the canonical API-Football ingestion command. It works
for a country, provider league ID and provider season, and never writes unless
`--write --confirm-write` is supplied.

## Configuration

League profiles live in `config/leagues.py`. A scope records country, provider
league ID (resolved from the provider for audit profiles), display name,
provider season, and display-season label. Provider season is never inferred:
England 2026 is labelled `2026/27`; USA and Sweden 2026 are labelled `2026`.

Set these values outside source control in `backend/.env` or the process
environment:

```text
DATABASE_URL=...
API_FOOTBALL_KEY=...
```

The command reads the same `DATABASE_URL` source as the active backend. It
does not use the legacy hard-coded script credentials or keys.

## League discovery and coverage audit

Profiles first call `/leagues?country=...`, resolve each requested name, then
call `/leagues?id=...&season=...` before teams or fixtures. The report marks
each requested competition unavailable rather than silently skipping it.

```powershell
.\.venv\Scripts\python.exe .\ingest_leagues.py --profile england-pyramid
.\.venv\Scripts\python.exe .\ingest_leagues.py --profile usa-priority
.\.venv\Scripts\python.exe .\ingest_leagues.py --profile sweden-priority
```

These are dry runs. Raw provider responses are cached under `.cache/api-football`
to reduce quota use, and JSON QA reports are written under `reports/ingestion`.

For one specific league after provider ID discovery:

```powershell
.\.venv\Scripts\python.exe .\ingest_leagues.py --country USA --league-id 253 --league-name "Major League Soccer" --season 2026 --display-season 2026
```

## Import stages

1. Run and review a dry run.
2. Fetch/cache API-Football league, team, and fixture responses with a timeout
   and one-second request interval.
3. Upsert provider teams by `team_id`, translating their provider venue ID to
   the canonical internal venue relationship.
4. Upsert venues by nullable unique `provider_venue_id`; PostgreSQL generates
   the canonical internal `venue_id` for new rows.
5. Upsert fixtures by API-Football `fixture_id`. Existing fixtures are updated
   so kickoff, venue, status, postponed/cancelled state and scores stay current.
6. Link fixtures through provider venue IDs. If a fixture provider venue is
   absent, use the home team's provider venue as a reported inference. Direct
   fixture venues remain authoritative and direct/home conflicts are reported.
   Name/city repair remains legacy historical-only work; ambiguous names must
   be reported and manually reviewed.
7. Validate coordinates and geocode only unresolved venues.
8. Review the QA report before treating the import as complete.

An actual import is explicit and non-destructive: it inserts or updates only.

```powershell
.\.venv\Scripts\python.exe .\ingest_leagues.py --country USA --league-id 253 --league-name "Major League Soccer" --season 2026 --display-season 2026 --write --confirm-write
```

Use `--no-geocode` when a reviewed import should defer coordinate enrichment.

## Canonical and provider venue identifiers

`venues.venue_id` is the canonical internal Terrace Talk identifier used by
fixture, team, tip, and review relationships. `venues.provider_venue_id` is the
nullable, unique API-Football identifier. Existing provider venues were
backfilled without renumbering, so their two values initially match; new
provider venues are found/upserted by `provider_venue_id` and receive a
PostgreSQL-generated internal `venue_id`.

Never place a made-up provider ID in either field. A reviewed manual venue has
a generated internal `venue_id` and `provider_venue_id = NULL`.

## Reviewed manual venue overrides

Overrides live declaratively in `config/venue_overrides.py`, keyed by provider,
league, season, and home-team provider ID. They include reviewed venue identity,
coordinates, and `source = manual_verified`. Linking precedence is always:

1. direct fixture provider venue;
2. provider home-team venue fallback;
3. reviewed manual override;
4. unresolved.

Thus a future authoritative fixture venue automatically supersedes an override.
Use the narrow `ingestion.apply_manual_venue_override` command for a reviewed
backfill rather than a broad league upsert when only existing null links should
change.

## Coordinate retry and ambiguity review

The coordinate checkpoint stores accepted results and is the only coordinate
source used by `--no-geocode` production writes. Preserve valid database
coordinates first. Retry only unresolved records with transport/rate-limit
errors, using one worker, conservative spacing, bounded backoff, and immediate
checkpoint writes. Review ambiguous candidates separately: require expected
locality/country plus a decisive venue-name, alias, feature-type, or exact-address
signal. Never promote ambiguous, wrong-city, or insufficient-data results.

## First production import lessons (MLS 2026)

The MLS dry run and write proved the cache-backed path end to end. Preflight the
exact database identity, provider-ID overlap, insert/update counts, coordinate
eligibility, duplicate IDs, and unresolved links before enabling the explicit
write safeguard. Use one transaction per league, disable broad geocoding, and
validate both database invariants and the active `/leagues`, `/fixtures`,
`/nearby`, and `/venues` endpoints afterward. San Diego demonstrated why null
provider venue IDs must remain unresolved until a reviewed canonical override
exists, and why direct provider venue data must retain highest precedence.

## Coordinates and retry process

The importer generalizes the prior England repair approach rather than replacing
it. Production `--no-geocode` writes preserve existing valid coordinates and
apply only accepted `geocoded` checkpoint results. An explicitly enabled audit
or enrichment run may use the Nominatim ladder:

1. stadium, address, city, country
2. address, city, country
3. stadium, city, country
4. stadium/address with the short city
5. stadium, country
6. stadium name

HTML entities and whitespace are normalized first. Nominatim uses a named
Terrace Talk user agent and waits at least 1.1 seconds after every request.
Resolved venues are not geocoded again on later imports. Invalid results are
never written. The QA report exposes records that still need retry/manual
review; name-based repair must not guess ambiguous matches.

The current schema has no `coordinate_source` column. A later migration may add
`api_football`, `nominatim`, or `manual`, but that is intentionally not bundled
with this importer because it changes the live database schema.

## QA and quota

Every report includes country, league, provider/display season, availability,
API requests/cache hits/failures, team/venue/fixture counts, planned new versus
updated records, provider venue linkage, coordinate status, unresolved venues,
ambiguous matches, and duplicate provider IDs.

Prefer cached dry runs, do not call country-wide `/venues` when team/fixture
venue records suffice, and do not repeatedly geocode already-resolved venues.
Run one league at a time while validating new countries. England data is never
deleted by this tool; the historic malformed 2026 rows require a separately
reviewed migration/reimport plan.

## Sweden unresolved-link resolution

Audit unresolved Swedish fixtures by home team and league, retaining fixture
counts plus every fixture-level and team-level venue name, city, and provider
ID. Classify each group before considering a write:

- `safely_resolvable_provider`: one authoritative provider venue ID maps to one
  canonical venue;
- `candidate_manual_override`: one consistent named venue exists, but its
  identity and locality still require independent review;
- `ambiguous`: the evidence conflicts or indicates multiple grounds;
- `no_venue_data`: neither fixture nor team metadata identifies a venue.

Do not use fuzzy name matching to move a group between classes. In the 2026
audit, AFC Malmö/Hyllie IP and Lilla Torg/Hästhagens IP remained candidates
because the cached provider data named a ground but the coordinate/locality
evidence was insufficient. The other 217 unresolved Swedish fixtures had no
venue metadata and remain deliberately null.

## Manual override examples

San Diego FC/Snapdragon Stadium, Sporting JAX/Hodges Stadium, and
Brooklyn/Maimonides Park demonstrate the reviewed path. Each mapping is scoped
to provider, league, season, and home-team provider ID; each canonical manual
venue has a generated internal ID and a null provider ID. The narrow override
command updates only fixtures whose provider fixture venue ID is absent and
whose current canonical venue link is null. Direct provider venue data always
wins on a future refresh.

Fort Wayne/Ruoff Mortgage Stadium is intentionally not an override yet: only
some fixtures name the ground and the audit could not obtain a decisive cached
coordinate/locality match. Boise remains unresolved because the provider gives
no reliable venue data.

## Final coordinate review rules

Start with cached results, never re-query accepted venues, and require one
decisive name or alias match in the provider city/locality and country. Preserve
existing valid database coordinates. Keep multiple exact features ambiguous,
reject wrong-city candidates, and keep empty results unresolved. If a new
Nominatim call is necessary, use one worker, conservative spacing, bounded
rate-limit/network backoff, and immediate cache persistence. Only the explicit
`accepted` set may be applied by `ingestion.apply_reviewed_coordinates`.

## MVP country coverage, 2026

- England: 5,540 fixtures in 11 supported competitions; all fixture venue
  links resolve. Thirteen distinct referenced venues remain without accepted
  coordinates after conservative review.
- USA: MLS, USL Championship, and USL League One are loaded. Sporting JAX and
  Brooklyn are linked through reviewed manual overrides. Fort Wayne (16) and
  Boise (16) remain intentionally unresolved.
- Sweden: 2,040 fixtures across the two national divisions, both Ettan groups,
  and all six available Division 2 groups. The audit added 39 accepted venue
  coordinates. The 245 unresolved fixture links remain null because no safe
  provider link or fully verified manual mapping was available.

The authoritative machine-readable audits are
`reports/ingestion/unresolved-link-review-2026.json`,
`reports/ingestion/mvp-coordinate-gaps-2026.json`, and
`reports/ingestion/mvp-data-quality-final-2026.json`.
