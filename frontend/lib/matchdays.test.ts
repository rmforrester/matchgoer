import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { previewItems, trustworthyScore, canConfirmAttendance, partitionMatchdays } from "./matchdays.ts";

const matchdaysPage = readFileSync(new URL("../app/components/InterestedTab.tsx", import.meta.url), "utf8");
const navigation = readFileSync(new URL("../app/components/Navigation.tsx", import.meta.url), "utf8");

test("bounds and expands matchday lists", () => {
  assert.deepEqual(previewItems([1, 2, 3, 4], 2, false), [1, 2]);
  assert.deepEqual(previewItems([1, 2, 3, 4], 2, true), [1, 2, 3, 4]);
});

test("shows only complete final scores", () => {
  assert.equal(trustworthyScore({ status: "FT", home_goals: 2, away_goals: 1 }), "2–1");
  assert.equal(trustworthyScore({ status: "NS", home_goals: null, away_goals: null }), null);
  assert.equal(trustworthyScore({ status: "FT", home_goals: 2, away_goals: null }), null);
});

test("matchday occasions use bounded editorial cards with a graceful score fallback", () => {
  assert.match(matchdaysPage, /tt-panel min-w-0 p-4 sm:p-5/);
  assert.match(matchdaysPage, /FixtureTeams compact/);
  assert.match(matchdaysPage, /UPCOMING_PREVIEW_LIMIT/);
  assert.match(matchdaysPage, /ANSWER_PREVIEW_LIMIT/);
  assert.match(matchdaysPage, /PAST_PREVIEW_LIMIT/);
});

test("mobile wordmark is calibrated without changing its desktop width", () => {
  assert.match(navigation, /w-\[7\.75rem\] sm:w-\[10\.5rem\]/);
});

const kickoff = "2026-10-10T14:00:00Z";
const saved = (id: number, going = false, status = "NS") => ({ fixture_id: id, fixture_date: kickoff, going, status });
test("three hour check-in does not require FT and excludes likely live or non-played matches", () => {
  assert.equal(canConfirmAttendance(saved(1), new Date("2026-10-10T16:59:59Z")), false);
  assert.equal(canConfirmAttendance(saved(1), new Date("2026-10-10T17:00:00Z")), true);
  for (const status of ["PST", "CANC", "ABD", "AWD", "WO", "1H", "HT", "2H", "ET", "P", "LIVE", "SUSP", "INT"])
    assert.equal(canConfirmAttendance(saved(1, false, status), new Date("2026-10-11T17:00:00Z")), false);
  assert.equal(canConfirmAttendance({ ...saved(1), fixture_date: "2026-10-10T10:00:00-04:00" }, new Date("2026-10-10T17:00:00Z")), true);
  assert.equal(canConfirmAttendance({ ...saved(1), fixture_date: "invalid" }, new Date()), false);
});
test("sections are exclusive, Went wins, Going is prioritized and retained plans remain accessible", () => {
  const result = partitionMatchdays([saved(1), saved(2, true), saved(3, true), saved(4, true, "PST"), saved(1)], new Set([3]), new Date("2026-10-10T17:00:00Z"));
  assert.deepEqual(result.awaiting.map(f => f.fixture_id), [2, 1]);
  assert.deepEqual(result.going.map(f => f.fixture_id), [4]);
  assert.equal(result.interested.length, 0);
  const upcoming = partitionMatchdays([saved(1), saved(2, true)], new Set(), new Date("2026-10-10T10:00:00Z"));
  assert.deepEqual(upcoming.going.map(f => f.fixture_id), [2]);
  assert.deepEqual(upcoming.interested.map(f => f.fixture_id), [1]);
});
test("confirmation preserves saves, decline alone deletes and old backend hides Going controls", () => {
  assert.match(matchdaysPage, /if \(!attended\) await api\.delete/);
  assert.match(matchdaysPage, /typeof fixture\.going === "boolean"/);
  assert.match(matchdaysPage, /View match/);
});
