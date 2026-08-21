# Phase 3.5 — Real-World Supporter Journey QA

**Status: next roadmap gate. Complete this manual journey QA before further major visual or feature expansion. The planned My Matchdays Design System V1 pass follows immediately afterward.**

This phase tests Matchgoer as a supporter would use it around real football attendance, rather than validating isolated controls or endpoints. Findings should be recorded before fixes are designed.

## Canonical supporter lifecycle

```text
DISCOVER → DECIDE → PLAN → ATTEND → RECORD → REVIEW / CONTRIBUTE → REMEMBER → REPEAT
```

Run journeys on a realistic mobile viewport and desktop where relevant. Preserve the same user/session throughout a scenario and inspect API/database state only to verify the product outcome.

## First testing pass — findings and retest status

Phase 3.5 remains **in progress**.

### Phase 4E account-journey retests

Run these in isolated browser profiles with disposable confirmed-email identities:

- **Anonymous history conversion:** Create Interested, a visit and optional review/tip; sign up; confirm email in the same browser; verify automatic claim retains the internal owner and every record; complete onboarding; confirm the original destination resumes.
- **Fresh account:** Begin without meaningful anonymous activity; create and confirm an account; verify setup completes without merge/conflict language.
- **Existing account, empty shell:** Sign into a mapped account with only an auto-created empty cookie owner; verify the correct registered history loads without an alarming conflict screen.
- **Existing account, meaningful device activity:** Sign into a mapped account while the cookie owns real activity; verify the Phase 4D holding state, no merge, no record movement and no session revocation.
- **Restoration and logout:** Refresh a registered route and verify Supabase restores/refreshes the bearer session without an incorrect anonymous flash. Log out, verify registered controls disappear, and confirm a new anonymous session is created only when an anonymous-capable action needs one.
- **Username:** Test 3 and 30 characters, invalid punctuation/spacing, case-insensitive collision, useful unavailable copy, and preservation of an existing lightweight profile during onboarding.
- **Return safety:** Exercise fixture and My Matchdays return paths, plus external and protocol-relative inputs; only normalized internal routes may be followed.

Observe whether account creation feels like unlocking existing Matchgoer history rather than starting again, whether confirmation instructions are sufficient, and whether the account controls fit at 375–430px without crowding primary navigation.

### Scenario A — Discovery and map

- **Result:** Discovery itself works.
- **Finding:** Panning the map did not offer a way to search from the newly viewed center.
- **Finding:** A fixture inside a map popup did not link directly to its fixture page.
- **Remediation:** Added thresholded **Search this area** behavior and a per-fixture **View match** action.
- **Status:** Retest required. Browser-level pan, zoom, popup cycling and navigation have not yet been revalidated by this documentation update.

### Scenario B — Interested and social planning

- **Result:** **Blocked / partial**, not failed. Interested exists and can be validated independently.
- **Remediation:** Phase 4E implements confirmed-email signup/sign-in, automatic in-place claim, minimum profile onboarding and return-to-fixture behavior. The product action is now **Who's Going?**.
- **Status:** Phase 4E account acceptance and Phase 4F registered-social acceptance passed on 20 August 2026. Anonymous gates, registered Who's Going?, post/refresh/delete-own, closed-board reading and server-side closed posting rejection were exercised live.

### Scenarios C/D — Attendance and repeat/manual visits

- **Result:** The attendance/visit architecture works.
- **Finding:** The repeat/manual visit interface did not make its commit action sufficiently clear.
- **Finding:** “Includes undated visit” exposed implementation language rather than supporter language.
- **Remediation:** The repeat flow now presents **Add another visit → Date → Add visit**, refreshes My Grounds after success, and describes unknown history as **1 visit with date unknown**.
- **Status:** Retest required for same-date idempotency, different-date increments, review preservation, known-date summaries and retention of the date-unknown visit.

### Product observation

Adding another visit must remain distinct from assigning a date to a previously date-unknown historical visit. The current action creates a separate dated visit and preserves the unknown historical visit. A future flow should support **Add / edit date** on an existing date-unknown visit; no such mutation is implemented in Phase 3.5.

### Second remediation pass

