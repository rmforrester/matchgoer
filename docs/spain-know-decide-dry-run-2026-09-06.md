# Spain KNOW + DECIDE publication ? 2026-09-06

**PASS ? SPAIN KNOW + DECIDE PUBLISHED AND RECONCILED**

The protected publication committed and an independent read-only hosted reconciliation passed. All three reviewed CSVs remain byte-for-byte unchanged. The existing France architecture was retained, with a minimal bounded-column migration and existing Entry/BTM models.

## Final state

- KNOW: 42 clubs (20 La Liga, 22 Segunda), 42 Tickets, 18 BTM, 24 intentional BTM NULL, 5 Entry, and 18 accepted BTM evidence rows.
- HOME/CURRENT: 42/42 correct, exactly one per scoped team, with no duplicates or senior/reserve collapse.
- Entry: FC Barcelona, Burgos CF, CD Eldense, FC Andorra and SD Eibar; all five descriptions and source URLs preserved exactly.
- BTM: all 18 display names, supporting lines, maps destinations, classifications, audience, status, confidence and order match the reviewed CSV. No truncation or new subjects. Two INDEPENDENT evidence classifications map to the existing EDITORIAL_RESEARCH source type with the reviewed classification retained in the evidence note; 16 use OFFICIAL. Empty reviewed evidence URLs remain NULL.
- DECIDE: all 52 reviewed catalogue rows represented; 51 live/current, one dormant/no-write (C?diz ? Xerez). 36 existing facts retained and 15 inserted. No duplicate natural keys or unapproved Spain facts.
- Catalogue categories: 21 SIGNIFICANT_RIVALRY (20 live, one dormant), 11 CLASSIC_GROUND, 6 FOOTBALL_LANDMARK, 2 UNIQUE_SETTING and 12 EXCEPTIONAL_SUPPORT.
- Great Support, exactly 12 live TEAM facts: Athletic Club, Real Betis, Sevilla FC, Rayo Vallecano, CA Osasuna, Racing Santander, Real Sporting, Real Oviedo, RC Deportivo, Cádiz CF, Málaga CF, CD Castellón.

## Capacity migration and exact text

- Previous limit: VARCHAR(180). New limit: VARCHAR(255), NOT NULL retained.
- Migration: `backend/migrations/20260906_btm_supporting_line_capacity.sql`.
- Safe rollback: `backend/migrations/20260906_btm_supporting_line_capacity_rollback.sql` refuses narrowing if any value exceeds 180; the live read-only guard test passed after publication.
- Maximum approved supporting-line length: **221 Unicode characters**. All 18 stored strings match the reviewed CSV exactly. Individual UTF-8 hashes and character lengths are recorded in the post-publication reconciliation JSON.
- ORM and generic KNOW validation now use 255; tests accept 180/221/255 and reject 256. Existing Pydantic response and frontend types impose no 180-character limit and needed no changes.
- Schema verification proved only the intended capacity changed: constraints, indexes, triggers and all other columns were unchanged. All 27 public tables retained their data during migration; the heap file was not rewritten.
- Migration SHA-256: `40DDD4E6FA9D727C5AC03D21130132BB4E75C6FF109F62515AA4EDBE023D70F1`.

## Physical database diff

| Table | INSERT | UPDATE | DELETE |
|---|---:|---:|---:|
| club_venues | 42 | 0 | 0 |
| decision_evidence | 0 | 0 | 0 |
| decision_facts | 15 | 0 | 0 |
| fixtures | 0 | 22 | 0 |
| pre_match_spot_evidence | 18 | 0 | 0 |
| pre_match_spots | 18 | 0 | 0 |
| teams | 0 | 0 | 0 |
| venue_guide_facts | 47 | 0 | 0 |
| venue_names | 1 | 0 | 0 |
| venue_provider_refs | 0 | 0 | 0 |
| venues | 1 | 41 | 0 |

