import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { hasKnowContent, type FixtureKnow } from "./know-v1.ts";

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

test("BTM-only rendering is supported with frozen copy and conditional Directions", () => {
  assert.match(renderer, /Where home supporters gather before the game\./);
  assert.match(renderer, /spot\.directions_url &&/);
  assert.match(venueGuide, /guide\.sections\.length === 0 && guide\.before_match\.length === 0/);
  assert.doesNotMatch(venueGuide, /Ticket information not yet confirmed/);
});

test("WHY THIS MATCH stays before KNOW and Ground Essentials stays secondary", () => {
  const why = fixturePage.indexOf("Why this match");
  const know = fixturePage.indexOf("<FixtureKnow know={know}");
  const ground = fixturePage.indexOf("Ground essentials");
  assert.ok(why >= 0 && know > why && ground > know);
  assert.match(fixturePage, /decisionReasons\[0\]\.explanation/);
  assert.doesNotMatch(fixturePage, /Before the match · \{venueGuide\.before_match\.length\}/);
  assert.doesNotMatch(fixturePage, /Terrace roll call/i);
  assert.match(fixturePage, /Ask other supporters about the match, pubs, travel or the ground\./);
});

test("venue guide presents useful sections without redundant wrappers", () => {
  assert.doesNotMatch(venueGuide, /Know before you go/);
  assert.doesNotMatch(venueGuide, />The essentials</);
  assert.match(venueGuide, /Where home supporters gather before the game\./);
});