- **Search this area:** Real-world testing found that the submitted origin could revert to an unrelated/default location. The action now reads the live Leaflet center at the moment it is pressed, logs previous/requested coordinates, and asserts that the applied coordinates match that live center. Retest with a known city-to-city pan remains required.
- **Completed Interested fixtures:** They now require an explicit post-match choice: record attendance or remove the fixture from plans. Interested never infers attendance automatically.
- **Closed Match Board:** An empty board for a completed/closed fixture now says the board is closed and the match has finished; it no longer implies that posting may begin later.
- **Historical attendance:** My Grounds now offers a lightweight past-match lookup around a remembered date. A known fixture creates fixture-linked attendance; “I don’t remember / none of these” creates a dated manual visit.
- **Status:** These paths require real browser retesting; Phase 3.5 is not complete.

## Historical attendance product rule

> **Ask the supporter what they remember; derive the rest from trusted fixture data.**

Historical attendance must support three honest levels of recall:

- **Exact fixture known:** attach attendance to the trusted fixture record.
- **Approximate date known:** show likely fixtures at the already-known venue around that date and let the supporter choose.
- **Venue only known:** preserve a manual date-unknown visit without forcing teams, competition, score or false precision.

## Attendance, review and contribution rule

```text
ATTENDANCE = I was there
REVIEW = my structured opinion of the ground
TIP = practical knowledge for the next supporter
```

Recording attendance must never depend on completing a review or tip. Creating or editing a review should offer an optional path into the existing venue-tip flow, without storing tip text in the review or changing visit/review counts.

### Additional remediation expectations

- Opening **Rate this ground**, **Continue review** or **Edit my review** from My Grounds exposes the form directly beneath that ground’s summary; the supporter must not search for a panel at the bottom of the page.
- Both new and existing reviews show an optional **Got a tip for the next supporter?** path into the existing Matchday Tips form.
- Completed Interested fixtures use **I went to this game** or **I didn’t go**. The first idempotently records attendance and moves the match to Attended; the second removes Interested without attendance.
- A completed fixture with existing attendance displays **Attendance recorded** and must not create another visit.
- After attendance, Rate/Edit Review and Add a Tip remain optional follow-up actions.
- Closed, empty Match Boards use final-state copy and never imply that posting will reopen.

Retest review-panel placement and keyboard focus/scroll context, saving with no tip, tip submission side effects, both completed-Interested choices, repeated attendance clicks, existing-review preservation and closed-board copy before completing Phase 3.5.

### Third refinement retests

- **Historical fixture ranking:** Verify exact-date fixtures appear first, followed by ±1 day, ±3 days and then the remainder of the lookup window. Multiple exact-date fixtures must be ordered by kickoff and fixture ID. Also test a date with no exact match.
- **Inline tips:** Test both first-review and edit-review flows. Opening or closing the reused inline tip form must preserve unsaved review fields; saving a tip must leave visit and review counts unchanged and keep the supporter in My Grounds.
- **Personal football map:** Observe whether one marker per canonical visited venue makes My Grounds feel like personal football history, whether the compact map earns its position above the cards, and whether the unplottable-ground message is understandable.

> **My Grounds is not just a checklist. It is the user’s personal football history.**

Future map extensions, not implemented in this phase, may include year filtering, country/city filtering, most-visited-ground summaries, repeat-visit intensity, shareable/exportable maps, collection overlays and personal milestones.

### My Matchdays Design System V1 remediation

- **Page hierarchy:** My Matchdays now separates **Upcoming**, **Needs Your Answer** and **Attended** beneath one editorial page identity. The redundant local My Matchdays / My Grounds destination switch has been removed; global navigation remains authoritative.
- **State presentation:** Upcoming cards present Interested and Who's Going? as planning states. Completed Interested fixtures without attendance move into **Needs Your Answer**, with no stale meeting-intent prominence. Fixture-linked visits alone populate **Attended**; manual dated and undated visits remain in My Grounds.
- **Consistency:** All three sections use the same date, vertical home/VS/away, ground/city and state-footer card skeleton, with mobile-first wrapping and touch targets.
- **Account status:** Anonymous Interested remains available. Who's Going? and Match Board writes now require a registered account with a complete profile; anonymous aggregate and board reads remain available.
- **Status:** Manual browser retest is required for upcoming and active Who's Going? states, both completed-plan answers, already-attended transitional records, long team names, narrow layouts and global-navigation active state. Phase 3.5 remains in progress.

### Design System V1.1 app-first retests

