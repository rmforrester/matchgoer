import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { hasKnowContent, selectFixtureKnowHighlights, showPrimaryIdentityHeadline, type FixtureKnow } from "./know-v1.ts";

const empty: FixtureKnow = { fixture_id: 1, team_id: 2, venue_id: 3, club_venue_id: 4, club: [], supporters: [], matchday: [], dont_miss: [], before_match: [], good_to_know: [] };
const renderer = readFileSync(new URL("../app/components/FixtureKnow.tsx", import.meta.url), "utf8");
const fixturePage = readFileSync(new URL("../app/fixture/[fixtureId]/page.tsx", import.meta.url), "utf8");
const venueGuide = readFileSync(new URL("../app/components/VenueGuide.tsx", import.meta.url), "utf8");

test("all KNOW modules are independently optional", () => {
  assert.equal(hasKnowContent(empty), false);
  for (const key of ["club", "supporters", "matchday", "dont_miss", "before_match", "good_to_know"] as const) {
    const value = key === "before_match" ? [{ pre_match_spot_id: 1, display_name: "Spot", classification: "SUPPORTER_SPOT" as const, audience: "HOME" as const, supporting_line: null, location_context: null, directions_url: null }] : [{ know_fact_id: 1, headline: null, content: "Useful fact", provenance: [] }];
    assert.equal(hasKnowContent({ ...empty, [key]: value }), true);
  }
});

test("BTM-only rendering is supported with supporter-facing copy and conditional Directions", () => {
  assert.match(renderer, /Places supporters go before kickoff\./);
  assert.match(renderer, /spot\.directions_url &&/);
  assert.match(venueGuide, /guide\.sections\.length === 0 && guide\.before_match\.length === 0/);
  assert.doesNotMatch(venueGuide, /Ticket information not yet confirmed/);
});

test("fixture guidance shows one identity and one practical highlight before BTM and optional context", () => {
  const identity = renderer.indexOf("Who you&apos;re watching");
  const essentials = renderer.indexOf("Matchday essentials");
  const beforeMatch = renderer.indexOf("Before the match");
  const dontMiss = renderer.indexOf("Don&apos;t miss");
  const more = renderer.indexOf("More about this matchday");
  assert.ok(identity >= 0 && identity < essentials && essentials < beforeMatch && beforeMatch < dontMiss && dontMiss < more);
  assert.match(renderer, /highlights\.primaryIdentity/);
  assert.match(renderer, /highlights\.primaryMatchday/);
  assert.match(renderer, /<details className=/);
  assert.match(renderer, /More matchday essentials/);
  assert.match(renderer, /Useful to know/);
});

test("highlight selection is deterministic and leaves secondary facts collapsed", () => {
  const fact = (id: number): FixtureKnow["club"][number] => ({ know_fact_id: id, headline: null, content: `Fact ${id}`, provenance: [] });
  const selected = selectFixtureKnowHighlights({
    ...empty,
    club: [fact(1), fact(2)],
    supporters: [fact(3)],
    matchday: [fact(4), fact(5)],
  });
  assert.equal(selected.primaryIdentity?.know_fact_id, 1);
  assert.equal(selected.primaryIdentityModule, "CLUB");
  assert.deepEqual(selected.secondaryClub.map((item) => item.know_fact_id), [2]);
  assert.deepEqual(selected.secondarySupporters.map((item) => item.know_fact_id), [3]);
  assert.equal(selected.primaryMatchday?.know_fact_id, 4);
  assert.deepEqual(selected.secondaryMatchday.map((item) => item.know_fact_id), [5]);
});

test("supporter identity is promoted only when no club identity exists and sparse pages stay empty", () => {
  const supporter = { know_fact_id: 6, headline: null, content: "Supporter identity", provenance: [] };
  const selected = selectFixtureKnowHighlights({ ...empty, supporters: [supporter] });
  assert.equal(selected.primaryIdentity?.know_fact_id, 6);
  assert.equal(selected.primaryIdentityModule, "SUPPORTERS");
  assert.equal(selectFixtureKnowHighlights(empty).primaryIdentity, null);
  assert.equal(hasKnowContent(empty), false);
});

test("published provenance remains in the API type but does not dominate the fixture UI", () => {
  assert.doesNotMatch(renderer, /fact\.provenance|Evidence|Editorial/);
});

test("WHY THIS MATCH stays before KNOW and Ground Essentials stays secondary", () => {
  const why = fixturePage.indexOf("Why this match");
  const tickets = fixturePage.indexOf("Buy tickets →");
  const know = fixturePage.indexOf("<FixtureKnow know={know}");
  const ground = fixturePage.indexOf("Ground essentials");
  assert.ok(why >= 0 && tickets > why && know > tickets && ground > know);
  assert.match(fixturePage, /decisionReasons\[0\]\.explanation/);
  assert.doesNotMatch(fixturePage, /Before the match · \{venueGuide\.before_match\.length\}/);
  assert.doesNotMatch(fixturePage, /Terrace roll call/i);
  assert.match(fixturePage, /Ask other supporters about the match, pubs, travel or the ground\./);
});

test("fixture ticket action uses compact separation without changing no-action KNOW spacing", () => {
  assert.match(fixturePage, /data\.ticket_action && <section className="tt-section-rule mt-6 pt-3"/);
  assert.match(fixturePage, /<FixtureKnow know=\{know\} compactTop=\{Boolean\(data\.ticket_action\)\}/);
  assert.match(renderer, /compactTop \? "mt-8" : "mt-10"/);
});

test("venue guide presents useful sections without redundant wrappers", () => {
  assert.doesNotMatch(venueGuide, /Know before you go/);
  assert.doesNotMatch(venueGuide, />The essentials</);
  assert.match(venueGuide, /Where home supporters gather before the game\./);
  assert.doesNotMatch(venueGuide, />Buy tickets →<\/a>/);
  assert.match(venueGuide, /supporterFacingFactContent\(fact\)/);
});

test("single identity facts omit the redundant sub-label", () => {
  const fact = { know_fact_id: 1, headline: "Club identity", content: "Identity", provenance: [] };
  assert.equal(showPrimaryIdentityHeadline({ ...empty, club: [fact] }), false);
  assert.equal(showPrimaryIdentityHeadline({ ...empty, supporters: [fact] }), false);
});

test("mixed and multiple identity facts retain sub-labels", () => {
  const first = { know_fact_id: 1, headline: "Club identity", content: "Identity", provenance: [] };
  const second = { ...first, know_fact_id: 2, headline: "Supporter culture" };
  assert.equal(showPrimaryIdentityHeadline({ ...empty, club: [first], supporters: [second] }), true);
  assert.equal(showPrimaryIdentityHeadline({ ...empty, club: [first, second] }), true);
  assert.equal(showPrimaryIdentityHeadline({ ...empty, supporters: [first, second] }), true);
});
