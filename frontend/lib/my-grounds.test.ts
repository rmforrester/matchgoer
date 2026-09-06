import assert from "node:assert/strict";
import test from "node:test";
import { groundsInTimeframe } from "./my-grounds.ts";
import type { MyGround } from "../app/types/grounds.ts";

const ground = (visits: MyGround["visits"]): MyGround => ({
  venue_id: 1, venue_name: "A Very Long Community Football Stadium Name", venue_city: "A long city name",
  venue_country: "England", capacity: null, latitude: 1, longitude: 1, visits,
  visit_count: visits.length, first_visit_date: null, latest_visit_date: null,
  has_undated_visit: visits.some((visit) => visit.visit_date === null), attended_fixtures: [], review: null,
  community_terrace_rating: null, community_review_count: 0, community_recommend_percentage: null,
});

test("lifetime retains dated and date-not-remembered visits", () => {
  assert.equal(groundsInTimeframe([ground([{ visit_id: 1, visit_date: null, fixture_id: null }])], "lifetime").length, 1);
});

test("finite timeframes use visit dates and do not invent dates", () => {
  const item = ground([
    { visit_id: 1, visit_date: null, fixture_id: null },
    { visit_id: 2, visit_date: "2026-08-20", fixture_id: null },
    { visit_id: 3, visit_date: "2025-01-01", fixture_id: null },
  ]);
  const filtered = groundsInTimeframe([item], "30d", new Date("2026-09-06T12:00:00Z"));
  assert.equal(filtered[0].visit_count, 1);
  assert.equal(filtered[0].latest_visit_date, "2026-08-20");
});
