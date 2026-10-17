import test from "node:test";
import assert from "node:assert/strict";
import { footprintGrounds, competitionsForGrounds } from "./football-footprint.ts";
import { footballPassport } from "./my-grounds.ts";
import type { MyGround, FootprintSummary } from "../app/types/grounds.ts";

const ground: MyGround = {
  venue_id: 11, venue_name: "Shared ground", venue_country: "England", venue_city: "Test",
  latitude: 51, longitude: 0, capacity: null, visit_count: 3, first_visit_date: "1999-01-01",
  latest_visit_date: "2026-09-01", has_undated_visit: true,
  visits: [{ visit_id: 1, visit_date: null, fixture_id: null },
    { visit_id: 2, visit_date: "1999-01-01", fixture_id: 7 },
    { visit_id: 3, visit_date: "2026-09-01", fixture_id: 8 }],
  attended_fixtures: [], review: null, community_terrace_rating: null, community_review_count: 0, community_recommend_percentage: null,
};
const summary: FootprintSummary = { reviewed_on: "2026-10-17", season_visit_ids: [3], unclassified_dated_visits: 1,
  competitions: [{ competition_id: 39, season: 2026, season_label: "2026/27", name: "League", country: "England",
    season_start: "2026-08-01", season_end: "2027-05-31", coverage: "ready", total_clubs: 2, lifetime_clubs: 2, season_clubs: 2,
    grounds: [{ venue_id: 11, clubs: ["One", "Two"], season_visit_ids: [3] }] }] };

test("Lifetime preserves all history, dates, reviews and input", () => {
  assert.equal(footprintGrounds([ground], "lifetime", summary)[0], ground);
  assert.equal(footprintGrounds([ground], "lifetime", null)[0], ground);
});
test("season projection updates all ground-derived counters and fixture attribution together", () => {
  const before = structuredClone(ground);
  const selected = footprintGrounds([ground], "season", summary);
  assert.deepEqual(selected[0].visits.map(v => v.visit_id), [3]);
  assert.equal(selected[0].visit_count, 1);
  assert.equal(selected[0].first_visit_date, "2026-09-01");
  assert.equal(selected[0].has_undated_visit, false);
  assert.deepEqual(footballPassport(selected), [{ key: "england", name: "England", groundCount: 1, matchdayCount: 1 }]);
  assert.deepEqual(ground, before);
});
test("missing contract and empty season cannot fall back to lifetime counts", () => {
  assert.deepEqual(footprintGrounds([ground], "season", null), []);
  assert.deepEqual(footprintGrounds([ground], "season", { ...summary, season_visit_ids: [] }), []);
});
test("stale visit IDs from another account cannot introduce grounds", () => {
  assert.deepEqual(footprintGrounds([{ ...ground, visits: [{ visit_id: 90, visit_date: "2026-09-01", fixture_id: null }] }], "season", summary), []);
});
test("country hierarchy only shows relevant grounds; shared clubs remain on one row", () => {
  const selected = competitionsForGrounds(summary.competitions, [ground], "season");
  assert.equal(selected[0].grounds.length, 1);
  assert.equal(selected[0].grounds[0].clubs.length, 2);
  assert.deepEqual(competitionsForGrounds(summary.competitions, [], "lifetime"), []);
});
