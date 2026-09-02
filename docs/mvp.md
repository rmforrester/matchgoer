# Matchgoer MVP

> **Find football worth going to.**

Matchgoer is the companion for people who go to football. Product decisions should support the real supporter lifecycle:

**DISCOVER → KNOW → CONNECT → ATTEND → REMEMBER → CONTRIBUTE**

The canonical test is whether a supporter in an unfamiliar place can find a less-obvious match, gain enough practical confidence to attend, connect where useful, record the match and contribute knowledge for the next supporter. Personal ground history supports that journey; it must not turn Matchgoer into primarily a stadium-tracker app.

## Audience and journey

The target audience is football fans who attend live football across standards and stadium qualities: travellers, groundhoppers, local fans and casual matchgoers.

```text
Current location or city search
→ date, radius and league discovery
→ map and nearby fixtures
→ fixture or stadium detail
→ ratings and tips
→ Interested
→ optional Who's Going?
→ fixture Match Board/community
→ attend
→ My Stadiums
→ review or edit review
→ optional supporter tip
```

## Scope and status

| Area | Requirement | Status |
|---|---|---|
| Discovery | City/location search and Use my location | Done; plain HTTP LAN geolocation remains browser-limited |
| Discovery | Explicit Search with default 25-mile radius; radius, date and country-grouped multi-league filters | Done |
| Discovery | Fixture pins grouped per venue; Show all stadiums default off; searched stadiums independently discoverable | Done |
| Discovery | Nearby square-card carousel below map, within selected radius, earliest kickoff first | Done |
| Carousel | Teams, stadium/location, distance, kickoff, Terrace Rating and result when applicable | Done |
| Stadium | Venue pages, ratings/categories, tips and upcoming fixtures | Done |
| Stadium | Stable venue identity, current display name and reviewed searchable name history | Done; suspected duplicate provider records remain review-only |
| Personal | My Stadiums; add, review and edit a stadium | Done |
| Personal | Separate venue attendance/history from one-per-venue reviews | Done; legacy review columns retained for retirement compatibility |
| Personal | Import My Grounds: bulk migration of existing stadium history | Approved future; depends on registered accounts and canonical venue matching |
| Social | Anonymous Interested and dismissible account-conversion prompt | Done |
| Social | Who's Going? implies Interested and requires an account | Done; anonymous aggregate reading and registered-only intent writes enforced |
| Social | Fixture Match Board | Done for MVP; anonymous reading, registered posting, delete-own/report-other and completed-board closure enforced |
| Accounts | Confirmed-email signup/sign-in, anonymous-to-registered conversion and cross-device persistence | Phase 4E implemented; existing-account merge not implemented |
| Visual system | Modern Fanzine with Away Day / wayfinding elements | Homepage, fixture-detail and venue-detail passes implemented; remaining application screens not started |
| Testing | Phase 3.5 real-world supporter journey QA | **Next roadmap gate; required before major visual or feature expansion** |
| Testing | Automated browser/API regression suite and public user testing | Not started |

The nearby carousel follows the selected radius (25 miles by default), orders qualifying fixtures by kickoff and then fixture ID before applying its result cap, and shows teams, ground/location, distance, day/time, Terrace Rating, recommendation signal and score/result where available.

Discovery has two explicit geographic modes: **location search = centre + selected radius**, while **Search This Area = the visible map viewport bounds**. Map-area results preserve dates, leagues and Show all stadiums, remain chronologically ordered and do not silently reapply the radius. The result UI identifies viewport searches as **Matches in this area** and distinguishes displayed from total matches when the safe cap is reached.

Discovery uses one matchday-planning form. Users set a city or current location, dates, radius, one or more stable league IDs and the optional Show all stadiums flag, then explicitly apply them with Search. A successful search collapses to a compact visible summary with an Edit search action; editing draft controls does not silently change the current result set.

Map fixture markers use the venue as the grouping unit for the qualifying search results. Each venue gets one fixture marker; its popup starts with the earliest kickoff and provides previous/next controls when the venue has multiple fixtures in the active result set. Fixtures without a venue ID remain separate rather than being grouped together.

## Stadium experience

- Venue identity, capacity and location.
- Community Terrace Rating, recommendation percentage and category scores.
- Matchday tips with helpful/report actions.
- Upcoming fixtures and Interested state/count.
- Visited, reviewed and editable review states in My Stadiums.
- One optional review per user and venue, independent of repeat venue visits.

Matchgoer now uses `venue_visits` for repeat attendance/history, My Grounds membership, map visited state and distinct-ground profile counts. Completed fixtures record attendance independently of reviews; My Matchdays includes fixture-linked attended history; and My Grounds supports simple additional dated visits. Every legacy ground has a reconciled visit. Reviews remain one optional venue opinion, with legacy columns and blank migrated review rows retained only for Phase 4 compatibility.