- **Discover:** At 375, 390 and 430px, confirm the initial planning sheet exposes its Search action without excessive scrolling, the active-search summary still collapses correctly, and the map/fixture content retains its exploration identity.
- **My Matchdays:** With at least three upcoming, one unresolved and several attended fixtures, confirm the real-count summary and compact diary cards support fast scanning, long club names wrap, and the attendance decision remains obvious.
- **My Grounds:** Confirm My Football World, its summary and compact map communicate personal history immediately; scan 5, 50 and conceptually 100+ collapsed ground cards without opening every history panel.
- **Known historical fixture:** Select **This one** and verify the created visit retains the selected `fixture_id`, appears in My Matchdays Attended, increments visit/matchday counts once and leaves the canonical ground and single review unchanged.
- **Unknown historical visit:** Select **I don’t remember / none of these** and verify the dated visit remains in My Grounds without creating a match in Attended.
- **App shell:** Confirm the active top destination is unmistakable and all three labels fit without horizontal overflow. Compare top navigation with a bottom-tab concept only in a future app/PWA experiment; do not ship both during this gate.

Phase 3.5 remains in progress until these browser journeys are completed.

### V1.1 usability-cleanup retests

- **Map popup and movement:** On a 375–430px viewport, open a grouped fixture popup, cycle its fixtures, use **View match**, dismiss it with the explicit close control, reopen it and dismiss by tapping the map. Confirm the map remains pannable and closing never resets the search or recentres the viewport.
- **Search This Area stability:** Pan from Manchester to Liverpool, press **Search This Area**, and verify the API origin and refreshed cards use the Liverpool-area center while the Leaflet viewport remains exactly where the supporter left it. Dates, radius, leagues and Show all stadiums must remain unchanged.
- **Post-match language:** Confirm the lifecycle summary avoids “To answer” and the completed-plan section reads **Did you go?**, with the existing **I went to this game** and **I didn’t go** outcomes unchanged.
- **Ground-card density:** At mobile widths, scan multiple collapsed cards and confirm each shows ground/location, visits, one latest date at most, both ratings and a dominant **View ground** action. Review, visit, past-match and history actions must remain discoverable but secondary; first/latest dates must not be duplicated.

Phase 3.5 remains in progress; these are manual browser retests, not completed checks.

### V1.1 viewport and visit-flow retests

- **Viewport query:** Begin with Luton + 25 miles, then pan/zoom wider and use **Search This Area**. Verify an in-view fixture beyond 25 miles appears, an out-of-view fixture does not, dates/leagues remain applied, and the map center and zoom do not change. Repeat with a dense London viewport and verify displayed-versus-total wording if capped.
- **Shared result universe:** Confirm TT markers, What's On and Worth the Trip all use the same viewport result set and say **Matches in this area**, not **Within 25 miles**.
- **Movement after search:** Open, cycle and dismiss a grouped popup, then pan or zoom again. Search This Area must reappear without popup or viewport jumps.
- **Add a visit:** Confirm each collapsed ground card exposes one Add a Visit action. Test exact fixture selection, none-of-these manual dating and the date-not-remembered path where available. Fixture selection must appear once in Attended; manual visits must not create fake matches; an existing unknown visit must not be silently replaced.
- **Recommendation density:** At 375–430px, verify empty Worth the Trip recommendations collapse to their copy and populated cards retain the intended fixture hierarchy without excessive padding.
- **Matchdays summary:** Confirm the hero contains only Upcoming and Attended counts while **Did you go?** independently communicates outstanding matches.

Phase 3.5 remains open pending these browser checks.

## Manual scenarios

### 1. Groundhopper in a new city

- **Starting state:** User has no active search for the destination.
- **Motivation:** Find a viable live match while travelling.
- **Actions:** Search the city; choose dates, radius and leagues; run Search; inspect map, nearby fixtures and a recommendation.
- **Expected product state:** Results share the chosen coordinates and filters; useful fixtures are ordered clearly; the selected fixture and ground can be opened.
- **Expected state outcome:** Discovery is read-only; no Interested, attendance, visit or review row is created.
- **Failure conditions:** Wrong location, hidden filters, irrelevant/out-of-radius result, conflicting map/list state, or no recovery from an empty search.
- **Observe:** Does discovery answer “what can I realistically attend?” quickly, and is city search as understandable as current location?

### 2. Fixture saved as Interested