**Total: 142 inserted rows, 63 updated rows, zero deletes.** The physical diff exactly matches the final dry-run plan. All 27 public tables were fingerprinted; unrelated row mutations were zero.
The 41 venue-row updates decode exactly 44 approved city/address values. The 22 fixture updates change only venue_id: 21 Andorra fixtures and one Real Madrid fixture. Every changed column was checked; no team or provider-reference row changed. One separate schema migration widens the supporting-line column; the publication transaction itself performs no DDL.

## Canonical and fixture reconciliation

- FC Andorra: new canonical venue **24094**, Estadi de la FAF, Carretera de Vila 23?25, AD200 Encamp, Andorra. No provider venue ID/reference, fabricated coordinates, or capacity. One current canonical venue-name row was created.
- Estadi Nacional **23567**, Andorra la Vella, and api_football:2618 remain unchanged.
- Exactly 21 FC Andorra 2026 Segunda home fixture IDs now link to 24094:

1569872, 1569894, 1569915, 1569928, 1569960, 1569983, 1570003, 1570025, 1570047, 1570071, 1570102, 1570124, 1570147, 1570180, 1570202, 1570223, 1570236, 1570258, 1570267, 1570289, 1570311.

- The five provider-unspecified Andorra fixtures described in the review are not hosted. None was inserted or assigned.
- Real Madrid fixture **1570340 ? 23269**. All **19/19** 2026/27 La Liga home fixtures now link to Santiago Bernab?u, whose primary provider reference remains api_football:1456.
- Real Murcia: canonical team **5275**; Cartagena: **5262**. Their reviewed rivalry remains live. Zero Real Murcia venue/provider/fixture mutations; provider venue 3989 inconsistency remains a later audit item.
- Preserved HOME exceptions: Rayo/Vallecas 23276; Celta Fortuna/Barreiro 23568; Real Sociedad B/Zubieta 23570; Betis/La Cartuja 23271; Barcelona/Camp Nou 23260; Valencia/Mestalla 23263. Rayo?s Butarque and Celta Fortuna?s Bala?dos fixture exceptions were untouched.

## Ticket maintenance

All 42 reviewed club routes passed the maintenance acceptance check. Five deterministic replacements were kept outside immutable CSVs and applied only to the published ticket URL:

| Club | Published official route | Source confirming destination |
|---|---|---|
| Racing Santander | https://abonados.realracingclub.es/ | https://www.realracingclub.es/noticias/arranca-la-venta-anticipada-de-entradas-para-la-visita-del-deportivo-alaves-a-los-campos-de-sport |
| RCD Espanyol | https://www.rcdespanyol.com/es/proximos-partidos | https://www.rcdespanyol.com/es/ |
| CE Sabadell | https://cesabadell.compralaentrada.com/ | https://www.cesabadellfc.com/ |
| Real Valladolid CF | https://www.realvalladolid.es/ticketing | https://www.realvalladolid.es/ticketing |
| UD Almería | https://tickets.udalmeriasad.com/ | https://www.udalmeriasad.com/ |

Espanyol, Valladolid and Almer?a?s old routes returned 404; Sabadell redirected to an old away-match article; Racing?s old route persistently timed out. All five replacements returned 200 and were linked from the same club?s official site. Deportivo and Legan?s retain their working reviewed redirects to club ticket platforms.
Four first-party routes returned access restrictions (403), retained under the France precedent. Rayo?s exact reviewed endpoint remains published with its documented branded 503 limitation, as explicitly authorized. No aggregator was invented.

## HTML normalization

Exactly 44 semantic values across 41 venues were normalized, matching the prior audited count with zero drift and zero new identity collisions. The post-write scan finds zero remaining decodable HTML references in city/address. Lille venue 23281 stores **Villeneuve d'Ascq** and its actual hosted values pass the VenueHeader rendering acceptance test.
The ingestion boundary uses the standard HTML decoder on complete known references, only for city/address. It preserves Unicode, ordinary ampersands and unknown reference names. Nested encodings are held for review rather than repeatedly decoded, preserving idempotency. Normal escaped React text rendering remains in place; malicious HTML-shaped text is safely escaped. No dangerouslySetInnerHTML or ad hoc apostrophe replacement was introduced.

## Reviewed input hashes