## Social intent

- Interested is a low-friction anonymous action.
- Enabling Who's Going? implies Interested; anonymous supporters are offered account creation or sign-in before intent is created.
- Removing Interested removes an associated Who's Going? intent.
- Match Boards are fixture-specific and readable anonymously.
- Match Board posting requires a registered account with a complete canonical Matchgoer profile. Authors may delete only their own posts; registered supporters may report another author's post once.
- Completed Match Boards remain readable, retain existing posts and reject new posts.

Fixture actions follow the match lifecycle. Before full time, Interested and Who's Going? support planning and social intent. Once provider status is `FT`, `AET` or `PEN`, the fixture instead asks whether the supporter attended and routes them through the existing My Grounds review for that venue, followed by an optional prompt to add a supporter tip. Live fixtures retain the pre-match social actions until they are completed.

## Data coverage

- England men's pyramid through the Step 7-equivalent premier divisions currently available from API-Football for provider season 2026.
- USA priority profiles: MLS, USL Championship and USL League One.
- Sweden priority profile: Allsvenskan through available national/Ettan/Division 2 competitions.
- Country and league expansion uses reusable profiles and the same reviewed pipeline.
- Provider fields are translated into a multi-provider-ready canonical model; API-Football remains the first provider.

Coverage is constrained by provider availability and reviewed venue quality, not by silently fabricated links.

## Working visual direction

**Modern Fanzine with Away Day / wayfinding elements.**

- Draw from supporter fanzines rather than conventional score or betting products.
- Use strong editorial typography and hierarchy.
- Centre football culture, travel and match discovery.
- Avoid sportsbook and generic sports-app styling.
- Avoid fake distressing or novelty “fanzine” effects that reduce clarity.
- Begin the visual-system work before broad public user testing.

The homepage is the **Matchgoer Reference Design / Design System V1**. Its direction combines Modern Fanzine × Away Day, Barlow Condensed editorial typography, Geist utility typography, the royal-blue/newsprint/near-black palette, flat paper surfaces, strong rules, restrained rounding, numbered editorial sections, vertical HOME / VS / AWAY fixtures and publication-style recommendations. Functional controls remain visually secondary to football content. Fixture detail applies the system as a matchday programme, while venue detail uses it as an editorial ground guide centred on Terrace Rating, the user’s visit, supporter tips and upcoming fixtures. Other core screens should follow these principles without copying these layouts literally. The working navigation labels are **Discover**, **My Matchdays** and **My Grounds**; routes and internal ownership concepts remain unchanged.

### Design System V1.1 — product surface differentiation

Matchgoer keeps one Modern Fanzine × Away Day identity while giving its three primary destinations different compositional roles:

- **Discover = exploration / geography:** a compact planning sheet leads quickly into the map, fixture options and editorial recommendations.
- **My Matchdays = timeline / diary:** dense chronological cards separate upcoming plans, decisions still needed and attended history.
- **My Grounds = collection / passport / personal map:** My Football World and its map lead into a scalable collection of compact ground records.

**App-first principle:** design decisions prioritize common 375–430px mobile widths, one-handed use, 44px primary targets, short paths to football content and future app/PWA use. Desktop remains supported without driving oversized mobile heroes. A top-navigation versus bottom-tab-navigation comparison is a **future UX experiment only**; V1.1 retains the single top navigation.

My Grounds exposes one supporter-facing **Add a visit** flow. A remembered date is used to suggest trusted fixtures: selecting one creates fixture-linked attendance and therefore a My Matchdays entry; choosing none creates a manual dated visit; where safe, not remembering the date creates a manual undated visit. Adding a visit never edits an existing date-unknown visit, and venue reviews remain separate.

For a future app-shell experiment, compare the current top navigation with fixed bottom tabs for **Discover**, **Matchdays**, **Grounds** and **Profile / Account** after account/profile implementation exists. Do not ship both navigation systems concurrently during the current MVP.

Map locations use the shared **Matchgoer location marker**: a flat, angular royal-blue symbol with a near-black outline, pointed base and simple paper-white M monogram. Visited grounds retain the blue Matchgoer marker and add a small paper-white badge with an explicit blue check, preserving the hierarchy of Matchgoer ground first and visited state second. The visual symbol remains approximately 30px while retaining a 44px interaction target.

## Next roadmap gate: Phase 3.5

Before further major visual or feature expansion, run **Phase 3.5 — Real-World Supporter Journey QA** against the canonical lifecycle:

```text
DISCOVER → DECIDE → PLAN → ATTEND → RECORD → REVIEW / CONTRIBUTE → REMEMBER → REPEAT
```

