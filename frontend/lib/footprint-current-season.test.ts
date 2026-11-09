import assert from "node:assert/strict";
import test from "node:test";
import { footprintGrounds, competitionsForGrounds, competitionGroundProgress } from "./football-footprint.ts";
import { footballPassport } from "./my-grounds.ts";
import type { MyGround, FootprintSummary, FootprintCompetition } from "../app/types/grounds.ts";

const ground = {
  venue_id: 11, venue_name: "Hinchliffe Stadium", venue_country: "USA", venue_city: "Paterson",
  visits: [{ visit_id: 1, visit_date: "2026-10-24", fixture_id: 10 },
    { visit_id: 2, visit_date: "2026-10-24", fixture_id: 20 },
    { visit_id: 3, visit_date: "2025-10-24", fixture_id: 30 }],
  visit_count: 3, attended_fixtures: [{ fixture_id: 10 }, { fixture_id: 20 }, { fixture_id: 30 }],
  review: { overall_score: 9 }, community_terrace_rating: 8, independently_saved: true,
} as MyGround;
const competition = {
  competition_id: 489, season: 2026, season_label: "2026", name: "USL League One", country: "USA",
  season_start: null, season_end: null,
  coverage: "attendance", total_clubs: 0, lifetime_clubs: null, season_clubs: null,
  grounds: [{ venue_id: 11, clubs: [], visit_ids: [1, 2], season_visit_ids: [1, 2] }],
} as FootprintCompetition;
const footprint = { reviewed_on: "2026-10-17", season_visit_ids: [1, 2], unclassified_dated_visits: 1,
  competitions: [], attendance_competitions: [competition] } as FootprintSummary;

test("USL season outside reviewed homes is visible with unique grounds and exact matchdays", () => {
  const result = footprintGrounds([ground], "season", footprint);
  assert.equal(result.length, 1);
  assert.equal(result[0].visit_count, 2);
  assert.deepEqual(result[0].attended_fixtures.map(f => f.fixture_id), [10, 20]);
  assert.deepEqual(footballPassport(result), [{ key: "united states", name: "United States", groundCount: 1, matchdayCount: 2 }]);
  assert.equal(result[0].review, ground.review);
  assert.equal(result[0].community_terrace_rating, 8);
  const groups = competitionsForGrounds([competition], result, "season");
  assert.equal(groups[0].name, "USL League One");
  assert.deepEqual(groups[0].grounds[0].visit_ids, [1, 2]);
  assert.equal(competitionGroundProgress(groups[0]), null);
});

test("rollover removes only season projection; lifetime and ratings stay unchanged", () => {
  const before = structuredClone(ground);
  const next = { ...footprint, season_visit_ids: [], attendance_competitions: [{ ...competition,
    grounds: [{ ...competition.grounds[0], season_visit_ids: [] }] }] };
  assert.deepEqual(footprintGrounds([ground], "season", next), []);
  assert.equal(footprintGrounds([ground], "lifetime", next)[0], ground);
  assert.equal(competitionsForGrounds(next.attendance_competitions, [ground], "lifetime")[0].season, 2026);
  assert.deepEqual(ground, before);
});