- **Starting state:** Anonymous user has found an upcoming fixture and is not Interested.
- **Motivation:** Remember a possible match without committing to attendance.
- **Actions:** Select Interested; dismiss the account prompt; revisit the fixture and My Matchdays.
- **Expected product state:** Interested remains selected and appears under Upcoming after the prompt is dismissed.
- **Expected state outcome:** One `interested_fixtures` row owned by the current `users.user_id`; no visit or review.
- **Failure conditions:** Lost state, duplicate writes, account prompt blocks the save, or the action implies attendance.
- **Observe:** Does Interested mean what supporters expect, and does its low-commitment nature remain clear?

### 3. Solo supporter plans socially

- **Starting state:** Upcoming Interested fixture; anonymous or registered state must be explicit.
- **Motivation:** Find company and ask matchday questions.
- **Actions:** Try Who's Going?; read the Match Board; create or sign into an account; complete minimum profile setup; return and attempt to post.
- **Expected product state:** Anonymous reading works; Who's Going? and posting require an account; account setup returns safely to the fixture; completed boards remain readable but closed to new posts.
- **Expected state outcome:** Meeting intent exists only for an eligible account and implies Interested; the anonymous owner is claimed in place with no duplicated activity.
- **Failure conditions:** Meeting intent without Interested, anonymous intent creation, unclear account gate, or inaccessible board reading.
- **Observe:** Is the difference between Who's Going? and the Match Board obvious, and does the safety/account copy feel proportionate?

### 4. Ground research before attending

- **Starting state:** User is considering or has saved a fixture.
- **Motivation:** Understand travel, atmosphere, facilities and supporter advice.
- **Actions:** Open fixture; open venue; inspect Terrace Rating, What the Terrace Says, tips and upcoming fixtures.
- **Expected product state:** Canonical current ground information is coherent and the user can return to the fixture.
- **Expected state outcome:** Read-only activity; no visit/review is inferred.
- **Failure conditions:** Conflicting names, ratings without context, buried travel/tip information, or broken fixture–venue navigation.
- **Observe:** Is the information sufficient for a real matchday decision without feeling like a generic venue database?

### 5. Return on matchday

- **Starting state:** Fixture is Interested and now occurs today; attendance has not been recorded.
- **Motivation:** Reopen plans, ground details and community information quickly.
- **Actions:** Open My Matchdays; return to fixture; inspect timing, venue and board.
- **Expected product state:** Fixture is easy to recover under Upcoming and pre-match actions remain available until completion.
- **Expected state outcome:** Interested remains intent only; no attendance row is created automatically.
- **Failure conditions:** Fixture disappears too early, completed controls appear prematurely, or current information is hard to find.
- **Observe:** Does My Matchdays work as a practical matchday return point?

### 6. Record completed-fixture attendance

- **Starting state:** Fixture status is `FT`, `AET` or `PEN`; user has no attendance for it.
- **Motivation:** Add the match to personal history.
- **Actions:** Choose **Yes — I was there**; reopen the fixture, My Matchdays and My Grounds.
- **Expected product state:** “Attendance recorded” persists; match appears under Attended; its ground appears in My Grounds.
- **Expected state outcome:** One fixture-linked `venue_visits` row using canonical `venue_id`; no review required.
- **Failure conditions:** Duplicate visit, missing ground/match history, review created automatically, or state lost after refresh.
- **Observe:** Is recording attendance sufficiently low friction?

### 7. Attend without reviewing

- **Starting state:** Newly recorded attendance; no venue review.
- **Motivation:** Preserve history without giving an opinion.
- **Actions:** Ignore Rate the Ground and Add a Tip; navigate away and return later.
- **Expected product state:** Attendance and My Grounds membership persist; rating remains optional.
- **Expected state outcome:** Visit exists; no new `away_day_reviews` row is required.
- **Failure conditions:** History disappears, persistent nagging blocks progress, or blank review is created merely by attendance.
- **Observe:** Is the product comfortable with a lightweight record-only journey?

### 8. Attend and rate the ground

- **Starting state:** Attendance exists; no review or a blank review state.
- **Motivation:** Record a considered venue opinion.
- **Actions:** Select Rate the Ground; enter categories and recommendation; save; revisit venue and My Grounds.
- **Expected product state:** One completed personal review is shown and attendance remains independent.
- **Expected state outcome:** Existing visit unchanged; one `away_day_reviews` row for user/venue; aggregate behavior unchanged.
- **Failure conditions:** Second visit/review created, attendance overwritten, scores lost, or review cannot be edited.
- **Observe:** Is the review request happening at the right moment and is the effort proportionate?

