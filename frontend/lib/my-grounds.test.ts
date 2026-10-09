import assert from "node:assert/strict";
import test from "node:test";
import { groundsInTimeframe } from "./my-grounds.ts";
import type { MyGround } from "../app/types/grounds.ts";
import { readFileSync } from "node:fs";

const visitedTab = readFileSync(new URL("../app/components/VisitedTab.tsx", import.meta.url), "utf8");

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

test("My Grounds keeps one contextual add flow and compact card actions", () => {
  assert.match(visitedTab, /grounds\.length > 0 && <button/);
  assert.match(visitedTab, /aria-controls="add-ground"/);
  assert.match(visitedTab, /grounds\.length > 0 && showAddGround && <section id="add-ground"/);
  assert.match(visitedTab, /grounds\.length === 0 && <section id="add-ground"/);
  assert.ok(visitedTab.indexOf("showAddGround && <section") < visitedTab.indexOf("My football world map"));
  assert.match(visitedTab, /Add somewhere you&apos;ve been\./);
  assert.doesNotMatch(visitedTab, /A review is optional\./);
  assert.doesNotMatch(visitedTab, />Add a visit<\/button>/);
  assert.match(visitedTab, /View ground →/);
});

test("all periods preserve visit identity, repeat visits and chronological metadata without mutating history", () => {
  const item = ground([
    { visit_id: 1, visit_date: "2025-01-01", fixture_id: null },
    { visit_id: 2, visit_date: "2026-03-01", fixture_id: null },
    { visit_id: 3, visit_date: "2026-08-01", fixture_id: null },
    { visit_id: 4, visit_date: "2026-10-01", fixture_id: 99 },
    { visit_id: 5, visit_date: null, fixture_id: null },
  ]);
  item.attended_fixtures = [{ fixture_id: 99, fixture_date: "2026-10-01T15:00:00Z", home_team: "Home", away_team: "Away", league_name: "League", status: "FT", home_goals: 1, away_goals: 0 }];
  const original = structuredClone(item);
  const now = new Date("2026-10-09T12:00:00Z");
  for (const [period, ids] of [["30d", [4]], ["3m", [3, 4]], ["1y", [2, 3, 4]], ["lifetime", [1, 2, 3, 4, 5]]] as const) {
    const result = groundsInTimeframe([item], period, now);
    assert.equal(result.length, 1);
    assert.equal(result[0].venue_id, item.venue_id);
    assert.deepEqual(result[0].visits.map(visit => visit.visit_id), ids);
    assert.equal(result[0].visit_count, ids.length);
    assert.equal(result[0].latest_visit_date, "2026-10-01");
    assert.equal(result[0].has_undated_visit, period === "lifetime");
    assert.deepEqual(result[0].attended_fixtures.map(fixture => fixture.fixture_id), [99]);
  }
  assert.deepEqual(item, original);
});