DECIDE must not bias toward famous top-flight football merely because it is easier to document. Its highest-value use is often important football that a travelling or unfamiliar supporter might otherwise overlook: major lower-league and regional rivalries, traditional grounds across the pyramid, and unusual or historically important grounds outside elite divisions. The editorial test remains: **Would a knowledgeable matchgoer tell another supporter to consider this fixture or ground specifically because of this characteristic?** Prioritisation should also ask: **Is Matchgoer telling the supporter something useful they may not already know?** Obscurity is not inherently better; famous fixtures and grounds still qualify when they genuinely meet the criteria.

This gate evaluates Matchgoer around real football attendance rather than as isolated features. The 20 manual scenarios, state expectations, failure conditions and observation questions are defined in [Supporter journey QA](supporter-journey-qa.md). The previously planned **My Matchdays Design System V1** pass remains next, immediately after this QA gate and its findings review.

Where space permits, a vertical fixture always uses equal-weight team names with `VS` as a standalone separator: **HOME TEAM / VS / AWAY TEAM**. `VS` is never appended to either club name. Compact contexts may remain single-line where that is more usable.

Preferred Matchgoer product vocabulary includes **Terrace Rating**, **What the Terrace Says**, **From the Terrace** and **Make It One of Yours**. Use these phrases where they clarify the relevant rating, supporter-knowledge or ground-ownership context; they are not mandatory labels for every screen.

### Future homepage module: From the Terrace

Once genuine community activity exists, the homepage may introduce **From the Terrace** for recent reviews, supporter tips and matchday posts. It should not launch as an empty or artificial feed; inclusion depends on enough authentic activity to keep the module useful.

### Future beta experiment: recommendation order

Test whether **Search → Map → Worth the Trip → All Matches** performs better than **Search → Map → What's On → Worth the Trip**. The hypothesis is that answering “What should I actually go to?” earlier may communicate Matchgoer's differentiated value more effectively. Keep the current order until beta-user evidence supports a change.

## Approved future: Import My Grounds

> **Move your football history to Matchgoer in minutes, not hours.**

Import My Grounds is a future registered-account onboarding and migration capability for established fans and groundhoppers. It should populate My Stadiums without requiring someone to add hundreds of grounds individually.

The preferred import hierarchy is:

1. **Direct import/export support:** investigate official exports, APIs or user-provided exports from established football and groundhopping services. Do not assume a particular service offers usable access until technical and legal implementation research verifies it.
2. **File import:** accept common structured formats such as CSV and Excel. Stadium name is the core input; club, city, country, visit date, fixture/opponent, competition and notes are optional enrichment.
3. **Copy/paste:** accept a simple list of current or historical ground names.
4. **Mass selection:** provide mobile-friendly country -> league -> club -> stadium browsing, search, multi-select, bulk select/deselect and clear visited/unvisited controls.

### Matching and review

Imports must resolve to Matchgoer's stable `venue_id`, using current names, reviewed aliases/name history, provider references, city, country, club/team and appropriate coordinate evidence. For example, an imported `Tele2 Arena` should resolve to the canonical `3Arena` venue when confidence is high. A differing name must not create a duplicate venue.

Matches should be classified as:

- **High confidence:** automatically matched and selected.
- **Ambiguous:** user chooses from likely canonical venues.
- **No match:** user is offered review and venue search.

The user reviews exceptions, not every successful match. Before committing, show a preview such as: `157 grounds found; 151 ready to import; 4 need your help; 2 not found.` Nothing is written until that preview is confirmed.

### Data and ownership

- Re-importing a venue already in My Stadiums must not create an accidental duplicate.
- Visited-venue state must remain distinct from future individual match/visit history.
- The first release may import only visited venues, but its design must allow later preservation of first visit, multiple visits, attended fixture, date, teams, competition, result and notes.
- Bulk import requires a registered account and must attach imported history to the approved persistent `users.user_id`, including after anonymous-to-registered conversion.

This roadmap item depends on stable canonical venue identity, venue aliases/name history, account persistence and robust duplicate handling. The intended onboarding path is: **Already use another football app? -> Import my grounds -> Upload, paste or select -> Review exceptions -> Import -> My Stadiums populated.**

Potential success measures are automatic-match rate, median completion time, manual confirmations per 100 grounds, abandonment rate, grounds imported per user, and conversion or retention among importing users. The primary UX objective is to minimize the actions required to migrate an established fan's history.

**Status: approved future capability; no import UI, parser, matching workflow or persistence behavior is implemented.**

## Explicitly deferred

Account merge/linking, Import My Grounds, completed closed-beta deployment, advanced moderation, advanced visit/fixture editing, gamification and a broad visual redesign are not currently live. Phase 5C repository deployment preparation is complete, but invitations remain gated on the external HTTPS environment and deployed mobile acceptance in [Closed-beta deployment](deployment.md).