### 9. Add a supporter tip

- **Starting state:** User has attended and is viewing the fixture/venue follow-up actions.
- **Motivation:** Help the next supporter with practical knowledge.
- **Actions:** Choose Add a Tip; submit useful advice; revisit the venue tips section.
- **Expected product state:** Tip appears through the existing moderation/status behavior; attendance and review remain unchanged.
- **Expected state outcome:** One tip row linked to the canonical venue and current owner where applicable.
- **Failure conditions:** Tip route misses the form, duplicate submission, unclear success, or tip mutates review/visit state.
- **Observe:** Is contribution invited while the experience is fresh without feeling pushy?

### 10. Revisit the same venue for another fixture

- **Starting state:** User has one fixture-linked visit at a venue.
- **Motivation:** Preserve a second matchday at a familiar ground.
- **Actions:** Record attendance at a different completed fixture at the same venue; inspect both histories.
- **Expected product state:** Venue remains one My Grounds entry with two visits; both matches appear under Attended.
- **Expected state outcome:** Two fixture-linked visits, one stable venue ID and at most one venue review.
- **Failure conditions:** Duplicate ground card, overwritten first visit, collapsed matchdays, or second review created.
- **Observe:** Is repeat attendance meaningfully represented?

### 11. Historical ground with unknown fixture/date

- **Starting state:** Venue is not in My Grounds.
- **Motivation:** Record an old ground despite incomplete memory.
- **Actions:** Search for the ground; add it without a date.
- **Expected product state:** Ground appears once with an honest undated-history indicator.
- **Expected state outcome:** One manual undated visit; no fixture and no required review.
- **Failure conditions:** Invented date/fixture, inability to add, duplicate venue identity, or misleading “latest” value.
- **Observe:** Does Make It One of Yours clearly communicate visited-ground recording?

### 12. Historical ground with a known date

- **Starting state:** Venue is not in My Grounds.
- **Motivation:** Preserve a dated historical visit.
- **Actions:** Search; supply the known date; add; inspect chronology.
- **Expected product state:** First/latest date reflects the supplied visit and no fixture is implied.
- **Expected state outcome:** One manual dated visit linked to canonical venue ID.
- **Failure conditions:** Time-zone date shift, duplicate on retry, fixture invented, or date not shown accurately.
- **Observe:** Is optional date entry discoverable without making basic ground recording cumbersome?

### 13. Remove incorrect fixture attendance

- **Starting state:** Fixture attendance was recorded mistakenly; other data may exist at the venue.
- **Motivation:** Correct personal match history.
- **Actions:** Choose Remove Attendance; confirm persisted fixture and My Grounds state.
- **Expected product state:** That match leaves Attended; unrelated visits, review and tips remain.
- **Expected state outcome:** Only the matching fixture-linked visit is deleted; repeated removal is harmless.
- **Failure conditions:** Review/tip deletion, another visit removed, stale recorded state, or ground removed despite other visits.
- **Observe:** Is cautious removal copy clear enough without creating anxiety?

### 14. Remove the only attendance while a review remains

- **Starting state:** One fixture visit and one venue review; no other visits at that venue.
- **Motivation:** Correct false attendance without retracting a genuine venue opinion.
- **Actions:** Remove attendance; inspect fixture, My Grounds, venue and review access.
- **Expected product state:** Match is no longer Attended and venue is no longer in visit-derived My Grounds; review remains available on the venue where appropriate.
- **Expected state outcome:** Zero visits for user/venue; existing review row and values unchanged.
- **Failure conditions:** Review deletion, review still defines visited state, map remains visited, or orphaned review causes an error.
- **Observe:** Can users understand that Reviewed Ground and Visited Ground are distinct states in this exceptional case?

### 15. My Grounds with multiple venues and repeats

- **Starting state:** Mix of dated, undated, fixture-linked, reviewed and unreviewed grounds.
- **Motivation:** Remember personal football history at a glance.
- **Actions:** Browse cards; compare counts/dates/ratings; expand match history; open a ground.
- **Expected product state:** Each canonical venue appears once; repeat visits and review status are legible without oversized cards.
- **Expected state outcome:** Membership equals distinct visited venue IDs; counts equal visit rows per venue.
- **Failure conditions:** Duplicate grounds, review-driven membership, misleading chronology, clutter, or inaccessible details.
- **Observe:** Does My Grounds feel like personal football history rather than a database?