- `spain-know-publication-inventory-20260906.csv`: `665DA96BEBB2975D2ECBBEE2D9DB00E08DA9E7BCFAB312F0C5F2F4F4CE1E6596`
- `spain-decide-reconciliation-20260906.csv`: `6C995556C74D39209E30AB3BB018C0CCF97D3470D6F6604C10C6D0F7C39938B7`
- `spain-club-venue-remediation-dry-run-20260906.csv`: `2E2D179345AC2D71A34F5111FDA5982CB54146DAA63EF269FFA25A7686E1DB3C`

`reports/spain/.gitattributes` disables text conversion for the three immutable CSVs so committed/check-out bytes retain these hashes.

## Validated full PostgreSQL backups

Both full custom archives passed pg_restore --list and a complete decode to null output, using PostgreSQL tools 18.4.

**Immediately before migration**

- Path: `C:\Users\rmfor\OneDrive\Documents\terrace-talk\backups\hosted\matchgoer-hosted-pre-spain-capacity-publication-20260906T182208Z.dump`
- UTC: `2026-09-06T18:22:08.965632+00:00`
- Size: 743,963 bytes.
- SHA-256: `0E45859068C6963F91B6639004DA6C97F6159136A7DFCE491501AFD6637FE38E`
- Archive validation: PASS.

**Immediately before successful publication**

- Path: `C:\Users\rmfor\OneDrive\Documents\terrace-talk\backups\hosted\matchgoer-hosted-pre-spain-publication-final-20260906T182747Z.dump`
- UTC: `2026-09-06T18:27:47.754828+00:00`
- Size: 743,963 bytes.
- SHA-256: `E9BAAAA232CF99A2C76C4F7A496BFF17C13BBC7795C9A62BBFE4758010DFBC33`
- Archive validation: PASS.

## Tests and safeguards

Final main regression run: **114 tests, 109 passed, 5 skipped, zero failures/errors**. The Germany remediation module passed its two tests in its original worktree, for **111 passed and 5 skipped overall**. Skips are two optional English candidate-environment tests and three isolated PostgreSQL round-trip tests without a test database URL.
The suite covers required KNOW, DECIDE, decision, club-venue KNOW, France, Spain and Germany tests, the changed English batch-2 fixture schema, provider text, venue reuse and fixture overrides. Python compilation and actual VenueHeader SSR pass. Live checks additionally verify the minimal migration, exact 18 BTM texts, rollback refusal and full final publication state.
Test setup issues were resolved without changing unrelated work: Germany tests ran in their existing worktree; the English batch-2 reviewed fixture was copied locally after hash verification and is excluded from these commits.
Before successful publication, two attempts rolled back: first the 180-character schema limit, then a reconciliation implementation defect that omitted DECIDE-only opponents because teams has no country column. Both now have regression guards/tests. The latter test reproduced the defect before the fix and passes with the corrected canonical subject scope. No partial publication rows persisted from either attempt. Nontransactional sequence advances were retained without rewinding.
Write required explicit --write, --confirm-write and --allow-remote-write, publisher/artifact/implementation hash gates, fresh plan matching, a validated matching database backup and a serializable transaction. The final publisher script hash is `5ADCBAD7827F753DC6E951CE6DEBF7D27696D2912B1D7DC6A41CD7EC6796094A`.

## Integration, deployment and retained audit items

The capacity migration/model/validation change and the Spain publication/HTML change are delivered as scoped commits from the isolated Spain worktree. Exact commit IDs and final origin/master status are provided in the delivery message. Unrelated working-tree changes and the local English test fixture are excluded.
**Normal backend/ingestion deployment is required after merge** to load the new model/validation capacity and prevent future encoded city/address values. The hosted schema migration and data publication are already applied; do not reapply the data write. No frontend code changed, so no frontend-only deployment is required.
Intentionally unresolved: Real Murcia?s provider venue anomaly; Rayo?s branded 503 service limitation; the five provider-unspecified Andorra fixtures absent from hosted inventory. No editorial content is awaiting approval.

**PASS ? SPAIN KNOW + DECIDE PUBLISHED AND RECONCILED**
