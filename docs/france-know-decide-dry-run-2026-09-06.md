# France KNOW + DECIDE dry run — 2026-09-06

## Outcome

The approved 36-club France KNOW package and 59-fact France DECIDE catalogue reconcile without an architectural or editorial blocker. No hosted write or migration was performed.

KNOW is editorially/canonically resolved but requires 36 deterministic `CURRENT/HOME` `club_venues` relationships. Paris FC resolves through the reviewed fixture-provider identity `api_football:18861` to canonical Stade Jean Bouin (`venue_id=23298`); no provider-reference write is required. The generated relationship inventory is a dry-run artifact only.

## KNOW reconciliation

- Ligue 1: 18 subjects.
- Ligue 2: 18 subjects.
- Total: 36 subjects; all canonical team IDs resolved.
- Before the Match: 21 populated; 15 intentional NULLs retained exactly.
- Tickets: 36 current first-party club routes. Queue/403 behavior on some ticket platforms does not change first-party provenance.
- Entry: 0 candidates in this artifact; 36 omissions. The brief permits NULL Entry, and exact current first-party wording was not supplied for safe publication. No claim was inferred from research notes.
- Destinations: every populated record has a named place plus exact supplied address, or a deterministic named supporter area + canonical stadium + city + France target. No coordinates or unsupported street addresses were invented.
- Provider venues: 36/36 complete. Paris FC's unanimous current fixture-provider identity resolves to provider-backed canonical venue `23298`, taking precedence over duplicate manual venue `23300` and stale team-default Charléty.
- Ownership: 0/36 current `club_venues`; 36 deterministic later-remediation rows prepared, with no write performed.
- Rennes: canonical HOME remains Roazhon Park `23287` (17 current league home fixtures). One current alternate venue row does not create an ownership ambiguity.

The complete schema-equivalent inventory is `reports/france/france-know-publication-inventory-20260906.csv`. The deterministic later-remediation inventory is `reports/france/france-club-venue-remediation-dry-run-20260906.csv`.

## DECIDE reconciliation

- Existing approved France catalogue: 47/47 accounted for.
- Hosted already present: 37.
- Existing approved facts recovered through explicit deterministic venue aliases: 2 proposed inserts (`Stade Bonal` → Stade Auguste-Bonal `23033`; `Stade Vélodrome` → Stade Orange Vélodrome `23283`).
- Genuinely dormant: 8, retained as catalogue-valid with `DORMANT_NO_WRITE`.
- New Great Support: exactly 12 current canonical TEAM facts, all proposed inserts.
- Total represented: 59; 51 current and 8 dormant; 37 already present, 14 proposed inserts, 8 dormant/no-write.
- No NO or insufficient-evidence record is proposed. No attendance ratio, score, or extra club is used.

Genuinely dormant facts are Bordeaux–Toulouse, Montpellier–Nîmes, Bastia–Ajaccio, Reims–Sedan, Marseille–Toulon, Concarneau–Stade Briochin, Stade de France, and Stade François-Coty. Their editorial facts remain approved; only current usable subject inventory is absent.

The complete 59-row reconciliation is `reports/france/france-decide-reconciliation-20260906.csv`.

## Safety and validation

The dry-run command opened a hosted transaction, issued `SET TRANSACTION READ ONLY`, queried identities and existing facts, and rolled back. Output confirms `hosted_writes=0` and `migrations=0`. No canonical team, venue, fixture, England, Germany, KNOW, or DECIDE row changed. No deployment occurred.

The artifact validates exact 18/18 league populations, 36 KNOW subjects, 21/15 BTM partition, deterministic populated destinations, HTTPS ticket routes, zero invented Entry facts, exactly 47 existing DECIDE facts, exactly 12 approved Great Support facts, and 59 total catalogue rows.

## Review gate

Before a protected publication: review the 36 proposed HOME relationships; execute the established protected relationship remediation; regenerate a hash-approved generic KNOW candidate with the resulting `club_venue_id` values; then perform one fresh read-only preflight. Duplicate venue `23300` and its fixture links remain a separately protected future cleanup and must not receive France KNOW ownership.

**READY FOR RAY REVIEW BEFORE PROTECTED FRANCE PUBLICATION**

## Protected publication result

Published and independently reconciled on 2026-09-06 after the approved Paris FC correction to provider-backed canonical Stade Jean Bouin `23298`. The transaction inserted 36 `CURRENT/HOME` relationships, 36 ticket facts, 21 Before-the-Match spots, 21 evidence rows, and 14 DECIDE facts. It performed no updates or deletes and made no provider-reference, venue, team, fixture, England KNOW, Germany KNOW, or non-France DECIDE mutation.

The eight dormant/no-write catalogue facts remain Bordeaux–Toulouse, Montpellier–Nîmes, Bastia–Ajaccio, Reims–Sedan, Marseille–Toulon, Concarneau–Stade Briochin, Stade de France, and Stade François-Coty.

Future protected cleanup: venue `23300` duplicates provider-backed Stade Jean Bouin `23298` and retains 17 Paris FC fixture links. Consolidation and fixture relinking were deliberately excluded from this publication.