### 16. My Matchdays with Upcoming and Attended

- **Starting state:** User has Interested future fixtures and fixture-linked past visits.
- **Motivation:** Understand what is planned and what has happened.
- **Actions:** Open My Matchdays; inspect Upcoming and Attended; navigate to both fixture types.
- **Expected product state:** Intent and history are distinct but coherent; manual ground visits do not appear as matches.
- **Expected state outcome:** Upcoming comes from `interested_fixtures`; Attended comes only from fixture-linked `venue_visits`.
- **Failure conditions:** Mixed chronology, manual visits shown as fixtures, unclear headings, or Interested presented as attendance.
- **Observe:** Is My Matchdays understandable as both future intent and attended history?

### 17. Edit one review after a repeat visit

- **Starting state:** Venue has multiple visits and one completed review.
- **Motivation:** Update the single overall venue opinion after a new experience.
- **Actions:** Open Edit My Review; change scores/recommendation; save; inspect history and aggregates.
- **Expected product state:** Review changes; all visits remain intact; no second review is offered.
- **Expected state outcome:** Same review ID updated; visit count and fixture links unchanged.
- **Failure conditions:** New review/visit, reassigned fixture history, lost earlier attendance, or stale review state.
- **Observe:** Does one evolving venue opinion make sense after repeat visits?

### 18. Visited map marker without review

- **Starting state:** User has a visit for a venue and no review.
- **Motivation:** Recognize previously visited grounds during new discovery.
- **Actions:** Run a search containing the venue; inspect map/list visited treatment; open the venue.
- **Expected product state:** Ground is marked visited based on canonical venue ID despite having no review.
- **Expected state outcome:** Marker state comes from `/my-grounds`/`venue_visits`, not `away_day_reviews`.
- **Failure conditions:** Missing marker, review required, alias produces another venue, or unrelated venue marked visited.
- **Observe:** Can users distinguish a visited but unreviewed ground immediately?

### 19. Future established-user import

- **Starting state:** **Future-only:** registered supporter has substantial Futbology/competitor history; import is not implemented today.
- **Motivation:** Avoid manually recreating years of ground history.
- **Actions:** Walk through the documented export/upload or paste concept, canonical matching, exception review and confirmation without pretending it is live.
- **Expected product state:** Proposed flow previews matched, ambiguous and unmatched grounds and asks the user to resolve exceptions only.
- **Expected state outcome:** Future writes attach visits to the same registered `users.user_id` and canonical venue IDs; re-import is idempotent.
- **Failure conditions:** Product implies unsupported competitor access, silent bad matches, duplicate grounds, loss of dates/fixtures, or writes before confirmation.
- **Observe:** What minimum import fidelity makes the migration trustworthy, and which competitor export formats are genuinely obtainable?

### 20. Accurate repeat-visit history

- **Starting state:** One venue has fixture-linked visits, manual dated visits and possibly one undated historical visit.
- **Motivation:** Trust Matchgoer as the long-term record of multiple matchdays.
- **Actions:** Compare My Grounds visit count, dates and expanded matches with My Matchdays Attended and source records.
- **Expected product state:** One venue identity summarizes all visits; known fixtures are individually accessible; unknown history is labelled honestly.
- **Expected state outcome:** Count equals all distinct visit rows allowed by uniqueness rules; only fixture-linked rows populate Attended; one venue review remains independent.
- **Failure conditions:** Double-counting, lost visit, undated visit masquerading as a match, duplicate venue, or review count mistaken for visit count.
- **Observe:** Is repeat attendance meaningfully represented, useful and emotionally resonant rather than merely numeric?

## Cross-journey observation questions

Record evidence and participant language for each:

- Does Interested mean what supporters expect?
- Is My Matchdays understandable as both future intent and attended history?
- Does Make It One of Yours clearly communicate visited-ground recording?
- Is recording attendance sufficiently low friction?
- Is the review/tip request happening at the right moment?
- Does My Grounds feel like personal football history rather than a database?
- Is repeat attendance meaningfully represented?
- Can users always understand the distinction between Interested, Attended, Visited Ground and Reviewed Ground?

## Gate exit

Phase 3.5 is complete only when all applicable current scenarios have been run end to end, failures and observations have been recorded, and the team has decided which findings block the next pass. Scenario 19 is a future concept test and does not require an implemented importer. The next planned implementation after this gate is **My Matchdays Design System V1**.
